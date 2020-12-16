# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for directory builder

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os

import resources.lib.common as common
from resources.lib.globals import G


def _get_custom_thumb_path(thumb_file_name):
    return os.path.join(G.ADDON_DATA_PATH, 'resources', 'media', thumb_file_name)


def add_items_previous_next_page(directory_items, pathitems, perpetual_range_selector, sub_genre_id=None):
    if pathitems and perpetual_range_selector:
        if 'previous_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('previous_start'),
                      'sub_genre_id': sub_genre_id if perpetual_range_selector.get('previous_start') == 0 else None}
            previous_page_item = {
                'url': common.build_url(pathitems=pathitems, params=params, mode=G.MODE_DIRECTORY),
                'label': common.get_local_string(30148),
                'art': {'thumb': _get_custom_thumb_path('FolderPagePrevious.png')},
                'is_folder': True,
                'properties': {'specialsort': 'top'}  # Force an item to stay on top (not documented in Kodi)
            }
            directory_items.insert(0, previous_page_item)
        if 'next_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('next_start')}
            next_page_item = {
                'url': common.build_url(pathitems=pathitems, params=params, mode=G.MODE_DIRECTORY),
                'label': common.get_local_string(30147),
                'art': {'thumb': _get_custom_thumb_path('FolderPageNext.png')},
                'is_folder': True,
                'properties': {'specialsort': 'bottom'}  # Force an item to stay on bottom (not documented in Kodi)
            }
            directory_items.append(next_page_item)


def get_param_watched_status_by_profile():
    """
    Get a the current profile guid, will be used as parameter in the ListItem's (of videos),
    so that Kodi database can distinguish the data (like watched status) according to each Netflix profile
    :return: a dictionary to be add to 'build_url' params
    """
    return {'profile_guid': G.LOCAL_DB.get_active_profile_guid()}


def get_availability_message(video_data):
    return (video_data.get('summary', {}).get('availabilityDateMessaging') or
            video_data.get('availability', {}).get('availabilityDate') or
            common.get_local_string(10005))  # "Not available"
