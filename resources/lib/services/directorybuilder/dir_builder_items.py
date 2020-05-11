# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Generate the data to build a directory of xbmcgui ListItem's

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from future.utils import iteritems

import resources.lib.common as common
from resources.lib.database.db_utils import (TABLE_MENU_DATA)
from resources.lib.globals import g
from resources.lib.kodi.context_menu import generate_context_menu_items
from resources.lib.kodi.infolabels import get_art, get_color_name, add_info_dict_item, set_watched_status
from resources.lib.services.directorybuilder.dir_builder_utils import (get_param_watched_status_by_profile,
                                                                       add_items_previous_next_page)

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

# This module convert a DataType object like VideoListSorted (that contains a list of items videos, items, etc)
# in a list of dict items very similar to xbmcgui.ListItem, that the client-frontend will convert into real ListItem's
# (because currently the xbmcgui.ListItem object is not serializable)
# The dict keys are managed from the method '_convert_list' of listings.py

# All build methods should return same tuple data ('directory items', 'extra data dict')
# common_data dict is used to avoid cpu overload in consecutive accesses to other resources improve a lot the execution


@common.time_execution(immediate=True)
def build_mainmenu_listing(lolomo_list):
    """Builds the main menu listing (my list, continue watching, etc.)"""
    from resources.lib.kodi.context_menu import generate_context_menu_mainmenu
    directory_items = []
    common_data = {
        'profile_language_code': g.LOCAL_DB.get_profile_config('language', ''),
        'supplemental_info_color': get_color_name(g.ADDON.getSettingInt('supplemental_info_color'))
    }
    for menu_id, data in iteritems(g.MAIN_MENU_ITEMS):
        if not g.ADDON.getSettingBool('_'.join(('show_menu', menu_id))):
            continue
        if data['lolomo_known']:
            list_id, video_list = lolomo_list.find_by_context(data['lolomo_contexts'][0])
            if not list_id:
                continue
            menu_title = video_list['displayName']
            dict_item = _create_videolist_item(list_id, video_list, data, common_data, static_lists=True)
        else:
            menu_title = common.get_local_string(data['label_id']) if data.get('label_id') else 'Missing menu title'
            menu_description = (common.get_local_string(data['description_id'])
                                if data['description_id'] is not None
                                else '')
            dict_item = {
                'url': common.build_url(data['path'], mode=g.MODE_DIRECTORY),
                'label': menu_title,
                'art': {'icon': data['icon']},
                'info': {'plot': menu_description},  # The description
                'is_folder': True
            }
        dict_item['menu_items'] = generate_context_menu_mainmenu(menu_id)
        directory_items.append(dict_item)
        # Save the menu titles, to reuse it when will be open the content of menus
        g.LOCAL_DB.set_value(menu_id, {'title': menu_title}, TABLE_MENU_DATA)
    return directory_items, {}


def build_profiles_listing():
    """Builds the profiles listing"""
    directory_items = []
    active_guid_profile = g.LOCAL_DB.get_active_profile_guid()
    for guid in g.LOCAL_DB.get_guid_profiles():
        directory_items.append(_create_profile_item(guid, (guid == active_guid_profile)))
    return directory_items, {}


def _create_profile_item(profile_guid, is_active):
    profile_name = g.LOCAL_DB.get_profile_config('profileName', '???', guid=profile_guid)

    profile_attributes = []
    if g.LOCAL_DB.get_profile_config('isPinLocked', False, guid=profile_guid):
        profile_attributes.append('[COLOR red]' + common.get_local_string(20068) + '[/COLOR]')
    if g.LOCAL_DB.get_profile_config('isAccountOwner', False, guid=profile_guid):
        profile_attributes.append(common.get_local_string(30221))
    if g.LOCAL_DB.get_profile_config('isKids', False, guid=profile_guid):
        profile_attributes.append(common.get_local_string(30222))
    attributes_desc = '[CR]'.join(profile_attributes) + '[CR]' if profile_attributes else ''
    description = attributes_desc + '[' + g.LOCAL_DB.get_profile_config('language_desc', '', guid=profile_guid) + ']'

    menu_action = common.run_plugin_action(common.build_url(pathitems=['autoselect_profile_set'],
                                                            params={'profile_name': profile_name.encode('utf-8'),
                                                                    'profile_guid': profile_guid},
                                                            mode=g.MODE_ACTION))
    dict_item = {
        'label': profile_name,
        'properties': {'nf_guid': profile_guid, 'nf_description': description.replace('[CR]', ' - ')},
        'art': {'icon': g.LOCAL_DB.get_profile_config('avatar', '', guid=profile_guid)},
        'info': {'plot': description},  # The description
        'is_selected': is_active,
        'menu_items': [(common.get_local_string(30056), menu_action)],
        'url': common.build_url(pathitems=['home'],
                                params={'switch_profile_guid': profile_guid},
                                mode=g.MODE_DIRECTORY),
        'is_folder': True
    }
    return dict_item


