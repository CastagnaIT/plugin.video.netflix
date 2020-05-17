# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for generating context menu items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
from resources.lib.globals import g


# Normally it wouldn't be necessary to split a module so small into two files,
# unfortunately use 'get_local_string' on a variable in the module header, makes that method (get_local_string)
# run immediately upon loading of the add-on modules, making it impossible to load the service instance.
# Separating the process of the loading of local strings would cause a huge slowdown in the processing of video lists.


def ctx_item_url(paths, mode=g.MODE_ACTION):
    """Return a function that builds an URL from a videoid for the predefined path"""
    def ctx_url_builder(videoid, params):
        """Build a context menu item URL"""
        return common.build_url(paths, videoid, params, mode=mode)
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
    'force_update_list': {
        'label': common.get_local_string(30214),
        'url': ctx_item_url(['force_update_list'])},
    'change_watched_status': {
        'label': common.get_local_string(30236),
        'url': ctx_item_url(['change_watched_status'])}
}
