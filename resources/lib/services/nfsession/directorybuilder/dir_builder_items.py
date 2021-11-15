# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Generate the data to build a directory of xbmcgui ListItem's

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
from resources.lib.common.cache_utils import CACHE_BOOKMARKS
from resources.lib.common.exceptions import CacheMiss
from resources.lib.common.kodi_wrappers import ListItemW
from resources.lib.database.db_utils import (TABLE_MENU_DATA)
from resources.lib.globals import G
from resources.lib.kodi.context_menu import (generate_context_menu_items, generate_context_menu_profile,
                                             generate_context_menu_remind_me)
from resources.lib.kodi.infolabels import get_color_name, set_watched_status, add_info_list_item
from resources.lib.services.nfsession.directorybuilder.dir_builder_utils import (get_param_watched_status_by_profile,
                                                                                 add_items_previous_next_page,
                                                                                 get_availability_message)
from resources.lib.utils.logging import measure_exec_time_decorator


# This module convert a DataType object like VideoListSorted (that contains a list of items videos, items, etc)
#   in a list of ListItemW items (a wrapper of the real xbmcgui.ListItem).

# All build methods should return same tuple data ('directory items', 'extra data dict'),
#  all the 'directory_items' variables stand for the items to put in to xbmcplugin.addDirectoryItems
# 'common_data' dict is used to avoid cpu overload for multiple accesses to other resources improve a lot the execution


@measure_exec_time_decorator(is_immediate=True)
def build_mainmenu_listing(loco_list):
    """Builds the main menu listing (my list, continue watching, etc.)"""
    from resources.lib.kodi.context_menu import generate_context_menu_mainmenu
    directory_items = []
    common_data = {
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', ''),
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color'))
    }
    for menu_id, data in G.MAIN_MENU_ITEMS.items():
        if data.get('has_show_setting', True) and not G.ADDON.getSettingBool('_'.join(('show_menu', menu_id))):
            continue
        if data['loco_known']:
            list_id, video_list = loco_list.find_by_context(data['loco_contexts'][0])
            if not list_id:
                continue
            menu_title = video_list['displayName']
            directory_item = _create_videolist_item(list_id, video_list, data, common_data, static_lists=True)
            directory_item[1].addContextMenuItems(generate_context_menu_mainmenu(menu_id))
            directory_items.append(directory_item)
        else:
            menu_title = common.get_local_string(data['label_id']) if data.get('label_id') else 'Missing menu title'
            menu_description = (common.get_local_string(data['description_id'])
                                if data['description_id'] is not None
                                else '')
            list_item = ListItemW(label=menu_title)
            list_item.setArt({'icon': data['icon']})
            list_item.setInfo('video', {'plot': menu_description})
            list_item.addContextMenuItems(generate_context_menu_mainmenu(menu_id))
            directory_items.append((common.build_url(data['path'], mode=G.MODE_DIRECTORY), list_item, True))
        # Save the menu titles, to reuse it when will be open the content of menus
        G.LOCAL_DB.set_value(menu_id, {'title': menu_title}, TABLE_MENU_DATA)
    # Add "Profiles" menu
    pfl_list_item = ListItemW(label=common.get_local_string(13200))
    pfl_list_item.setArt({'icon': 'DefaultUser.png'})
    directory_items.append((common.build_url(['profiles'], mode=G.MODE_DIRECTORY), pfl_list_item, True))
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {}


def build_profiles_listing(preselect_guid=None, detailed_info=True):
    """Builds the profiles listing"""
    directory_items = []
    preselect_guid = preselect_guid or G.LOCAL_DB.get_active_profile_guid()
    autoselect_guid = G.LOCAL_DB.get_value('autoselect_profile_guid')
    library_playback_guid = G.LOCAL_DB.get_value('library_playback_profile_guid')
    for guid in G.LOCAL_DB.get_guid_profiles():
        directory_items.append(_create_profile_item(guid,
                                                    (guid == preselect_guid),
                                                    (guid == autoselect_guid),
                                                    (guid == library_playback_guid),
                                                    detailed_info))
    return directory_items, {}


