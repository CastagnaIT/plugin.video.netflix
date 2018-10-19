# -*- coding: utf-8 -*-
"""Helper functions to build plugin listings for Kodi"""
from __future__ import unicode_literals

from functools import wraps

import xbmc
import xbmcgui
import xbmcplugin

import resources.lib.common as common
import resources.lib.api.paths as paths

VIEW_FOLDER = 'folder'
VIEW_MOVIE = 'movie'
VIEW_SHOW = 'show'
VIEW_SEASON = 'season'
VIEW_EPISODE = 'episode'
VIEW_EXPORTED = 'exported'

VIEWTYPES = [VIEW_FOLDER, VIEW_MOVIE, VIEW_SHOW, VIEW_SEASON,
             VIEW_EPISODE, VIEW_EXPORTED]

CONTENT_FOLDER = 'files'
CONTENT_MOVIE = 'movies'
CONTENT_SHOW = 'tvshows'
CONTENT_SEASON = 'seasons'
CONTENT_EPISODE = 'episodes'

def create_list_item(label, icon=None, fanart=None):
    """Create a rudimentary list item with icon and fanart"""
    list_item = xbmcgui.ListItem(label=label,
                                 iconImage=icon or common.DEFAULT_FANART)
    list_item.setProperty('fanart_image', fanart or common.DEFAULT_FANART)
    return list_item

def finalize_directory(items, sort_methods=None, content_type=CONTENT_FOLDER,
                       refresh=False):
    """Finalize a directory listing.
    Add items, set available sort methods and content type"""
    xbmcplugin.addDirectoryItems(
        common.PLUGIN_HANDLE, items, len(items))

    for sort_method in (sort_methods
                        if sort_methods
                        else [xbmcplugin.SORT_METHOD_UNSORTED]):
        xbmcplugin.addSortMethod(
            handle=common.PLUGIN_HANDLE,
            sortMethod=sort_method)

    xbmcplugin.setContent(
        handle=common.PLUGIN_HANDLE,
        content=content_type)

    xbmcplugin.endOfDirectory(
        handle=common.PLUGIN_HANDLE,
        updateListing=refresh)

def custom_viewmode(viewtype):
    """Decorator that sets a custom viewmode if currently in
    a listing of the plugin"""
    # pylint: disable=missing-docstring
    def decorate_viewmode(func):
        @wraps(func)
        def set_custom_viewmode(*args, **kwargs):
            viewtype_override = func(*args, **kwargs)
            view = (viewtype_override
                    if viewtype_override in VIEWTYPES
                    else viewtype)
            if (('plugin://{}'.format(common.ADDON_ID) in
                 xbmc.getInfoLabel('Container.FolderPath')) and
                    common.ADDON.getSettingBool('customview')):
                view_id = common.ADDON.getSettingInt('viewmode' + view)
                if view_id != -1:
                    xbmc.executebuiltin(
                        'Container.SetViewMode({})'.format(view_id))
        return set_custom_viewmode
    return decorate_viewmode

@custom_viewmode(VIEW_FOLDER)
def build_profiles_listing(profiles):
    """
    Builds the profiles list Kodi screen

    :param profiles: list of user profiles
    :type profiles: list
    :param action: action paramter to build the subsequent routes
    :type action: str
    :param build_url: function to build the subsequent routes
    :type build_url: fn
    :returns: bool -- List could be build
    """
    directory_items = []
    try:
        from HTMLParser import HTMLParser
    except ImportError:
        from html.parser import HTMLParser
    html_parser = HTMLParser()
    for profile_guid, profile in profiles.iteritems():
        profile_name = profile.get('profileName', '')
        unescaped_profile_name = html_parser.unescape(profile_name)
        enc_profile_name = profile_name.encode('utf-8')
        list_item = create_list_item(
            label=unescaped_profile_name, icon=profile.get('avatar'))
        autologin_url = common.build_url(
            pathitems=['save_autologin', profile_guid],
            params={'autologin_user': enc_profile_name},
            mode='action')
        list_item.addContextMenuItems(
            items=[(common.get_local_string(30053),
                    'RunPlugin({})'.format(autologin_url))])
        directory_items.append(
            (common.build_directory_url(
                ['home'], {'profile_id': profile_guid}),
             list_item,
             True))

    finalize_directory(
        items=directory_items,
        sort_methods=[xbmcplugin.SORT_METHOD_LABEL])

