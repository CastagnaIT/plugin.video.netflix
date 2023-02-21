# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for directory handling

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from functools import wraps

import xbmc
import xbmcplugin

import resources.lib.common as common
from resources.lib.utils.api_requests import verify_profile_lock
from resources.lib.database.db_utils import TABLE_MENU_DATA
from resources.lib.globals import G
from resources.lib.kodi import ui


def custom_viewmode(content_type):
    """Decorator that sets a custom viewmode (skin viewtype) if currently in a listing of the plugin"""
    # pylint: disable=missing-docstring
    def decorate_viewmode(func):
        @wraps(func)
        def set_custom_viewmode(*args, **kwargs):
            override_content_type = func(*args, **kwargs)
            _content_type = override_content_type if override_content_type else content_type
            if (G.ADDON.getSettingBool('customview')
                    and f'plugin://{G.ADDON_ID}' in xbmc.getInfoLabel('Container.FolderPath')):
                # Activate the given skin viewtype if the plugin is run in the foreground
                view_id = G.ADDON.getSettingInt(f'viewmode{_content_type}id')
                if view_id > 0:
                    xbmc.executebuiltin(f'Container.SetViewMode({view_id})')
        return set_custom_viewmode
    return decorate_viewmode


def add_sort_methods(sort_type):
    if sort_type == 'sort_nothing':
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_NONE)
    if sort_type == 'sort_label':
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL)
    if sort_type == 'sort_label_ignore_folders':
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_FOLDERS)
    if sort_type == 'sort_episodes':
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(G.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_VIDEO_TITLE)


def finalize_directory(dir_items, content_type=G.CONTENT_FOLDER, sort_type='sort_nothing', title=None):
    """Finalize a directory listing. Add items, set available sort methods and content type"""
    if title:
        xbmcplugin.setPluginCategory(G.PLUGIN_HANDLE, title)
    xbmcplugin.setContent(G.PLUGIN_HANDLE, content_type)
    add_sort_methods(sort_type)
    xbmcplugin.addDirectoryItems(G.PLUGIN_HANDLE, dir_items)


def end_of_directory(dir_update_listing):
    # If dir_update_listing=True overwrite the history list, so we can get back to the main page
    xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE,
                              succeeded=True,
                              updateListing=dir_update_listing,
                              cacheToDisc=False)


def get_title(menu_data, extra_data):
    """Get title for the directory"""
    # Try to get the title from 'extra_data', if not exists then try fallback to the title contained in the 'menu_data'
    # But 'menu_data' do not have the title if:
    # - Is a main-menu, menu data in 'globals' do not have the titles (are saved from build_main_menu_listing)
    # - In case of dynamic menu
    # So get the menu title from TABLE_MENU_DATA of the database
    return extra_data.get('title',
                          menu_data.get('title',
                                        G.LOCAL_DB.get_value(menu_data['path'][1],
                                                             {},
                                                             table=TABLE_MENU_DATA).get('title', '')))


def activate_profile(guid):
    """Activate a profile and ask the PIN if required"""
    pin_result = verify_profile_pin(guid, G.LOCAL_DB.get_profile_config('addon_remember_pin', False, guid=guid))
    if not pin_result:
        if pin_result is not None:
            G.LOCAL_DB.set_profile_config('addon_pin', '', guid=guid)
            ui.show_notification(common.get_local_string(30106), time=8000)
        return False
    common.make_call('activate_profile', guid)
    return True


def verify_profile_pin(guid, is_remember_pin):
    """Verify if the profile is locked by a PIN and ask the PIN"""
    if not G.LOCAL_DB.get_profile_config('isPinLocked', False, guid=guid):
        return True
    stored_pin = ''
    if is_remember_pin:
        try:
            stored_pin = common.decrypt_string(G.LOCAL_DB.get_profile_config('addon_pin', '', guid=guid))
        except Exception:  # pylint: disable=broad-except
            pass
    if stored_pin:
        pin = stored_pin
    else:
        pin = ui.show_dlg_input_numeric(common.get_local_string(30006))
    if not pin:
        return None
    if verify_profile_lock(guid, pin):
        if is_remember_pin:
            G.LOCAL_DB.set_profile_config('addon_pin', common.encrypt_string(pin), guid=guid)
        return True
    return False


def auto_scroll(dir_items):
    """
    Auto scroll the current viewed list to select the last partial watched or next episode to be watched,
    works only with Sync of watched status with netflix
    """
    # A sad implementation to a Kodi feature available only for the Kodi library
    if G.ADDON.getSettingBool('sync_watched_status') and G.ADDON.getSettingBool('select_first_unwatched'):
        total_items = len(dir_items)
        if total_items:
            # Delay a bit to wait for the completion of the screen update
            xbmc.sleep(200)
            if not _auto_scroll_init_checks():
                return
            # Check if all items are already watched
            watched_items = 0
            to_resume_items = 0
            for _, list_item, _ in dir_items:
                watched_items += list_item.getVideoInfoTag().getPlayCount() != 0
                if G.IS_OLD_KODI_MODULES:
                    resume_time = list_item.getProperty('ResumeTime')
                else:
                    resume_time = list_item.getVideoInfoTag().getResumeTime()
                to_resume_items += float(resume_time) != 0
            if total_items == watched_items or (watched_items + to_resume_items) == 0:
                return
            steps = _find_index_last_watched(total_items, dir_items)
            # Get the sort order of the view
            is_sort_descending = xbmc.getCondVisibility('Container.SortDirection(descending)')
            if is_sort_descending:
                steps = (total_items - 1) - steps
            gui_sound_mode = common.json_rpc('Settings.GetSettingValue',
                                             {'setting': 'audiooutput.guisoundmode'})['value']
            if gui_sound_mode != 0:
                # Disable GUI sounds to avoid squirting sound with item selections
                common.json_rpc('Settings.SetSettingValue',
                                {'setting': 'audiooutput.guisoundmode', 'value': 0})
            # Auto scroll the list
            for _ in range(0, steps + 1):
                common.json_rpc('Input.Down')
            if gui_sound_mode != 0:
                # Restore GUI sounds
                common.json_rpc('Settings.SetSettingValue',
                                {'setting': 'audiooutput.guisoundmode', 'value': gui_sound_mode})


def _auto_scroll_init_checks():
    # Check if view sort method is "Episode" (ID 23 = SortByEpisodeNumber)
    if not xbmc.getCondVisibility('Container.SortMethod(23)'):
        return False
    # Check if a selection is already done (CurrentItem return the index)
    if int(xbmc.getInfoLabel('ListItem.CurrentItem') or 2) > 1:
        return False
    return True


def _find_index_last_watched(total_items, dir_items):
    """Find last watched item"""
    for index in range(total_items - 1, -1, -1):
        list_item = dir_items[index][1]
        if list_item.getVideoInfoTag().getPlayCount() != 0:
            # Last watched item
            return index + 1
        if G.IS_OLD_KODI_MODULES:
            resume_time = list_item.getProperty('ResumeTime')
        else:
            resume_time = list_item.getVideoInfoTag().getResumeTime()
        if float(resume_time) != 0:
            # Last partial watched item
            return index
    return 0