def _create_profile_item(profile_guid, is_selected, is_autoselect, is_library_playback, detailed_info):
    profile_name = G.LOCAL_DB.get_profile_config('profileName', '???', guid=profile_guid)
    profile_attributes = []
    if G.LOCAL_DB.get_profile_config('isPinLocked', False, guid=profile_guid):
        profile_attributes.append(f'[COLOR red]{common.get_local_string(20068)}[/COLOR]')
    if G.LOCAL_DB.get_profile_config('isAccountOwner', False, guid=profile_guid):
        profile_attributes.append(common.get_local_string(30221))
    if G.LOCAL_DB.get_profile_config('isKids', False, guid=profile_guid):
        profile_attributes.append(common.get_local_string(30222))
    if is_autoselect and detailed_info:
        profile_attributes.append(common.get_local_string(30054))
    if is_library_playback and detailed_info:
        profile_attributes.append(common.get_local_string(30051))
    attributes_desc = '[CR]'.join(profile_attributes) + '[CR]' if profile_attributes else ''
    description = f'{attributes_desc}[{G.LOCAL_DB.get_profile_config("language_desc", "", guid=profile_guid)}]'

    if detailed_info:
        menu_items = generate_context_menu_profile(profile_guid, is_autoselect, is_library_playback)
    else:
        menu_items = []
    list_item = ListItemW(label=profile_name)
    list_item.setProperties({
        'nf_guid': profile_guid,
        'nf_description': description.replace('[CR]', ' - ')
    })
    list_item.setArt({'icon': G.LOCAL_DB.get_profile_config('avatar', '', guid=profile_guid)})
    list_item.setInfo('video', {'plot': description})
    list_item.select(is_selected)
    list_item.addContextMenuItems(menu_items)
    return (common.build_url(pathitems=['home'], params={'switch_profile_guid': profile_guid}, mode=G.MODE_DIRECTORY),
            list_item,
            True)


@measure_exec_time_decorator(is_immediate=True)
def build_season_listing(season_list, tvshowid, pathitems=None):
    """Build a season listing"""
    common_data = {
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', '')
    }
    directory_items = [_create_season_item(tvshowid, seasonid_value, season, season_list, common_data)
                       for seasonid_value, season in season_list.seasons.items()]
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, season_list.perpetual_range_selector, tvshowid)
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {'title': f'{season_list.tvshow["title"]} - {common.get_local_string(20366)[2:]}'}


def _create_season_item(tvshowid, seasonid_value, season, season_list, common_data):
    seasonid = tvshowid.derive_season(seasonid_value)
    list_item = ListItemW(label=season['summary']['name'])
    list_item.setProperty('nf_videoid', seasonid.to_string())
    add_info_list_item(list_item, seasonid, season, season_list.data, False, common_data,
                       art_item=season_list.artitem)
    list_item.addContextMenuItems(generate_context_menu_items(seasonid, False, None))
    return common.build_url(videoid=seasonid, mode=G.MODE_DIRECTORY), list_item, True


@measure_exec_time_decorator(is_immediate=True)
def build_episode_listing(episodes_list, seasonid, pathitems=None):
    """Build a episodes listing of a season"""
    common_data = {
        'params': get_param_watched_status_by_profile(),
        'set_watched_status': G.ADDON.getSettingBool('sync_watched_status'),
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', ''),
        'active_profile_guid': G.LOCAL_DB.get_active_profile_guid()
    }
    directory_items = [_create_episode_item(seasonid, episodeid_value, episode, episodes_list, common_data)
                       for episodeid_value, episode
                       in episodes_list.episodes.items()]
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, episodes_list.perpetual_range_selector)
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {'title': f'{episodes_list.tvshow["title"]} - {episodes_list.season["summary"]["name"]}'}


def _create_episode_item(seasonid, episodeid_value, episode, episodes_list, common_data):
    is_playable = episode['summary']['isPlayable']
    episodeid = seasonid.derive_episode(episodeid_value)
    list_item = ListItemW(label=episode['title'])
    list_item.setProperties({
        'isPlayable': str(is_playable).lower(),
        'nf_videoid': episodeid.to_string()
    })
    add_info_list_item(list_item, episodeid, episode, episodes_list.data, False, common_data)
    set_watched_status(list_item, episode, common_data)
    if is_playable:
        url = common.build_url(videoid=episodeid, mode=G.MODE_PLAY, params=common_data['params'])
        list_item.addContextMenuItems(generate_context_menu_items(episodeid, False, None))
    else:
        # The video is not playable, try check if there is a date
        list_item.setProperty('nf_availability_message', get_availability_message(episode))
        url = common.build_url(['show_availability_message'], videoid=episodeid, mode=G.MODE_ACTION)
    return url, list_item, False


