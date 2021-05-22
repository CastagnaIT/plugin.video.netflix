# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions to generating context menu items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
import resources.lib.kodi.library_utils as lib_utils
from resources.lib.globals import G


def generate_context_menu_mainmenu(menu_id):
    """Generate context menu items for a listitem of the main menu"""
    items = []
    if menu_id in ['myList', 'continueWatching']:
        items.append(_ctx_item('force_update_list', None, {'menu_id': menu_id}))
    return items


def generate_context_menu_profile(profile_guid, is_autoselect, is_library_playback):
    """Generate context menu items for a listitem of the profile"""
    items = [
        _ctx_item('autoselect_remove_profile' if is_autoselect else 'autoselect_set_profile',
                  None,
                  {'profile_guid': profile_guid}),
        _ctx_item('library_playback_remove_profile' if is_library_playback else 'library_playback_set_profile',
                  None,
                  {'profile_guid': profile_guid}),
        _ctx_item('profile_parental_control', None, {'profile_guid': profile_guid})
    ]
    return items


def generate_context_menu_searchitem(row_id, search_type):
    """Generate context menu items for a listitem of the search menu"""
    items = []
    if search_type == 'text':
        items.append(_ctx_item('search_edit', None, {'row_id': row_id}))
    items.append(_ctx_item('search_remove', None, {'row_id': row_id}))
    return items


def generate_context_menu_remind_me(videoid, is_set, trackid):
    items = []
    if is_set is not None and videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        action = 'remove_remind_me' if is_set else 'add_remind_me'
        items.insert(0, _ctx_item(action, videoid, {'trackid': trackid}))
    return items


def generate_context_menu_items(videoid, is_in_mylist, perpetual_range_start=None, add_remove_watched_status=False):
    """Generate context menu items for a listitem"""
    items = []

    if videoid.mediatype not in [common.VideoId.SUPPLEMENTAL, common.VideoId.EPISODE]:
        # Library operations for supplemental (trailers etc) and single episodes are not allowed
        lib_auto_upd_mode = G.ADDON.getSettingInt('lib_auto_upd_mode')
        if lib_auto_upd_mode != 0:
            items = _generate_library_ctx_items(videoid, lib_auto_upd_mode)

    # Old rating system
    # if videoid.mediatype != common.VideoId.SEASON and \
    #    videoid.mediatype != common.VideoId.SUPPLEMENTAL:
    #     items.insert(0, _ctx_item('rate', videoid))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        items.insert(0, _ctx_item('rate_thumb', videoid))
        if add_remove_watched_status:
            items.insert(0, _ctx_item('remove_watched_status', videoid))

    if (videoid.mediatype != common.VideoId.SUPPLEMENTAL and
            videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]):
        items.insert(0, _ctx_item('trailer', videoid))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        list_action = 'remove_from_list' if is_in_mylist else 'add_to_list'
        items.insert(0, _ctx_item(list_action, videoid, {'perpetual_range_start': perpetual_range_start}))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.EPISODE]:
        # Add menu to allow change manually the watched status when progress manager is enabled
        if G.ADDON.getSettingBool('sync_watched_status'):
            items.insert(0, _ctx_item('change_watched_status', videoid))

    return items


def _generate_library_ctx_items(videoid, lib_auto_upd_mode):
    library_actions = []
    allow_lib_operations = True
    lib_is_sync_with_mylist = (G.ADDON.getSettingBool('lib_sync_mylist') and
                               lib_auto_upd_mode == 2)

    if lib_is_sync_with_mylist:
        # If the synchronization of Netflix "My List" with the Kodi library is enabled
        # only in the chosen profile allow to do operations in the Kodi library otherwise
        # it creates inconsistency to the exported elements and increases the work for sync
        sync_mylist_profile_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         G.LOCAL_DB.get_guid_owner_profile())
        allow_lib_operations = sync_mylist_profile_guid == G.LOCAL_DB.get_active_profile_guid()

    if allow_lib_operations:
        _is_in_library = lib_utils.is_videoid_in_db(videoid)
        if lib_is_sync_with_mylist:
            if _is_in_library:
                library_actions = ['update']
        else:
            library_actions = ['remove', 'update'] if _is_in_library else ['export']

        if videoid.mediatype == common.VideoId.SHOW and _is_in_library:
            library_actions.append('export_new_episodes')
            if lib_utils.is_show_excluded_from_auto_update(videoid):
                library_actions.append('include_in_auto_update')
            else:
                library_actions.append('exclude_from_auto_update')

    return [_ctx_item(action, videoid) for action in library_actions]


def _ctx_item(template, videoid, params=None):
    """Create a context menu item based on the given template and videoid"""
    # Do not move the import to the top of the module header, see context_menu_utils.py
    from resources.lib.kodi.context_menu_utils import CONTEXT_MENU_ACTIONS
    return (CONTEXT_MENU_ACTIONS[template]['label'],
            common.run_plugin_action(
                CONTEXT_MENU_ACTIONS[template]['url'](videoid, params)))