@common.time_execution(immediate=True)
def build_season_listing(season_list, tvshowid, pathitems=None):
    """Build a season listing"""
    common_data = {
        'supplemental_info_color': get_color_name(g.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': g.LOCAL_DB.get_profile_config('language', '')
    }
    directory_items = [_create_season_item(tvshowid, seasonid_value, season, season_list, common_data)
                       for seasonid_value, season
                       in iteritems(season_list.seasons)]
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, season_list.perpetual_range_selector, tvshowid)
    return directory_items, {'title': season_list.tvshow['title'] + ' - ' + common.get_local_string(20366)[2:]}


def _create_season_item(tvshowid, seasonid_value, season, season_list, common_data):
    seasonid = tvshowid.derive_season(seasonid_value)
    dict_item = {
        'video_id': seasonid_value,
        'media_type': seasonid.mediatype,
        'label': season['summary']['name'],
        'is_folder': True
    }
    add_info_dict_item(dict_item, seasonid, season, season_list.data, False, common_data)
    dict_item['art'] = get_art(tvshowid, season, common_data['profile_language_code'])
    dict_item['url'] = common.build_url(videoid=seasonid, mode=g.MODE_DIRECTORY)
    dict_item['menu_items'] = generate_context_menu_items(seasonid, False, None)
    return dict_item


@common.time_execution(immediate=True)
def build_episode_listing(episodes_list, seasonid, pathitems=None):
    """Build a episodes listing of a season"""
    common_data = {
        'params': get_param_watched_status_by_profile(),
        'set_watched_status': g.ADDON.getSettingBool('ProgressManager_enabled'),
        'supplemental_info_color': get_color_name(g.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': g.LOCAL_DB.get_profile_config('language', '')
    }
    directory_items = [_create_episode_item(seasonid, episodeid_value, episode, episodes_list, common_data)
                       for episodeid_value, episode
                       in iteritems(episodes_list.episodes)]
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, episodes_list.perpetual_range_selector)
    return directory_items, {'title': episodes_list.tvshow['title'] + ' - ' + episodes_list.season['summary']['name']}


def _create_episode_item(seasonid, episodeid_value, episode, episodes_list, common_data):
    episodeid = seasonid.derive_episode(episodeid_value)
    dict_item = {'video_id': episodeid_value,
                 'media_type': episodeid.mediatype,
                 'label': episode['title'],
                 'is_folder': False}
    add_info_dict_item(dict_item, episodeid, episode, episodes_list.data, False, common_data)
    set_watched_status(dict_item, episode, common_data)
    dict_item['art'] = get_art(episodeid, episode, common_data['profile_language_code'])
    dict_item['url'] = common.build_url(videoid=episodeid, mode=g.MODE_PLAY, params=common_data['params'])
    dict_item['menu_items'] = generate_context_menu_items(episodeid, False, None)
    return dict_item


@common.time_execution(immediate=True)
def build_lolomo_listing(lolomo_list, menu_data, force_use_videolist_id=False, exclude_lolomo_known=False):
    """Build a listing of video lists (LoLoMo)"""
    # If contexts are specified (lolomo_contexts in the menu_data), then the lolomo_list data will be filtered by
    # the specified contexts, otherwise all LoLoMo items will be added
    common_data = {
        'menu_data': menu_data,
        'supplemental_info_color': get_color_name(g.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': g.LOCAL_DB.get_profile_config('language', '')
    }
    contexts = menu_data.get('lolomo_contexts')
    items_list = lolomo_list.lists_by_context(contexts) if contexts else iteritems(lolomo_list.lists)
    directory_items = []
    for video_list_id, video_list in items_list:
        menu_parameters = common.MenuIdParameters(video_list_id)
        if not menu_parameters.is_menu_id:
            continue
        if exclude_lolomo_known and menu_parameters.type_id != '28':
            # Keep only the menus genre
            continue
        list_id = (menu_parameters.context_id
                   if menu_parameters.context_id and not force_use_videolist_id
                   else video_list_id)
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], list_id, list_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
        sub_menu_data['force_use_videolist_id'] = force_use_videolist_id
        sub_menu_data['title'] = video_list['displayName']
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        g.LOCAL_DB.set_value(list_id, sub_menu_data, TABLE_MENU_DATA)

        directory_items.append(_create_videolist_item(list_id, video_list, sub_menu_data, common_data))
    return directory_items, {}


