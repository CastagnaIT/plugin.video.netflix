# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions to build plugin listings for Kodi

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
from functools import wraps
from future.utils import iteritems

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.database.db_utils import (TABLE_MENU_DATA)
from resources.lib.globals import g
import resources.lib.common as common

from .infolabels import add_info, add_art
from .context_menu import generate_context_menu_items, generate_context_menu_mainmenu

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


def custom_viewmode(partial_setting_id):
    """Decorator that sets a custom viewmode if currently in
    a listing of the plugin"""
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


@custom_viewmode(g.VIEW_PROFILES)
@common.time_execution(immediate=False)
def build_profiles_listing():
    """Builds the profiles list Kodi screen"""
    try:
        from HTMLParser import HTMLParser
    except ImportError:
        from html.parser import HTMLParser
    html_parser = HTMLParser()
    directory_items = []
    active_guid_profile = g.LOCAL_DB.get_active_profile_guid()
    for guid in g.LOCAL_DB.get_guid_profiles():
        directory_items.append(_create_profile_item(guid,
                                                    (guid == active_guid_profile),
                                                    html_parser))
    # The standard kodi theme does not allow to change view type if the content is "files" type,
    # so here we use "images" type, visually better to see
    finalize_directory(directory_items, g.CONTENT_IMAGES)


def _create_profile_item(profile_guid, is_active, html_parser):
    """Create a tuple that can be added to a Kodi directory that represents
    a profile as listed in the profiles listing"""
    profile_name = g.LOCAL_DB.get_profile_config('profileName', '', guid=profile_guid)
    unescaped_profile_name = html_parser.unescape(profile_name)
    is_account_owner = g.LOCAL_DB.get_profile_config('isAccountOwner', False, guid=profile_guid)
    is_kids = g.LOCAL_DB.get_profile_config('isKids', False, guid=profile_guid)
    description = []
    if is_account_owner:
        description.append(common.get_local_string(30221))
    if is_kids:
        description.append(common.get_local_string(30222))
    enc_profile_name = profile_name.encode('utf-8')
    list_item = list_item_skeleton(
        label=unescaped_profile_name,
        icon=g.LOCAL_DB.get_profile_config('avatar', '', guid=profile_guid),
        description=', '.join(description))
    list_item.select(is_active)
    autologin_url = common.build_url(
        pathitems=['save_autologin', profile_guid],
        params={'autologin_user': enc_profile_name},
        mode=g.MODE_ACTION)
    list_item.addContextMenuItems(
        [(common.get_local_string(30053),
          'RunPlugin({})'.format(autologin_url))])
    url = common.build_url(pathitems=['home'],
                           params={'profile_id': profile_guid},
                           mode=g.MODE_DIRECTORY)
    return (url, list_item, True)


@custom_viewmode(g.VIEW_MAINMENU)
@common.time_execution(immediate=False)
def build_main_menu_listing(lolomo):
    """
    Builds the video lists (my list, continue watching, etc.) Kodi screen
    """
    directory_items = []
    for menu_id, data in iteritems(g.MAIN_MENU_ITEMS):
        if not g.ADDON.getSettingBool('_'.join(('show_menu', menu_id))):
            continue
        if data['lolomo_known']:
            context_data = lolomo.find_by_context(data['lolomo_contexts'][0])
            if not context_data:
                continue
            list_id, video_list = context_data
            menu_title = video_list['displayName']
            videolist_item = _create_videolist_item(list_id, video_list, data, static_lists=True)
        else:
            menu_title = common.get_local_string(data['label_id']) if data.get('label_id') else 'Missing menu title'
            menu_description = common.get_local_string(data['description_id']) \
                if data['description_id'] is not None else ''
            videolist_item = (common.build_url(data['path'], mode=g.MODE_DIRECTORY),
                              list_item_skeleton(menu_title,
                                                 icon=data['icon'],
                                                 description=menu_description),
                              True)
        videolist_item[1].addContextMenuItems(generate_context_menu_mainmenu(menu_id))
        directory_items.append(videolist_item)
        g.LOCAL_DB.set_value(menu_id, {'title': menu_title}, TABLE_MENU_DATA)
    finalize_directory(directory_items, g.CONTENT_FOLDER, title=common.get_local_string(30097))


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_lolomo_listing(lolomo, menu_data, force_videolistbyid=False, exclude_lolomo_known=False):
    """Build a listing of video lists (LoLoMo). Only show those
    lists with a context specified context if contexts is set."""
    contexts = menu_data['lolomo_contexts']
    lists = (lolomo.lists_by_context(contexts)
             if contexts
             else iter(list(lolomo.lists.items())))
    directory_items = []
    for video_list_id, video_list in lists:
        menu_parameters = common.MenuIdParameters(id_values=video_list_id)
        if exclude_lolomo_known:
            # Keep only the menus genre
            if menu_parameters.type_id != '28':
                continue
        if menu_parameters.is_menu_id:
            # Create a new submenu info in MAIN_MENU_ITEMS
            # for reference when 'directory' find the menu data
            sel_video_list_id = menu_parameters.context_id\
                if menu_parameters.context_id and not force_videolistbyid else video_list_id
            sub_menu_data = menu_data.copy()
            sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
            sub_menu_data['lolomo_known'] = False
            sub_menu_data['lolomo_contexts'] = None
            sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
            sub_menu_data['force_videolistbyid'] = force_videolistbyid
            sub_menu_data['main_menu'] = menu_data['main_menu']\
                if menu_data.get('main_menu') else menu_data.copy()
            sub_menu_data.update({'title': video_list['displayName']})
            g.LOCAL_DB.set_value(sel_video_list_id, sub_menu_data, TABLE_MENU_DATA)
            directory_items.append(_create_videolist_item(sel_video_list_id,
                                                          video_list,
                                                          sub_menu_data))
    parent_menu_data = g.LOCAL_DB.get_value(menu_data['path'][1],
                                            table=TABLE_MENU_DATA, data_type=dict)
    finalize_directory(directory_items, g.CONTENT_FOLDER,
                       title=parent_menu_data['title'],
                       sort_type='sort_label')
    return menu_data.get('view')


