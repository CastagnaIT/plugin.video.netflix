# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for directory handling

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps

from future.utils import iteritems

import xbmc
import xbmcgui
import xbmcplugin

import resources.lib.common as common
from resources.lib.api.api_requests import verify_profile_lock
from resources.lib.database.db_utils import TABLE_MENU_DATA
from resources.lib.globals import g
from resources.lib.kodi.ui import ask_for_pin


def custom_viewmode(partial_setting_id):
    """Decorator that sets a custom viewmode if currently in a listing of the plugin"""
    # pylint: disable=missing-docstring
    def decorate_viewmode(func):
        @wraps(func)
        def set_custom_viewmode(*args, **kwargs):
            # pylint: disable=no-member
            override_partial_setting_id = func(*args, **kwargs)
            _activate_view(override_partial_setting_id
                           if override_partial_setting_id else
                           partial_setting_id)
        return set_custom_viewmode
    return decorate_viewmode


def _activate_view(partial_setting_id):
    """Activate the given view if the plugin is run in the foreground"""
    if 'plugin://{}'.format(g.ADDON_ID) in xbmc.getInfoLabel('Container.FolderPath'):
        if g.ADDON.getSettingBool('customview'):
            view_mode = int(g.ADDON.getSettingInt('viewmode' + partial_setting_id))
            if view_mode == 0:
                # Leave the management to kodi
                return
            # Force a custom view, get the id from settings
            view_id = int(g.ADDON.getSettingInt('viewmode' + partial_setting_id + 'id'))
            if view_id > 0:
                xbmc.executebuiltin('Container.SetViewMode({})'.format(view_id))


def convert_list_to_list_items(list_data):
    """Convert a generic list (of dict) items into a list of xbmcgui.Listitem"""
    list_items = []
    for dict_item in list_data:
        list_items.append(_convert_dict_to_listitem(dict_item))
    return list_items


def convert_list_to_dir_items(list_data):
    """Convert a generic list (of dict) items into a list of directory tuple items for xbmcplugin.addDirectoryItems"""
    directory_items = []
    for dict_item in list_data:
        directory_items.append((dict_item['url'], _convert_dict_to_listitem(dict_item), dict_item['is_folder']))
    return directory_items


def _convert_dict_to_listitem(dict_item):
    list_item = xbmcgui.ListItem(label=dict_item['label'], offscreen=True)
    list_item.setContentLookup(False)
    properties = dict_item.get('properties', {})  # 'properties' key allow to set custom properties to xbmcgui.Listitem
    properties['isFolder'] = str(dict_item['is_folder'])

    if not dict_item['is_folder'] and dict_item['media_type'] in [common.VideoId.EPISODE,
                                                                  common.VideoId.MOVIE,
                                                                  common.VideoId.SUPPLEMENTAL]:
        properties.update({
            'IsPlayable': 'true',
            'TotalTime': dict_item.get('TotalTime', ''),
            'ResumeTime': dict_item.get('ResumeTime', '')
        })
    for stream_type, quality_info in iteritems(dict_item.get('quality_info', {})):
        list_item.addStreamInfo(stream_type, quality_info)
    list_item.setProperties(properties)
    list_item.setInfo('video', dict_item.get('info', {}))
    list_item.setArt(dict_item.get('art', {}))
    list_item.addContextMenuItems(dict_item.get('menu_items', []))
    if dict_item.get('is_selected'):
        list_item.select(True)
    return list_item


def add_sort_methods(sort_type):
    if sort_type == 'sort_nothing':
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_NONE)
    if sort_type == 'sort_label':
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL)
    if sort_type == 'sort_label_ignore_folders':
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_FOLDERS)
    if sort_type == 'sort_episodes':
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_EPISODE)
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(g.PLUGIN_HANDLE, xbmcplugin.SORT_METHOD_VIDEO_TITLE)


def finalize_directory(items, content_type=g.CONTENT_FOLDER, sort_type='sort_nothing', title=None):
    """Finalize a directory listing. Add items, set available sort methods and content type"""
    if title:
        xbmcplugin.setPluginCategory(g.PLUGIN_HANDLE, title)
    xbmcplugin.setContent(g.PLUGIN_HANDLE, content_type)
    add_sort_methods(sort_type)
    xbmcplugin.addDirectoryItems(g.PLUGIN_HANDLE, items)


def end_of_directory(dir_update_listing, cache_to_disc=True):
    # If dir_update_listing=True overwrite the history list, so we can get back to the main page
    xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE,
                              succeeded=True,
                              updateListing=dir_update_listing,
                              cacheToDisc=cache_to_disc)


def get_title(menu_data, extra_data):
    """Get title for the directory"""
    # Try to get the title from 'extra_data', if not exists then try fallback to the title contained in the 'menu_data'
    # But 'menu_data' do not have the title if:
    # - Is a main-menu, menu data in 'globals' do not have the titles (are saved from build_main_menu_listing)
    # - In case of dynamic menu
    # So get the menu title from TABLE_MENU_DATA of the database
    return extra_data.get('title',
                          menu_data.get('title',
                                        g.LOCAL_DB.get_value(menu_data['path'][1],
                                                             {},
                                                             table=TABLE_MENU_DATA).get('title', '')))


def verify_profile_pin(guid):
    """Verify if the profile is locked by a PIN and ask the PIN"""
    if not g.LOCAL_DB.get_profile_config('isPinLocked', False, guid=guid):
        return True
    pin = ask_for_pin(common.get_local_string(30006))
    return None if not pin else verify_profile_lock(guid, pin)