def _create_videolist_item(list_id, video_list, menu_data, common_data, static_lists=False):
    if static_lists and g.is_known_menu_context(video_list['context']):
        pathitems = menu_data['path']
        pathitems.append(video_list['context'])
    else:
        # It is a dynamic video list / menu context
        if menu_data.get('force_use_videolist_id', False):
            path = 'video_list'
        else:
            path = 'video_list_sorted'
        pathitems = [path, menu_data['path'][1], list_id]
    dict_item = {'label': video_list['displayName'],
                 'is_folder': True}
    add_info_dict_item(dict_item, video_list.id, video_list, video_list.data, False, common_data)
    dict_item['art'] = get_art(video_list.id, video_list.artitem, common_data['profile_language_code'])
    dict_item['url'] = common.build_url(pathitems,
                                        # genre_id add possibility to browse the sub-genres (see build_video_listing)
                                        params={'genre_id': unicode(video_list.get('genreId'))},
                                        mode=g.MODE_DIRECTORY)
    return dict_item


@common.time_execution(immediate=True)
def build_video_listing(video_list, menu_data, sub_genre_id=None, pathitems=None, perpetual_range_start=None,
                        mylist_items=None):
    """Build a video listing"""
    common_data = {
        'params': get_param_watched_status_by_profile(),
        'mylist_items': mylist_items,
        'set_watched_status': g.ADDON.getSettingBool('ProgressManager_enabled'),
        'supplemental_info_color': get_color_name(g.ADDON.getSettingInt('supplemental_info_color')),
        'mylist_titles_color': (get_color_name(g.ADDON.getSettingInt('mylist_titles_color'))
                                if menu_data['path'][1] != 'myList'
                                else None),
        'profile_language_code': g.LOCAL_DB.get_profile_config('language', '')
    }
    directory_items = [_create_video_item(videoid_value, video, video_list, perpetual_range_start, common_data)
                       for videoid_value, video
                       in iteritems(video_list.videos)]
    # If genre_id exists add possibility to browse LoLoMo sub-genres
    if sub_genre_id and sub_genre_id != 'None':
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        menu_id = 'subgenre_' + sub_genre_id
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], menu_id, sub_genre_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
        sub_menu_data.update({'title': common.get_local_string(30089)})
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        g.LOCAL_DB.set_value(menu_id, sub_menu_data, TABLE_MENU_DATA)
        # Create the folder for the access to sub-genre
        folder_dict_item = {
            'url': common.build_url(['genres', menu_id, sub_genre_id], mode=g.MODE_DIRECTORY),
            'label': common.get_local_string(30089),
            'art': {'icon': 'DefaultVideoPlaylists.png'},
            'info': {'plot': common.get_local_string(30088)},  # The description
            'is_folder': True
        }
        directory_items.insert(0, folder_dict_item)
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, video_list.perpetual_range_selector, sub_genre_id)
    return directory_items, {}


def _create_video_item(videoid_value, video, video_list, perpetual_range_start, common_data):
    videoid = common.VideoId.from_videolist_item(video)
    is_folder = videoid.mediatype == common.VideoId.SHOW
    is_in_mylist = videoid in common_data['mylist_items']
    dict_item = {'video_id': videoid_value,
                 'media_type': videoid.mediatype,
                 'label': video['title'],
                 'is_folder': is_folder}
    add_info_dict_item(dict_item, videoid, video, video_list.data, is_in_mylist, common_data)
    set_watched_status(dict_item, video, common_data)
    dict_item['art'] = get_art(videoid, video, common_data['profile_language_code'])
    dict_item['url'] = common.build_url(videoid=videoid,
                                        mode=g.MODE_DIRECTORY if is_folder else g.MODE_PLAY,
                                        params=common_data['params'])
    dict_item['menu_items'] = generate_context_menu_items(videoid, is_in_mylist, perpetual_range_start)
    return dict_item


@common.time_execution(immediate=True)
def build_subgenres_listing(subgenre_list, menu_data):
    """Build a listing of sub-genres list"""
    directory_items = []
    for index, subgenre_data in subgenre_list.lists:  # pylint: disable=unused-variable
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        sel_video_list_id = unicode(subgenre_data['id'])
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
        sub_menu_data['title'] = subgenre_data['name']
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        g.LOCAL_DB.set_value(sel_video_list_id, sub_menu_data, TABLE_MENU_DATA)
        directory_items.append(_create_subgenre_item(sel_video_list_id,
                                                     subgenre_data,
                                                     sub_menu_data))
    return directory_items, {}


def _create_subgenre_item(video_list_id, subgenre_data, menu_data):
    pathitems = ['video_list_sorted', menu_data['path'][1], video_list_id]
    dict_item = {
        'url': common.build_url(pathitems, mode=g.MODE_DIRECTORY),
        'is_folder': True,
        'label': subgenre_data['name']
    }
    return dict_item
