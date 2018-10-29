# -*- coding: utf-8 -*-
"""Helper functions to build plugin listings for Kodi"""
from __future__ import unicode_literals

from functools import wraps

import xbmc
import xbmcgui
import xbmcplugin

import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.library as library

from .infolabels import add_info, add_art

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

RUN_PLUGIN = 'XBMC.RunPlugin({})'

ADDITIONAL_MAIN_MENU_ITEMS = [
    {'path': ['genres', '83'],
     'label': common.get_local_string(30095),
     'icon': 'DefaultTVShows.png',
     'description': None},
    {'path': ['genres', '34399'],
     'label': common.get_local_string(30096),
     'icon': 'DefaultMovies.png',
     'description': None},
    {'path': ['search'],
     'label': common.get_local_string(30011),
     'icon': None,
     'description': common.get_local_string(30092)},
    {'path': ['exported'],
     'label': common.get_local_string(30048),
     'icon': 'DefaultHardDisk.png',
     'description': common.get_local_string(30091)},
]

CONTEXT_MENU_ACTIONS = {
    'export': {
        'label': common.get_local_string(30018),
        'url': (lambda videoid:
                common.build_url(['export'], videoid,
                                 mode=common.MODE_LIBRARY))},
    'remove': {
        'label': common.get_local_string(30030),
        'url': (lambda videoid:
                common.build_url(['remove'], videoid,
                                 mode=common.MODE_LIBRARY))},
    'update': {
        'label': common.get_local_string(30030),
        'url': (lambda videoid:
                common.build_url(['update'], videoid,
                                 mode=common.MODE_LIBRARY))},
    'rate': {
        'label': common.get_local_string(30019),
        'url': (lambda videoid:
                common.build_url(['rate'], videoid,
                                 mode=common.MODE_ACTION))},
    'add_to_list': {
        'label': common.get_local_string(30021),
        'url': (lambda videoid:
                common.build_url(['my_list', 'add'], videoid,
                                 mode=common.MODE_ACTION))},
    'remove_from_list': {
        'label': common.get_local_string(30020),
        'url': (lambda videoid:
                common.build_url(['my_list', 'remove'], videoid,
                                 mode=common.MODE_ACTION))},
}


def custom_viewmode(viewtype):
    """Decorator that sets a custom viewmode if currently in
    a listing of the plugin"""
    # pylint: disable=missing-docstring
    def decorate_viewmode(func):
        @wraps(func)
        def set_custom_viewmode(*args, **kwargs):
            # pylint: disable=no-member
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
            mode=common.MODE_ACTION)
        list_item.addContextMenuItems(
            items=[(common.get_local_string(30053),
                    'RunPlugin({})'.format(autologin_url))])
        directory_items.append(
            (common.build_url(pathitems=['home'],
                              params={'profile_id': profile_guid},
                              mode=common.MODE_DIRECTORY),
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
        list_item = create_list_item(user_list['displayName'])
        add_info(user_list.id, list_item, user_list, user_list.data)
        add_art(user_list.id, list_item, user_list.artitem)
        directory_items.append(
            (common.build_url(
                ['video_list', user_list['context']],
                mode=common.MODE_DIRECTORY),
             list_item,
             True))

    for context_type, data in common.MISC_CONTEXTS.iteritems():
        directory_items.append(
            (common.build_url([context_type], mode=common.MODE_DIRECTORY),
             create_list_item(common.get_local_string(data['label_id']),
                              icon=data['icon'],
                              description=common.get_local_string(
                                  data['description_id'])),
             True))

    for menu_item in ADDITIONAL_MAIN_MENU_ITEMS:
        directory_items.append(
            (common.build_url(menu_item['path'], mode=common.MODE_DIRECTORY),
             create_list_item(menu_item['label'],
                              icon=menu_item['icon'],
                              description=menu_item['description']),
             True))

    finalize_directory(
        items=directory_items,
        title=common.get_local_string(30097),
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED],
        content_type=CONTENT_FOLDER)

@custom_viewmode(VIEW_FOLDER)
def build_lolomo_listing(lolomo, contexts=None):
    """Build a listing of vieo lists (LoLoMo). Only show those
    lists with a context specified context if contexts is set."""
    directory_items = []
    lists = (lolomo.lists_by_context(contexts)
             if contexts
             else lolomo.lists.iteritems())
    for video_list_id, video_list in lists:
        if video_list['context'] == 'billboard':
            # Skip billboard (only contains one video)
            continue
        params = ({'genreId': video_list['genreId']}
                  if video_list.get('genreId')
                  else None)
        list_item = create_list_item(video_list['displayName'])
        add_info(video_list.id, list_item, video_list, video_list.data)
        add_art(video_list.id, list_item, video_list.artitem)
        directory_items.append(
            (common.build_url(
                ['video_list', video_list_id], mode=common.MODE_DIRECTORY,
                params=params),
             list_item,
             True))
    finalize_directory(
        items=directory_items,
        title=lolomo.get('name'),
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED],
        content_type=CONTENT_FOLDER)