@common.time_execution(immediate=False)
def _create_videolist_item(video_list_id, video_list, menu_data, static_lists=False):
    """Create a tuple that can be added to a Kodi directory that represents
    a videolist as listed in a LoLoMo"""
    if static_lists and g.is_known_menu_context(video_list['context']):
        pathitems = menu_data['path']
        pathitems.append(video_list['context'])
    else:
        # Has a dynamic video list-menu context
        if menu_data.get('force_videolistbyid', False):
            path = 'video_list'
        else:
            path = 'video_list_sorted'
        pathitems = [path, menu_data['path'][1], video_list_id]
    list_item = list_item_skeleton(video_list['displayName'])
    add_info(video_list.id, list_item, video_list, video_list.data, handle_highlighted_title=not static_lists)
    if video_list.artitem:
        add_art(video_list.id, list_item, video_list.artitem)
    url = common.build_url(pathitems,
                           params={'genre_id': unicode(video_list.get('genreId'))},
                           mode=g.MODE_DIRECTORY)
    return (url, list_item, True)


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_subgenre_listing(subgenre_list, menu_data):
    """Build a listing of subgenre lists."""
    directory_items = []
    for index, subgenre_data in subgenre_list.lists:  # pylint: disable=unused-variable
        # Create a new submenu info in MAIN_MENU_ITEMS
        # for reference when 'directory' find the menu data
        sel_video_list_id = unicode(subgenre_data['id'])
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
        sub_menu_data['main_menu'] = menu_data['main_menu']\
            if menu_data.get('main_menu') else menu_data.copy()
        sub_menu_data.update({'title': subgenre_data['name']})
        g.LOCAL_DB.set_value(sel_video_list_id, sub_menu_data, TABLE_MENU_DATA)
        directory_items.append(_create_subgenre_item(sel_video_list_id,
                                                     subgenre_data,
                                                     sub_menu_data))
    parent_menu_data = g.LOCAL_DB.get_value(menu_data['path'][1],
                                            table=TABLE_MENU_DATA, data_type=dict)
    finalize_directory(directory_items, g.CONTENT_FOLDER,
                       title=parent_menu_data['title'],
                       sort_type='sort_label')
    return menu_data.get('view')


@common.time_execution(immediate=False)
def _create_subgenre_item(video_list_id, subgenre_data, menu_data):
    """Create a tuple that can be added to a Kodi directory that represents
    a videolist as listed in a subgenre listing"""
    pathitems = ['video_list_sorted', menu_data['path'][1], video_list_id]
    list_item = list_item_skeleton(subgenre_data['name'])
    url = common.build_url(pathitems, mode=g.MODE_DIRECTORY)
    return (url, list_item, True)


