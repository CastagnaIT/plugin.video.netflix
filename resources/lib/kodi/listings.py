# -*- coding: utf-8 -*-
"""Helper functions to build plugin listings for Kodi"""
from __future__ import unicode_literals

from functools import wraps

import collections
import os
import xbmc
import xbmcgui
import xbmcplugin

from resources.lib.globals import g
import resources.lib.common as common

from .infolabels import add_info, add_art
from .context_menu import generate_context_menu_items


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
            # Do not change the sequence of this keys, match the return value of the enum xml menu
            list_views = collections.OrderedDict({
                '''
                With Kodi 19 should be implemented a method to get the id of the current skin,
                so we can use this list only with the default skin,
                the other skins partially implement the view types of the standard skin of kodi
                causing also alterations in the translations of the view type names.
                'List': 50,
                'Poster': 51,
                'IconWall': 52,
                'Shift': 53,
                'InfoWall': 54,
                'WideList': 55,
                'Wall': 500,
                'Banner': 501,
                'FanArt': 502,'''
                'LastUsed': 0, # Leave the management to kodi
                'Custom': -1
            })
            # Force a custom view
            view_id = list_views.values()[int(g.ADDON.getSettingInt('viewmode' + partial_setting_id))]
            if view_id == -1:
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
    enc_profile_name = profile_name.encode('utf-8')
    list_item = list_item_skeleton(
        label=unescaped_profile_name,
        icon=g.LOCAL_DB.get_profile_config('avatar', '', guid=profile_guid))
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
    mylist_menu_exists = False

    for menu_id, data in g.MAIN_MENU_ITEMS.iteritems():
        show_in_menu = g.ADDON.getSettingBool('_'.join(('show_menu', menu_id)))
        if show_in_menu:
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
    # g.PERSISTENT_STORAGE.commit()  performed with the next call to PERSISTENT_STORAGE setitem
    g.PERSISTENT_STORAGE['profile_have_mylist_menu'] = mylist_menu_exists
    finalize_directory(directory_items, g.CONTENT_FOLDER, title=common.get_local_string(30097))


