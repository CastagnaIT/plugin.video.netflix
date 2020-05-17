# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for directory builder

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os

import resources.lib.common as common
from resources.lib.globals import g

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


def _get_custom_thumb_path(thumb_file_name):
    return os.path.join(g.ADDON_DATA_PATH, 'resources', 'media', thumb_file_name)


def add_items_previous_next_page(directory_items, pathitems, perpetual_range_selector, sub_genre_id=None):
    if pathitems and perpetual_range_selector:
        if 'previous_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('previous_start'),
                      'genre_id': sub_genre_id if perpetual_range_selector.get('previous_start') == 0 else None}
            # todo: change params to sub_genre_id
            previous_page_item = {
                'url': common.build_url(pathitems=pathitems, params=params, mode=g.MODE_DIRECTORY),
                'label': common.get_local_string(30148),
                'art': {'thumb': _get_custom_thumb_path('FolderPagePrevious.png')},
                'is_folder': True
            }
            directory_items.insert(0, previous_page_item)
        if 'next_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('next_start')}
            next_page_item = {
                'url': common.build_url(pathitems=pathitems, params=params, mode=g.MODE_DIRECTORY),
                'label': common.get_local_string(30147),
                'art': {'thumb': _get_custom_thumb_path('FolderPageNext.png')},
                'is_folder': True
            }
            directory_items.append(next_page_item)


def get_param_watched_status_by_profile():
    """
    Get a value used as parameter in the ListItem (of videos),
    in order to differentiate the watched status and other Kodi data by profiles
    :return: a dictionary to be add to 'build_url' params
    """
    return {'profile_guid': g.LOCAL_DB.get_active_profile_guid()}