@custom_viewmode(g.VIEW_SHOW)
@common.time_execution(immediate=False)
def build_video_listing(video_list, menu_data, pathitems=None, genre_id=None):
    """Build a video listing"""
    params = get_param_watched_status_by_profile()
    directory_items = [_create_video_item(videoid_value, video, video_list, menu_data, params)
                       for videoid_value, video
                       in list(video_list.videos.items())]
    # If genre_id exists add possibility to browse lolomos subgenres
    if genre_id and genre_id != 'None':
        menu_id = 'subgenre_' + genre_id
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], menu_id, genre_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = menu_data.get('content_type', g.CONTENT_SHOW)
        sub_menu_data['main_menu'] = menu_data['main_menu']\
            if menu_data.get('main_menu') else menu_data.copy()
        sub_menu_data.update({'title': common.get_local_string(30089)})
        g.LOCAL_DB.set_value(menu_id, sub_menu_data, TABLE_MENU_DATA)
        directory_items.insert(0,
                               (common.build_url(['genres', menu_id, genre_id],
                                                 mode=g.MODE_DIRECTORY),
                                list_item_skeleton(common.get_local_string(30089),
                                                   icon='DefaultVideoPlaylists.png',
                                                   description=common.get_local_string(30088)),
                                True))
    add_items_previous_next_page(directory_items, pathitems,
                                 video_list.perpetual_range_selector, genre_id)
    sort_type = 'sort_nothing'
    if menu_data['path'][1] == 'myList' and \
       int(g.ADDON.getSettingInt('menu_sortorder_mylist')) == 0:
        # At the moment it is not possible to make a query with results sorted for the 'mylist',
        # so we adding the sort order of kodi
        sort_type = 'sort_label_ignore_folders'
    parent_menu_data = g.LOCAL_DB.get_value(menu_data['path'][1],
                                            table=TABLE_MENU_DATA, data_type=dict)
    finalize_directory(directory_items, menu_data.get('content_type', g.CONTENT_SHOW),
                       title=parent_menu_data['title'],
                       sort_type=sort_type)
    return menu_data.get('view')


@common.time_execution(immediate=False)
def _create_video_item(videoid_value, video, video_list, menu_data, params):
    """Create a tuple that can be added to a Kodi directory that represents
    a video as listed in a videolist"""
    is_movie = video['summary']['type'] == 'movie'
    videoid = common.VideoId(
        **{('movieid' if is_movie else 'tvshowid'): videoid_value})
    list_item = list_item_skeleton(video['title'])
    add_info(videoid, list_item, video, video_list.data, handle_highlighted_title=menu_data['path'][1] != 'myList')
    add_art(videoid, list_item, video)
    url = common.build_url(videoid=videoid,
                           mode=(g.MODE_PLAY
                                 if is_movie
                                 else g.MODE_DIRECTORY),
                           params=params)
    list_item.addContextMenuItems(generate_context_menu_items(videoid))
    return (url, list_item, not is_movie)


@custom_viewmode(g.VIEW_SEASON)
@common.time_execution(immediate=False)
def build_season_listing(tvshowid, season_list, pathitems=None):
    """Build a season listing"""
    directory_items = [_create_season_item(tvshowid, seasonid_value, season,
                                           season_list)
                       for seasonid_value, season
                       in list(season_list.seasons.items())]
    add_items_previous_next_page(directory_items, pathitems, season_list.perpetual_range_selector)
    finalize_directory(directory_items, g.CONTENT_SEASON, 'sort_only_label',
                       title=' - '.join((season_list.tvshow['title'],
                                         common.get_local_string(20366)[2:])))


@common.time_execution(immediate=False)
def _create_season_item(tvshowid, seasonid_value, season, season_list):
    """Create a tuple that can be added to a Kodi directory that represents
    a season as listed in a season listing"""
    seasonid = tvshowid.derive_season(seasonid_value)
    list_item = list_item_skeleton(season['summary']['name'])
    add_info(seasonid, list_item, season, season_list.data)
    add_art(tvshowid, list_item, season_list.tvshow)
    list_item.addContextMenuItems(generate_context_menu_items(seasonid))
    url = common.build_url(videoid=seasonid, mode=g.MODE_DIRECTORY)
    return (url, list_item, True)


@custom_viewmode(g.VIEW_EPISODE)
@common.time_execution(immediate=False)
def build_episode_listing(seasonid, episode_list, pathitems=None):
    """Build a season listing"""
    params = get_param_watched_status_by_profile()
    directory_items = [_create_episode_item(seasonid, episodeid_value, episode,
                                            episode_list, params)
                       for episodeid_value, episode
                       in list(episode_list.episodes.items())]
    add_items_previous_next_page(directory_items, pathitems, episode_list.perpetual_range_selector)
    finalize_directory(directory_items, g.CONTENT_EPISODE, 'sort_episodes',
                       title=' - '.join(
                           (episode_list.tvshow['title'],
                            episode_list.season['summary']['name'])))