@measure_exec_time_decorator(is_immediate=True)
def build_loco_listing(loco_list, menu_data, force_use_videolist_id=False, exclude_loco_known=False):
    """Build a listing of video lists (LoCo)"""
    # If contexts are specified (loco_contexts in the menu_data), then the loco_list data will be filtered by
    # the specified contexts, otherwise all LoCo items will be added
    common_data = {
        'menu_data': menu_data,
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color')),
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', '')
    }
    contexts = menu_data.get('loco_contexts')
    items_list = loco_list.lists_by_context(contexts) if contexts else loco_list.lists.items()
    directory_items = []
    for video_list_id, video_list in items_list:
        menu_parameters = common.MenuIdParameters(video_list_id)
        if not menu_parameters.is_menu_id:
            continue
        list_id = (menu_parameters.context_id
                   if menu_parameters.context_id and not force_use_videolist_id
                   else video_list_id)
        # Keep only some type of menus: 28=genre, 101=top 10
        if exclude_loco_known:
            if menu_parameters.type_id not in ['28', '101']:
                continue
            if menu_parameters.type_id == '101':
                # Top 10 list can be obtained only with 'video_list' query
                force_use_videolist_id = True
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], list_id, list_id]
        sub_menu_data['loco_known'] = False
        sub_menu_data['loco_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', G.CONTENT_SHOW)
        sub_menu_data['force_use_videolist_id'] = force_use_videolist_id
        sub_menu_data['title'] = video_list['displayName']
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        sub_menu_data['no_use_cache'] = menu_parameters.type_id == '101'
        G.LOCAL_DB.set_value(list_id, sub_menu_data, TABLE_MENU_DATA)

        directory_items.append(_create_videolist_item(list_id, video_list, sub_menu_data, common_data))
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {}


def _create_videolist_item(list_id, video_list, menu_data, common_data, static_lists=False):
    if static_lists and G.is_known_menu_context(video_list['context']):
        pathitems = list(menu_data['path'])  # Make a copy
        pathitems.append(video_list['context'])
    else:
        # It is a dynamic video list / menu context
        if menu_data.get('force_use_videolist_id', False):
            path = 'video_list'
        else:
            path = 'video_list_sorted'
        pathitems = [path, menu_data['path'][1], list_id]
    list_item = ListItemW(label=video_list['displayName'])
    add_info_list_item(list_item, video_list.videoid, video_list, video_list.data, False, common_data,
                       art_item=video_list.artitem)
    # Add possibility to browse the sub-genres (see build_video_listing)
    sub_genre_id = video_list.get('genreId')
    params = {'sub_genre_id': str(sub_genre_id)} if sub_genre_id else None
    return common.build_url(pathitems, params=params, mode=G.MODE_DIRECTORY), list_item, True


@measure_exec_time_decorator(is_immediate=True)
def build_video_listing(video_list, menu_data, sub_genre_id=None, pathitems=None, perpetual_range_start=None,
                        mylist_items=None, path_params=None):
    """Build a video listing"""
    common_data = {
        'params': get_param_watched_status_by_profile(),
        'mylist_items': mylist_items,
        'set_watched_status': G.ADDON.getSettingBool('sync_watched_status'),
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color')),
        'mylist_titles_color': (get_color_name(G.ADDON.getSettingInt('mylist_titles_color'))
                                if menu_data['path'][1] != 'myList'
                                else None),
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', ''),
        'ctxmenu_remove_watched_status': menu_data['path'][1] == 'continueWatching',
        'active_profile_guid': G.LOCAL_DB.get_active_profile_guid()
    }
    directory_items = [_create_video_item(videoid_value, video, video_list, perpetual_range_start, common_data)
                       for videoid_value, video
                       in video_list.videos.items()]
    # If genre_id exists add possibility to browse LoCo sub-genres
    if sub_genre_id and sub_genre_id != 'None':
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        menu_id = f'subgenre_{sub_genre_id}'
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], menu_id, sub_genre_id]
        sub_menu_data['loco_known'] = False
        sub_menu_data['loco_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', G.CONTENT_SHOW)
        sub_menu_data.update({'title': common.get_local_string(30089)})
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        G.LOCAL_DB.set_value(menu_id, sub_menu_data, TABLE_MENU_DATA)
        # Create the folder for the access to sub-genre
        folder_list_item = ListItemW(label=common.get_local_string(30089))
        folder_list_item.setArt({'icon': 'DefaultVideoPlaylists.png'})
        folder_list_item.setInfo('video', {'plot': common.get_local_string(30088)})  # The description
        directory_items.insert(0, (common.build_url(['genres', menu_id, sub_genre_id], mode=G.MODE_DIRECTORY),
                                   folder_list_item,
                                   True))
    # add_items_previous_next_page use the new value of perpetual_range_selector
    add_items_previous_next_page(directory_items, pathitems, video_list.perpetual_range_selector, sub_genre_id,
                                 path_params)
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {}