@custom_viewmode(g.VIEW_FOLDER)
@common.time_execution(immediate=False)
def build_lolomo_listing(lolomo, menu_data, force_videolistbyid=False, exclude_lolomo_known=False):
    """Build a listing of video lists (LoLoMo). Only show those
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
            sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
            sub_menu_data['lolomo_known'] = False
            sub_menu_data['lolomo_contexts'] = None
            sub_menu_data['content_type'] = g.CONTENT_SHOW
            sub_menu_data['force_videolistbyid'] = force_videolistbyid
            sub_menu_data['main_menu'] = menu_data['main_menu'] if menu_data.get('main_menu') else menu_data.copy()
            g.PERSISTENT_STORAGE['sub_menus'][sel_video_list_id] = sub_menu_data
            g.PERSISTENT_STORAGE['menu_titles'][sel_video_list_id] = video_list['displayName']
            directory_items.append(_create_videolist_item(sel_video_list_id, video_list, sub_menu_data))
    g.PERSISTENT_STORAGE.commit()
    finalize_directory(directory_items, menu_data.get('content_type', g.CONTENT_SHOW),
                       title=g.get_menu_title(menu_data['path'][1]), sort_type='sort_label')
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
    add_info(video_list.id, list_item, video_list, video_list.data)
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
    for index, subgenre_data in subgenre_list.lists:
        # Create a new submenu info in MAIN_MENU_ITEMS for reference when 'directory' find the menu data
        sel_video_list_id = unicode(subgenre_data['id'])
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], sel_video_list_id, sel_video_list_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = g.CONTENT_SHOW
        sub_menu_data['main_menu'] = menu_data['main_menu'] if menu_data.get('main_menu') else menu_data.copy()
        g.PERSISTENT_STORAGE['sub_menus'][sel_video_list_id] = sub_menu_data
        g.PERSISTENT_STORAGE['menu_titles'][sel_video_list_id] = subgenre_data['name']
        directory_items.append(_create_subgenre_item(sel_video_list_id, subgenre_data, sub_menu_data))
    g.PERSISTENT_STORAGE.commit()
    finalize_directory(directory_items, menu_data.get('content_type', g.CONTENT_SHOW),
                       title=g.get_menu_title(menu_data['path'][1]), sort_type='sort_label')
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
    directory_items = [_create_video_item(videoid_value, video, video_list)
                       for videoid_value, video
                       in video_list.videos.iteritems()]
    # If genre_id exists add possibility to browse lolomos subgenres
    if genre_id and genre_id != 'None':
        menu_id = 'subgenre_' + genre_id
        sub_menu_data = menu_data.copy()
        sub_menu_data['path'] = [menu_data['path'][0], menu_id, genre_id]
        sub_menu_data['lolomo_known'] = False
        sub_menu_data['lolomo_contexts'] = None
        sub_menu_data['content_type'] = g.CONTENT_SHOW
        sub_menu_data['main_menu'] = menu_data['main_menu'] if menu_data.get('main_menu') else menu_data.copy()
        g.PERSISTENT_STORAGE['sub_menus'][menu_id] = sub_menu_data
        g.PERSISTENT_STORAGE['menu_titles'][menu_id] = common.get_local_string(30089)
        g.PERSISTENT_STORAGE.commit()
        directory_items.insert(0,
                               (common.build_url(['genres', menu_id, genre_id],
                                                 mode=g.MODE_DIRECTORY),
                                list_item_skeleton(common.get_local_string(30089),
                                                   icon='DefaultVideoPlaylists.png',
                                                   description=common.get_local_string(30088)),
                                True))
    add_items_previous_next_page(directory_items, pathitems, video_list.perpetual_range_selector, genre_id)
    # At the moment it is not possible to make a query with results sorted for the 'mylist',
    # so we adding the sort order of kodi
    sort_type = 'sort_nothing'
    if menu_data['path'][1] == 'myList':
        sort_type = 'sort_label_ignore_folders'
    finalize_directory(directory_items, menu_data.get('content_type', g.CONTENT_SHOW),
                       title=g.get_menu_title(menu_data['path'][1]), sort_type=sort_type)
    return menu_data.get('view')


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
def build_season_listing(tvshowid, season_list, pathitems=None):
    """Build a season listing"""
    directory_items = [_create_season_item(tvshowid, seasonid_value, season,
                                           season_list)
                       for seasonid_value, season
                       in season_list.seasons.iteritems()]
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
    directory_items = [_create_episode_item(seasonid, episodeid_value, episode,
                                            episode_list)
                       for episodeid_value, episode
                       in episode_list.episodes.iteritems()]
    add_items_previous_next_page(directory_items, pathitems, episode_list.perpetual_range_selector)
    finalize_directory(directory_items, g.CONTENT_EPISODE, 'sort_episodes',
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


@custom_viewmode(g.VIEW_SHOW)
@common.time_execution(immediate=False)
def build_supplemental_listing(video_list, pathitems=None):
    """Build a supplemental listing (eg. trailers)"""
    directory_items = [_create_supplemental_item(videoid_value, video, video_list)
                       for videoid_value, video
                       in video_list.videos.iteritems()]
    finalize_directory(directory_items, g.CONTENT_SHOW, 'sort_label',
                       title='Trailers')


@common.time_execution(immediate=False)
def _create_supplemental_item(videoid_value, video, video_list):
    """Create a tuple that can be added to a Kodi directory that represents
    a video as listed in a videolist"""
    videoid = common.VideoId(
        **{'supplementalid': videoid_value})
    list_item = list_item_skeleton(video['title'])
    add_info(videoid, list_item, video, video_list.data)
    add_art(videoid, list_item, video)
    url = common.build_url(videoid=videoid,
                           mode=g.MODE_PLAY)
    # replaceItems still look broken because it does not remove the default ctx menu, i hope in the future Kodi fix this
    list_item.addContextMenuItems(generate_context_menu_items(videoid), replaceItems=True)
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


def add_items_previous_next_page(directory_items, pathitems, perpetual_range_selector, genre_id=None):
    if pathitems and perpetual_range_selector:
        if 'previous_start' in perpetual_range_selector:
            previous_page_url = \
                common.build_url(pathitems=pathitems,
                                 params={'perpetual_range_start': perpetual_range_selector.get('previous_start'),
                                         'genre_id':
                                             genre_id if perpetual_range_selector.get('previous_start') == 0 else None},
                                 mode=g.MODE_DIRECTORY)
            directory_items.insert(0, (previous_page_url,
                                       list_item_skeleton(common.get_local_string(30148),
                                                          customicon='FolderPagePrevious.png'), True))
        if 'next_start' in perpetual_range_selector:
            next_page_url = \
                common.build_url(pathitems=pathitems,
                                 params={'perpetual_range_start': perpetual_range_selector.get('next_start')},
                                 mode=g.MODE_DIRECTORY)
            directory_items.append((next_page_url, list_item_skeleton(common.get_local_string(30147),
                                                                      customicon='FolderPageNext.png'), True))


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
