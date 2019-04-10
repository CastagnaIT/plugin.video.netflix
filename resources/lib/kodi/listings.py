# -*- coding: utf-8 -*-
"""Helper functions to build plugin listings for Kodi"""
from __future__ import unicode_literals

from functools import wraps

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.globals import g
import resources.lib.common as common

from .infolabels import add_info, add_art
from .context_menu import generate_context_menu_items


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
                    if viewtype_override in g.VIEWTYPES
                    else viewtype)
            _activate_view(view)
        return set_custom_viewmode
    return decorate_viewmode


def _activate_view(view):
    """Activate the given view if the plugin is run in the foreground
    and custom views are enabled"""
    if (('plugin://{}'.format(g.ADDON_ID) in
         xbmc.getInfoLabel('Container.FolderPath')) and
            g.ADDON.getSettingBool('customview')):

        #enum order: List|Poster|IconWall|Shift|InfoWall|WideList|Wall|Banner|FanArt|Custom
        views_id_list = [50, 51, 52, 53, 54, 55, 500, 501, 502, -1]

        view_id = views_id_list[int(g.ADDON.getSettingInt('viewmode' + view))]

        if view_id == -1:
            view_id = int(g.ADDON.getSettingInt('viewmode' + view + 'id'))

        if view_id != -1 and view_id != 0:
            xbmc.executebuiltin(
                'Container.SetViewMode({})'.format(view_id))


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_profiles_listing(profiles):
    """Builds the profiles list Kodi screen"""
    try:
        from HTMLParser import HTMLParser
    except ImportError:
        from html.parser import HTMLParser
    html_parser = HTMLParser()
    finalize_directory([_create_profile_item(guid, profile, html_parser)
                        for guid, profile
                        in profiles.iteritems()])


def _create_profile_item(profile_guid, profile, html_parser):
    """Create a tuple that can be added to a Kodi directory that represents
    a profile as listed in the profiles listing"""
    profile_name = profile.get('profileName', '')
    unescaped_profile_name = html_parser.unescape(profile_name)
    enc_profile_name = profile_name.encode('utf-8')
    list_item = list_item_skeleton(
        label=unescaped_profile_name, icon=profile.get('avatar'))
    list_item.select(profile.get('isActive', False))
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


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_main_menu_listing(lolomo):
    """
    Builds the video lists (my list, continue watching, etc.) Kodi screen
    """
    directory_items = []
    mylist_menu_exists = False

    for menu_id, data in g.MAIN_MENU_ITEMS.iteritems():
        if data['show_in_menu']:
            if data['lolomo_known']:
                for list_id, user_list in lolomo.lists_by_context(data['lolomo_contexts'], break_on_first=True):
                    directory_items.append(_create_videolist_item(list_id, user_list, data, static_lists=True))
                    g.PERSISTENT_STORAGE['menu_titles'][menu_id] = user_list['displayName']
                    if "queue" in data['lolomo_contexts']:
                        mylist_menu_exists = True
            else:
                menu_title = common.get_local_string(data['label_id']) \
                    if data['label_id'] is not None else 'Missing menu title'
                g.PERSISTENT_STORAGE['menu_titles'][menu_id] = menu_title
                menu_description = common.get_local_string(data['description_id']) \
                    if data['description_id'] is not None else ''
                directory_items.append(
                    (common.build_url(data['path'], mode=g.MODE_DIRECTORY),
                     list_item_skeleton(menu_title,
                                        icon=data['icon'],
                                        description=menu_description),
                     True))
    #g.PERSISTENT_STORAGE.commit()  performed with the next call to PERSISTENT_STORAGE setitem
    g.PERSISTENT_STORAGE['profile_have_mylist_menu'] = mylist_menu_exists
    finalize_directory(directory_items, g.CONTENT_FOLDER,
                       title=common.get_local_string(30097))


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_lolomo_listing(lolomo, menu_data, force_videolistbyid=False, exclude_lolomo_known=False):
    """Build a listing of vieo lists (LoLoMo). Only show those
    lists with a context specified context if contexts is set."""
    contexts = menu_data['lolomo_contexts']
    lists = (lolomo.lists_by_context(contexts)
             if contexts
             else lolomo.lists.iteritems())
    directory_items = []
    for video_list_id, video_list in lists:
        menu_parameters = common.MenuIdParameters(id_values=video_list_id)
        if exclude_lolomo_known:
            # Keep only the menus genre
            if menu_parameters.type_id != '28':
                 continue
        if menu_parameters.is_menu_id:
            # Create a new submenu info in MAIN_MENU_ITEMS for reference when 'directory' find the menu data
            sel_video_list_id = menu_parameters.context_id if menu_parameters.context_id and not force_videolistbyid else video_list_id
            sub_menu_data = menu_data.copy()
            sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id]
            sub_menu_data['lolomo_known'] = False
            sub_menu_data['lolomo_contexts'] = None
            sub_menu_data['show_in_menu'] = False
            sub_menu_data['force_videolistbyid'] = force_videolistbyid
            g.PERSISTENT_STORAGE['sub_menus'][sel_video_list_id] = sub_menu_data
            g.PERSISTENT_STORAGE['menu_titles'][sel_video_list_id] = video_list['displayName']
            directory_items.append(_create_videolist_item(sel_video_list_id, video_list, sub_menu_data))
    g.PERSISTENT_STORAGE.commit()
    finalize_directory(directory_items, g.CONTENT_FOLDER,
                       title=g.get_menu_title(menu_data['path'][1]))


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
    add_info(video_list.id, list_item, video_list, video_list.data)
    if video_list.artitem:
        add_art(video_list.id, list_item, video_list.artitem)
    url = common.build_url(pathitems, mode=g.MODE_DIRECTORY)
    return (url, list_item, True)