def _create_video_item(videoid_value, video, video_list, perpetual_range_start, common_data):  # pylint: disable=unused-argument
    videoid = common.VideoId.from_videolist_item(video)
    is_folder = videoid.mediatype == common.VideoId.SHOW
    is_playable = video['availability']['isPlayable']
    is_video_playable = not is_folder and is_playable
    is_in_mylist = videoid in common_data['mylist_items']
    list_item = ListItemW(label=video['title'])
    list_item.setProperties({
        'isPlayable': str(is_video_playable).lower(),
        'nf_videoid': videoid.to_string(),
        'nf_is_in_mylist': str(is_in_mylist),
        'nf_perpetual_range_start': str(perpetual_range_start)
    })
    add_info_list_item(list_item, videoid, video, video_list.data, is_in_mylist, common_data)
    if not is_folder:
        set_watched_status(list_item, video, common_data)
    if is_playable:
        # The movie or tvshow (episodes) is playable
        url = common.build_url(videoid=videoid,
                               mode=G.MODE_DIRECTORY if is_folder else G.MODE_PLAY,
                               params=None if is_folder else common_data['params'])
        list_item.addContextMenuItems(generate_context_menu_items(videoid, is_in_mylist, perpetual_range_start,
                                                                  common_data['ctxmenu_remove_watched_status']))
    else:
        # The movie or tvshow (episodes) is not available
        # Try check if there is a availability date
        list_item.setProperty('nf_availability_message', get_availability_message(video))
        # Check if the user has set "Remind Me" feature,
        try:
            #  Due to the add-on cache we can not change in easy way the value stored in database cache,
            #  then we temporary override the value (see 'remind_me' in navigation/actions.py)
            is_in_remind_me = G.CACHE.get(CACHE_BOOKMARKS, f'is_in_remind_me_{videoid}')
        except CacheMiss:
            #  The website check the "Remind Me" value on key "inRemindMeList" and also "queue"/"inQueue"
            is_in_remind_me = video['inRemindMeList'] or video['queue']['inQueue']
        trackid = video['trackIds']['trackId_jaw']
        list_item.addContextMenuItems(generate_context_menu_remind_me(videoid, is_in_remind_me, trackid))
        url = common.build_url(['show_availability_message'], videoid=videoid, mode=G.MODE_ACTION)
    return url, list_item, is_folder and is_playable


@measure_exec_time_decorator(is_immediate=True)
def build_subgenres_listing(subgenre_list, menu_data):
    """Build a listing of sub-genres list"""
    directory_items = []
    for index, subgenre_data in subgenre_list.lists:  # pylint: disable=unused-variable
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        sel_video_list_id = str(subgenre_data['id'])
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
        sub_menu_data['loco_known'] = False
        sub_menu_data['loco_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', G.CONTENT_SHOW)
        sub_menu_data['title'] = subgenre_data['name']
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        G.LOCAL_DB.set_value(sel_video_list_id, sub_menu_data, TABLE_MENU_DATA)
        directory_items.append(_create_subgenre_item(sel_video_list_id,
                                                     subgenre_data,
                                                     sub_menu_data))
    return directory_items, {}


def _create_subgenre_item(video_list_id, subgenre_data, menu_data):
    pathitems = ['video_list_sorted', menu_data['path'][1], video_list_id]
    list_item = ListItemW(label=subgenre_data['name'])
    return common.build_url(pathitems, mode=G.MODE_DIRECTORY), list_item, True


def build_lolomo_category_listing(lolomo_cat_list, menu_data):
    """Build a folders listing of a LoLoMo category"""
    common_data = {
        'profile_language_code': G.LOCAL_DB.get_profile_config('language', ''),
        'supplemental_info_color': get_color_name(G.ADDON.getSettingInt('supplemental_info_color'))
    }
    directory_items = []
    for list_id, summary_data, video_list in lolomo_cat_list.lists():
        if summary_data['length'] == 0:  # Do not show empty lists
            continue
        menu_parameters = common.MenuIdParameters(list_id)
        # Create dynamic sub-menu info in MAIN_MENU_ITEMS
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], list_id, list_id]
        sub_menu_data['loco_known'] = False
        sub_menu_data['loco_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', G.CONTENT_SHOW)
        sub_menu_data['title'] = summary_data['displayName']
        sub_menu_data['initial_menu_id'] = menu_data.get('initial_menu_id', menu_data['path'][1])
        sub_menu_data['no_use_cache'] = menu_parameters.type_id == '101'
        G.LOCAL_DB.set_value(list_id, sub_menu_data, TABLE_MENU_DATA)
        directory_item = _create_category_item(list_id, video_list, sub_menu_data, common_data, summary_data)
        directory_items.append(directory_item)
    G.CACHE_MANAGEMENT.execute_pending_db_ops()
    return directory_items, {}


def _create_category_item(list_id, video_list, menu_data, common_data, summary_data):
    pathitems = ['video_list', menu_data['path'][1], list_id]
    list_item = ListItemW(label=summary_data['displayName'])
    add_info_list_item(list_item, video_list.videoid, video_list, video_list.data, False, common_data,
                       art_item=video_list.artitem)
    return common.build_url(pathitems, mode=G.MODE_DIRECTORY), list_item, True