@custom_viewmode(VIEW_SHOW)
def build_video_listing(video_list, genre_id=None):
    """
    Build a video listing
    """
    only_movies = True
    directory_items = []
    for videoid_value, video in video_list.videos.iteritems():
        is_movie = video['summary']['type'] == 'movie'
        videoid = common.VideoId(
            **{('movieid' if is_movie else 'tvshowid'): videoid_value})
        list_item = create_list_item(video['title'])
        add_info(videoid, list_item, video, video_list.data)
        add_art(videoid, list_item, video)
        needs_pin = int(video.get('maturity', {})
                        .get('level', 1001)) >= 1000
        url = common.build_url(videoid=videoid,
                               params={'pin': needs_pin},
                               mode=(common.MODE_PLAY
                                     if is_movie
                                     else common.MODE_DIRECTORY))
        list_item.addContextMenuItems(
            _generate_context_menu_items(videoid))
        directory_items.append(
            (url,
             list_item,
             not is_movie))
        only_movies = only_movies and is_movie
    if genre_id:
        directory_items.append(
            (common.build_url(pathitems=['genres', genre_id],
                              mode=common.MODE_DIRECTORY),
             create_list_item(common.get_local_string(30088),
                              icon='DefaultAddSource.png',
                              description=common.get_local_string(30090)),
             True))
        # TODO: Implement browsing of subgenres
        # directory_items.append(
        #     (common.build_url(pathitems=['genres', genre_id, 'subgenres'],
        #                       mode=common.MODE_DIRECTORY),
        #      create_list_item('Browse subgenres...'),
        #      True))
    finalize_directory(
        items=directory_items,
        title=video_list['displayName'],
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
    for seasonid_value, season in season_list.seasons.iteritems():
        seasonid = tvshowid.derive_season(seasonid_value)
        list_item = create_list_item(season['summary']['name'])
        add_info(seasonid, list_item, season, season_list.data)
        add_art(tvshowid, list_item, season_list.tvshow)
        list_item.addContextMenuItems(
            _generate_context_menu_items(seasonid))
        directory_items.append(
            (common.build_url(videoid=seasonid, mode=common.MODE_DIRECTORY),
             list_item,
             True))
    finalize_directory(
        items=directory_items,
        title=' - '.join((season_list.tvshow['title'],
                          common.get_local_string(20366)[2:])),
        sort_methods=[xbmcplugin.SORT_METHOD_NONE,
                      xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                      xbmcplugin.SORT_METHOD_LABEL,
                      xbmcplugin.SORT_METHOD_LASTPLAYED,
                      xbmcplugin.SORT_METHOD_TITLE],
        content_type=CONTENT_SEASON)


@custom_viewmode(VIEW_EPISODE)
def build_episode_listing(seasonid, episode_list):
    """
    Build a season listing
    """
    directory_items = []
    for episodeid_value, episode in episode_list.episodes.iteritems():
        episodeid = seasonid.derive_episode(episodeid_value)
        list_item = create_list_item(episode['title'])
        add_info(episodeid, list_item, episode, episode_list.data)
        add_art(episodeid, list_item, episode)
        list_item.addContextMenuItems(
            _generate_context_menu_items(episodeid))
        directory_items.append(
            (common.build_url(videoid=episodeid, mode=common.MODE_PLAY),
             list_item,
             False))
    finalize_directory(
        items=directory_items,
        title=' - '.join((episode_list.tvshow['title'],
                          episode_list.season['summary']['name'])),
        sort_methods=[xbmcplugin.SORT_METHOD_UNSORTED,
                      xbmcplugin.SORT_METHOD_LABEL,
                      xbmcplugin.SORT_METHOD_TITLE,
                      xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                      xbmcplugin.SORT_METHOD_GENRE,
                      xbmcplugin.SORT_METHOD_LASTPLAYED],
        content_type=CONTENT_EPISODE)


def create_list_item(label, icon=None, fanart=None, description=None):
    """Create a rudimentary list item with icon and fanart"""
    # pylint: disable=unexpected-keyword-arg
    list_item = xbmcgui.ListItem(label=label, iconImage=icon, offscreen=True)
    list_item.setContentLookup(False)
    if fanart:
        list_item.setProperty('fanart_image', fanart)
    info = {'title': label}
    if description:
        info['plot'] = description
    list_item.setInfo('video', info)
    return list_item


def finalize_directory(items, sort_methods=None, content_type=CONTENT_FOLDER,
                       refresh=False, title=None):
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

    if title:
        xbmcplugin.setPluginCategory(
            handle=common.PLUGIN_HANDLE,
            category=title)

    xbmcplugin.setContent(
        handle=common.PLUGIN_HANDLE,
        content=content_type)

    xbmcplugin.endOfDirectory(
        handle=common.PLUGIN_HANDLE,
        updateListing=refresh)


def _generate_context_menu_items(videoid):
    items = []
    if library.is_in_library(videoid):
        items.append(
            (CONTEXT_MENU_ACTIONS['remove']['label'],
             RUN_PLUGIN.format(
                 CONTEXT_MENU_ACTIONS['remove']['url'](videoid))))
        if videoid.mediatype in [common.VideoId.SHOW, common.VideoId.SEASON]:
            items.append(
                (CONTEXT_MENU_ACTIONS['update']['label'],
                 RUN_PLUGIN.format(
                     CONTEXT_MENU_ACTIONS['update']['url'](videoid))))
    else:
        items.append(
            (CONTEXT_MENU_ACTIONS['export']['label'],
             RUN_PLUGIN.format(
                 CONTEXT_MENU_ACTIONS['export']['url'](videoid))))

    if videoid.mediatype != common.VideoId.SEASON:
        items.append(
            (CONTEXT_MENU_ACTIONS['rate']['label'],
             RUN_PLUGIN.format(
                 CONTEXT_MENU_ACTIONS['rate']['url'](videoid))))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]:
        list_action = ('remove_from_list'
                       if videoid.value in api.mylist_items()
                       else 'add_to_list')
        items.append(
            (CONTEXT_MENU_ACTIONS[list_action]['label'],
             RUN_PLUGIN.format(
                 CONTEXT_MENU_ACTIONS[list_action]['url'](videoid))))
    return items