@custom_viewmode(g.VIEW_SHOW)
@common.time_execution(immediate=False)
def build_video_listing(video_list, menu_data):
    """Build a video listing"""
    directory_items = [_create_video_item(videoid_value, video, video_list)
                       for videoid_value, video
                       in video_list.videos.iteritems()]
    if video_list.get('genreId'):
        directory_items.append(
            (common.build_url(['genres', unicode(video_list['genreId'])],
                              mode=g.MODE_DIRECTORY),
             list_item_skeleton(common.get_local_string(30088),
                                icon='DefaultAddSource.png',
                                description=common.get_local_string(30090)),
             True))
        # TODO: Implement browsing of subgenres
        # directory_items.append(
        #     (common.build_url(pathitems=['genres', genre_id, 'subgenres'],
        #                       mode=g.MODE_DIRECTORY),
        #      list_item_skeleton('Browse subgenres...'),
        #      True))
    finalize_directory(directory_items, menu_data['content_type'],
                       title=g.get_menu_title(menu_data['path'][1]))


@common.time_execution(immediate=False)
def _create_video_item(videoid_value, video, video_list):
    """Create a tuple that can be added to a Kodi directory that represents
    a video as listed in a videolist"""
    is_movie = video['summary']['type'] == 'movie'
    videoid = common.VideoId(
        **{('movieid' if is_movie else 'tvshowid'): videoid_value})
    list_item = list_item_skeleton(video['title'])
    add_info(videoid, list_item, video, video_list.data)
    add_art(videoid, list_item, video)
    url = common.build_url(videoid=videoid,
                           mode=(g.MODE_PLAY
                                 if is_movie
                                 else g.MODE_DIRECTORY))
    list_item.addContextMenuItems(generate_context_menu_items(videoid))
    return (url, list_item, not is_movie)


@custom_viewmode(g.VIEW_SEASON)
@common.time_execution(immediate=False)
def build_season_listing(tvshowid, season_list):
    """Build a season listing"""
    directory_items = [_create_season_item(tvshowid, seasonid_value, season,
                                           season_list)
                       for seasonid_value, season
                       in season_list.seasons.iteritems()]
    finalize_directory(directory_items, g.CONTENT_SEASON,
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
def build_episode_listing(seasonid, episode_list):
    """Build a season listing"""
    directory_items = [_create_episode_item(seasonid, episodeid_value, episode,
                                            episode_list)
                       for episodeid_value, episode
                       in episode_list.episodes.iteritems()]
    finalize_directory(directory_items, g.CONTENT_EPISODE,
                       title=' - '.join(
                           (episode_list.tvshow['title'],
                            episode_list.season['summary']['name'])))


@common.time_execution(immediate=False)
def _create_episode_item(seasonid, episodeid_value, episode, episode_list):
    """Create a tuple that can be added to a Kodi directory that represents
    an episode as listed in an episode listing"""
    episodeid = seasonid.derive_episode(episodeid_value)
    list_item = list_item_skeleton(episode['title'])
    add_info(episodeid, list_item, episode, episode_list.data)
    add_art(episodeid, list_item, episode)
    list_item.addContextMenuItems(generate_context_menu_items(episodeid))
    url = common.build_url(videoid=episodeid, mode=g.MODE_PLAY)
    return (url, list_item, False)


def list_item_skeleton(label, icon=None, fanart=None, description=None):
    """Create a rudimentary list item skeleton with icon and fanart"""
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


def finalize_directory(items, content_type=g.CONTENT_FOLDER, refresh=False,
                       title=None):
    """Finalize a directory listing.
    Add items, set available sort methods and content type"""
    if title:
        xbmcplugin.setPluginCategory(g.PLUGIN_HANDLE, title)
    xbmcplugin.setContent(g.PLUGIN_HANDLE, content_type)
    xbmcplugin.addDirectoryItems(g.PLUGIN_HANDLE, items)
    xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=True)