@custom_viewmode(VIEW_FOLDER)
def build_main_menu_listing(lolomo):
    """
    Builds the video lists (my list, continue watching, etc.) Kodi screen
    """
    directory_items = []
    for _, user_list in lolomo.lists_by_context(common.KNOWN_LIST_TYPES):
        common.debug('Creating listitem for: {}'.format(user_list))
        directory_items.append(
            (common.build_directory_url(
                ['video_list', user_list['context']]),
             create_list_item(user_list['displayName']),
             True))

    for context_type, data in common.MISC_CONTEXTS.iteritems():
        directory_items.append(
            (common.build_directory_url(
                [context_type]),
             create_list_item(common.get_local_string(data['label_id'])),
             True))

    # Add search
    directory_items.append(
        (common.build_url(['search']),
         create_list_item(common.get_local_string(30011)),
         True))

    # Add exported
    directory_items.append(
        (common.build_directory_url(['exported']),
         create_list_item(common.get_local_string(30048)),
         True))

    finalize_directory(
        items=directory_items,
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED],
        content_type=CONTENT_FOLDER)

@custom_viewmode(VIEW_SHOW)
def build_video_listing(video_list):
    """
    Build a video listing
    """
    only_movies = True
    directory_items = []
    for video_id, video in video_list.videos.iteritems():
        list_item = create_list_item(video['title'])
        # add_infolabels(list_item, video)
        add_art(list_item, video)
        needs_pin = int(video.get('maturity', {})
                        .get('level', 1001)) >= 1000
        is_movie = video['summary']['type'] == 'movie'
        if is_movie:
            url = common.build_url(
                pathitems=['play', video_id],
                params={'pin': needs_pin})
        else:
            url = common.build_directory_url(
                pathitems=['show', video_id],
                params={'pin': needs_pin})
        directory_items.append(
            (url,
             list_item,
             not is_movie))
        only_movies = only_movies and is_movie
    finalize_directory(
        items=directory_items,
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED,
                      xbmcplugin.SORT_METHOD_LABEL,
                      xbmcplugin.SORT_METHOD_TITLE,
                      xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                      xbmcplugin.SORT_METHOD_GENRE,
                      xbmcplugin.SORT_METHOD_LASTPLAYED],
        content_type=CONTENT_MOVIE if only_movies else CONTENT_SHOW)
    return VIEW_MOVIE if only_movies else VIEW_SHOW

@custom_viewmode(VIEW_SEASON)
def build_season_listing(tvshowid, season_list):
    """
    Build a season listing
    """
    directory_items = []
    for season_id, season in season_list.seasons.iteritems():
        list_item = create_list_item(season['summary']['name'])
        # add_infolabels(list_item, video)
        add_art(list_item, season_list.tvshow)
        directory_items.append(
            (common.build_directory_url(
                pathitems=['show', tvshowid, 'seasons', season_id]),
             list_item,
             True))
    finalize_directory(
        items=directory_items,
        sort_methods=[xbmcplugin.SORT_METHOD_NONE,
                      xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                      xbmcplugin.SORT_METHOD_LABEL,
                      xbmcplugin.SORT_METHOD_LASTPLAYED,
                      xbmcplugin.SORT_METHOD_TITLE],
        content_type=CONTENT_SEASON)

@custom_viewmode(VIEW_EPISODE)
def build_episode_listing(tvshowid, seasonid, episode_list):
    """
    Build a season listing
    """
    directory_items = []
    for episode_id, episode in episode_list.episodes.iteritems():
        list_item = create_list_item(episode['title'])
        # add_infolabels(list_item, video)
        add_art(list_item, episode)
        directory_items.append(
            (common.build_url(
                pathitems=['play', 'show', tvshowid, 'seasons', seasonid,
                           'episodes', episode_id]),
             list_item,
             False))
    finalize_directory(
        items=directory_items,
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED,
                      xbmcplugin.SORT_METHOD_LABEL,
                      xbmcplugin.SORT_METHOD_TITLE,
                      xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                      xbmcplugin.SORT_METHOD_GENRE,
                      xbmcplugin.SORT_METHOD_LASTPLAYED],
        content_type=CONTENT_EPISODE)

def add_art(list_item, item):
    """Add art infolabels to list_item"""
    boxarts = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[0] + ['url'], item)
    boxart_large = boxarts[paths.ART_SIZE_FHD]
    boxart_small = boxarts[paths.ART_SIZE_SD]
    poster = boxarts[paths.ART_SIZE_POSTER]
    interesting_moment = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[1] + ['url'], item)[paths.ART_SIZE_FHD]
    clearlogo = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[3] + ['url'], item)
    fanart = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[4] + [0, 'url'], item)
    if boxart_large or boxart_small:
        art = {
            'thumb': boxart_large or boxart_small,
            'landscape': boxart_large or boxart_small,
            'fanart': boxart_large or boxart_small,
        }
    else:
        art = {}
    if poster:
        art['poster'] = poster
    if clearlogo:
        art['clearlogo'] = clearlogo
    if interesting_moment:
        art['fanart'] = interesting_moment
        if item.get('summary', {}).get('type') == 'episode':
            art['thumb'] = interesting_moment
            art['landscape'] = interesting_moment
    if fanart:
        art['fanart'] = fanart
    list_item.setArt(art)
    return list_item