@common.time_execution(immediate=False)
def _create_episode_item(seasonid, episodeid_value, episode, episode_list, params):
    """Create a tuple that can be added to a Kodi directory that represents
    an episode as listed in an episode listing"""
    episodeid = seasonid.derive_episode(episodeid_value)
    list_item = list_item_skeleton(episode['title'])
    add_info(episodeid, list_item, episode, episode_list.data)
    add_art(episodeid, list_item, episode)
    list_item.addContextMenuItems(generate_context_menu_items(episodeid))
    url = common.build_url(videoid=episodeid, mode=g.MODE_PLAY, params=params)
    return (url, list_item, False)


@custom_viewmode(g.VIEW_SHOW)
@common.time_execution(immediate=False)
def build_supplemental_listing(video_list, pathitems=None):  # pylint: disable=unused-argument
    """Build a supplemental listing (eg. trailers)"""
    params = get_param_watched_status_by_profile()
    directory_items = [_create_supplemental_item(videoid_value, video, video_list, params)
                       for videoid_value, video
                       in list(video_list.videos.items())]
    finalize_directory(directory_items, g.CONTENT_SHOW, 'sort_label',
                       title='Trailers')


@common.time_execution(immediate=False)
def _create_supplemental_item(videoid_value, video, video_list, params):
    """Create a tuple that can be added to a Kodi directory that represents
    a video as listed in a videolist"""
    videoid = common.VideoId(
        **{'supplementalid': videoid_value})
    list_item = list_item_skeleton(video['title'])
    add_info(videoid, list_item, video, video_list.data)
    add_art(videoid, list_item, video)
    url = common.build_url(videoid=videoid,
                           mode=g.MODE_PLAY,
                           params=params)
    list_item.addContextMenuItems(generate_context_menu_items(videoid))
    return (url, list_item, False)


def list_item_skeleton(label, icon=None, fanart=None, description=None, customicon=None):
    """Create a rudimentary list item skeleton with icon and fanart"""
    # pylint: disable=unexpected-keyword-arg
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setContentLookup(False)
    art_values = {}
    if customicon:
        addon_dir = xbmc.translatePath(g.ADDON.getAddonInfo('path'))
        icon = os.path.join(addon_dir, 'resources', 'media', customicon)
        art_values['thumb'] = icon
    if icon:
        art_values['icon'] = icon
    if fanart:
        art_values['fanart'] = fanart
    if art_values:
        list_item.setArt(art_values)
    info = {'title': label}
    if description:
        info['plot'] = description
    list_item.setInfo('video', info)
    return list_item


def add_items_previous_next_page(directory_items, pathitems, perpetual_range_selector,
                                 genre_id=None):
    if pathitems and perpetual_range_selector:
        if 'previous_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('previous_start'),
                      'genre_id':
                          genre_id if perpetual_range_selector.get('previous_start') == 0 else None}
            previous_page_url = common.build_url(pathitems=pathitems,
                                                 params=params,
                                                 mode=g.MODE_DIRECTORY)
            directory_items.insert(0, (previous_page_url,
                                       list_item_skeleton(common.get_local_string(30148),
                                                          customicon='FolderPagePrevious.png'),
                                       True))
        if 'next_start' in perpetual_range_selector:
            params = {'perpetual_range_start': perpetual_range_selector.get('next_start')}
            next_page_url = common.build_url(pathitems=pathitems,
                                             params=params,
                                             mode=g.MODE_DIRECTORY)
            directory_items.append((next_page_url,
                                    list_item_skeleton(common.get_local_string(30147),
                                                       customicon='FolderPageNext.png'),
                                    True))


def finalize_directory(items, content_type=g.CONTENT_FOLDER, sort_type='sort_nothing',
                       title=None):
    """Finalize a directory listing.
    Add items, set available sort methods and content type"""
    if title:
        xbmcplugin.setPluginCategory(g.PLUGIN_HANDLE, title)
    xbmcplugin.setContent(g.PLUGIN_HANDLE, content_type)
    add_sort_methods(sort_type)
    xbmcplugin.addDirectoryItems(g.PLUGIN_HANDLE, items)


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


def get_param_watched_status_by_profile():
    """
    Get a value used as parameter in the ListItem (of videos),
    in order to differentiate the watched status and other Kodi data by profiles
    :return: a dictionary to be add to 'build_url' params
    """
    return {'profile_guid': g.LOCAL_DB.get_active_profile_guid()}
