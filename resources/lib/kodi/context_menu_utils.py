# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for generating context menu items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
from resources.lib.globals import G


# Normally it wouldn't be necessary to split a module so small into two files,
# unfortunately use 'get_local_string' on a variable in the module header, makes that method (get_local_string)
# run immediately upon loading of the add-on modules, making it impossible to load the service instance.
# Separating the process of the loading of local strings would cause a huge slowdown in the processing of video lists.


def ctx_item_url(paths, mode=G.MODE_ACTION):
    """Return a function that builds an URL from a videoid for the predefined path"""
    def ctx_url_builder(videoid, params):
        """Build a context menu item URL"""
        return common.build_url(paths, videoid, params, mode=mode)
    return ctx_url_builder


CONTEXT_MENU_ACTIONS = {
    'export': {
        'label': common.get_local_string(30018),
        'url': ctx_item_url(['export'], G.MODE_LIBRARY)},
    'remove': {
        'label': common.get_local_string(30030),
        'url': ctx_item_url(['remove'], G.MODE_LIBRARY)},
    'update': {
        'label': common.get_local_string(30061),
        'url': ctx_item_url(['update'], G.MODE_LIBRARY)},
    'export_new_episodes': {
        'label': common.get_local_string(30195),
        'url': ctx_item_url(['export_new_episodes'], G.MODE_LIBRARY)},
    'exclude_from_auto_update': {
        'label': common.get_local_string(30196),
        'url': ctx_item_url(['exclude_from_auto_update'], G.MODE_LIBRARY)},
    'include_in_auto_update': {
        'label': common.get_local_string(30197),
        'url': ctx_item_url(['include_in_auto_update'], G.MODE_LIBRARY)},
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
    'force_update_list': {
        'label': common.get_local_string(30214),
        'url': ctx_item_url(['force_update_list'])},
    'change_watched_status': {
        'label': common.get_local_string(30236),
        'url': ctx_item_url(['change_watched_status'])},
    'search_remove': {
        'label': common.get_local_string(15015),
        'url': ctx_item_url(['search', 'search', 'remove'], G.MODE_DIRECTORY)},
    'search_edit': {
        'label': common.get_local_string(21450),
        'url': ctx_item_url(['search', 'search', 'edit'], G.MODE_DIRECTORY)},
    'remove_watched_status': {
        'label': common.get_local_string(15015),
        'url': ctx_item_url(['remove_watched_status'])},
    'autoselect_set_profile': {
        'label': common.get_local_string(30055),
        'url': ctx_item_url(['autoselect_set_profile'])},
    'autoselect_remove_profile': {
        'label': common.get_local_string(30056),
        'url': ctx_item_url(['autoselect_remove_profile'])},
    'library_playback_set_profile': {
        'label': common.get_local_string(30052),
        'url': ctx_item_url(['library_playback_set_profile'])},
    'library_playback_remove_profile': {
        'label': common.get_local_string(30053),
        'url': ctx_item_url(['library_playback_remove_profile'])},
    'profile_parental_control': {
        'label': common.get_local_string(30062),
        'url': ctx_item_url(['parental_control'])},
    'add_remind_me': {
        'label': common.get_local_string(30622),
        'url': ctx_item_url(['remind_me', 'add'])},
    'remove_remind_me': {
        'label': common.get_local_string(30623),
        'url': ctx_item_url(['remind_me', 'remove'])}
}
