# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions to generating context menu items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api
from resources.lib.globals import g
from resources.lib.kodi.library_autoupdate import show_excluded_from_auto_update
from resources.lib.kodi.library import is_in_library


def ctx_item_url(paths, mode=g.MODE_ACTION):
    """Return a function that builds an URL from a videoid
    for the predefined path"""
    def ctx_url_builder(videoid):
        """Build a context menu item URL"""
        return common.build_url(paths, videoid, mode=mode)
    return ctx_url_builder


CONTEXT_MENU_ACTIONS = {
    'export': {
        'label': common.get_local_string(30018),
        'url': ctx_item_url(['export'], g.MODE_LIBRARY)},
    'remove': {
        'label': common.get_local_string(30030),
        'url': ctx_item_url(['remove'], g.MODE_LIBRARY)},
    'update': {
        'label': common.get_local_string(30061),
        'url': ctx_item_url(['update'], g.MODE_LIBRARY)},
    'export_new_episodes': {
        'label': common.get_local_string(30195),
        'url': ctx_item_url(['export_new_episodes'], g.MODE_LIBRARY)},
    'exclude_from_auto_update': {
        'label': common.get_local_string(30196),
        'url': ctx_item_url(['exclude_from_auto_update'], g.MODE_LIBRARY)},
    'include_in_auto_update': {
        'label': common.get_local_string(30197),
        'url': ctx_item_url(['include_in_auto_update'], g.MODE_LIBRARY)},
    'rate': {
        'label': common.get_local_string(30019),
        'url': ctx_item_url(['rate'])},
    'rate_thumb': {
        'label': common.get_local_string(30019),
        'url': ctx_item_url(['rate_thumb'])},
    'add_to_list': {
        'label': common.get_local_string(30021),
        'url': ctx_item_url(['my_list', 'add'])},
    'remove_from_list': {
        'label': common.get_local_string(30020),
        'url': ctx_item_url(['my_list', 'remove'])},
    'trailer': {
        'label': common.get_local_string(30179),
        'url': ctx_item_url(['trailer'])},
    'force_update_mylist': {
        'label': common.get_local_string(30214),
        'url': ctx_item_url(['force_update_mylist'])}
}


def generate_context_menu_mainmenu(menu_id):
    """Generate context menu items for a listitem"""
    items = []

    if menu_id == 'myList':
        items.append(_ctx_item('force_update_mylist', None))

    return items


def generate_context_menu_items(videoid):
    """Generate context menu items for a listitem"""
    items = _generate_library_ctx_items(videoid)

    # Old rating system
    # if videoid.mediatype != common.VideoId.SEASON and \
    #    videoid.mediatype != common.VideoId.SUPPLEMENTAL:
    #     items.insert(0, _ctx_item('rate', videoid))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        items.insert(0, _ctx_item('rate_thumb', videoid))

    if videoid.mediatype != common.VideoId.SUPPLEMENTAL and \
            videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        items.insert(0, _ctx_item('trailer', videoid))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        list_action = ('remove_from_list'
                       if videoid in api.mylist_items()
                       else 'add_to_list')
        items.insert(0, _ctx_item(list_action, videoid))

    return items


def _generate_library_ctx_items(videoid):
    library_actions = []
    # Do not allow operations for supplemental (trailers etc) and single episodes
    if videoid.mediatype in [common.VideoId.SUPPLEMENTAL, common.VideoId.EPISODE]:
        return library_actions

    allow_lib_operations = True
    lib_is_sync_with_mylist = g.ADDON.getSettingBool('lib_sync_mylist') and \
        g.ADDON.getSettingInt('lib_auto_upd_mode') != 0

    if lib_is_sync_with_mylist:
        # If the synchronization of Netflix "My List" with the Kodi library is enabled
        # only in the chosen profile allow to do operations in the Kodi library otherwise
        # it creates inconsistency to the exported elements and increases the work for sync
        sync_mylist_profile_guid = g.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         g.LOCAL_DB.get_guid_owner_profile())
        allow_lib_operations = sync_mylist_profile_guid == g.LOCAL_DB.get_active_profile_guid()

    if allow_lib_operations:
        _is_in_library = is_in_library(videoid)
        if lib_is_sync_with_mylist:
            if _is_in_library:
                library_actions = ['update']
        else:
            library_actions = ['remove', 'update'] if _is_in_library else ['export']

        if videoid.mediatype == common.VideoId.SHOW and _is_in_library:
            library_actions.append('export_new_episodes')
            if show_excluded_from_auto_update(videoid):
                library_actions.append('include_in_auto_update')
            else:
                library_actions.append('exclude_from_auto_update')

    return [_ctx_item(action, videoid) for action in library_actions]


def _ctx_item(template, videoid):
    """Create a context menu item based on the given template and videoid"""
    return (CONTEXT_MENU_ACTIONS[template]['label'],
            common.run_plugin_action(
                CONTEXT_MENU_ACTIONS[template]['url'](videoid)))
