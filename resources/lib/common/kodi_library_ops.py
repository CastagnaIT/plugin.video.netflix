# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for Kodi library operations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os

import xbmcvfs

from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .exceptions import ItemNotFound, DBRecordNotExistError
from .kodi_ops import json_rpc, get_local_string, json_rpc_multi
from .videoid import VideoId


LIBRARY_PROPS = {
    'episode': ['title', 'plot', 'writer', 'playcount', 'director', 'season',
                'episode', 'originaltitle', 'showtitle', 'lastplayed', 'file',
                'resume', 'dateadded', 'art', 'userrating', 'firstaired', 'runtime'],
    'movie': ['title', 'genre', 'year', 'director', 'trailer',
              'tagline', 'plot', 'plotoutline', 'originaltitle', 'lastplayed',
              'playcount', 'writer', 'studio', 'mpaa', 'country',
              'imdbnumber', 'runtime', 'set', 'showlink', 'premiered',
              'top250', 'file', 'sorttitle', 'resume', 'setid', 'dateadded',
              'tag', 'art', 'userrating']
}


def update_library_item_details(dbtype, dbid, details):
    """Update properties of an item in the Kodi library"""
    method = f'VideoLibrary.Set{dbtype.capitalize()}Details'
    params = {f'{dbtype}id': dbid}
    params.update(details)
    return json_rpc(method, params)


def get_library_items(dbtype, video_filter=None):
    """Return a list of all items in the Kodi library that are of type dbtype (either movie or episode)"""
    method = f'VideoLibrary.Get{dbtype.capitalize()}s'
    params = {'properties': ['file']}
    if video_filter:
        params.update({'filter': video_filter})
    return json_rpc(method, params)[dbtype + 's']


def get_library_item_details(dbtype, itemid):
    """Return details for an item from the Kodi library"""
    method = f'VideoLibrary.Get{dbtype.capitalize()}Details'
    params = {
        dbtype + 'id': itemid,
        'properties': LIBRARY_PROPS[dbtype]}
    return json_rpc(method, params)[dbtype + 'details']


def scan_library(path=''):
    """
    Start a Kodi library scanning in a specified folder to find new items
    :param path: Update only the library elements in the specified path (fast processing)
    """
    method = 'VideoLibrary.Scan'
    params = {'directory': xbmcvfs.makeLegalFilename(xbmcvfs.translatePath(path))}
    return json_rpc(method, params)


def clean_library(show_dialog=True, path=''):
    """
    Start a Kodi library cleaning to remove non-existing items
    :param show_dialog: True a progress dialog is shown
    :param path: Clean only the library elements in the specified path (fast processing)
    """
    method = 'VideoLibrary.Clean'
    params = {'content': 'video',
              'showdialogs': show_dialog}
    if path:
        params['directory'] = xbmcvfs.makeLegalFilename(xbmcvfs.translatePath(path))
    return json_rpc(method, params)


def get_library_item_by_videoid(videoid):
    """Find an item in the Kodi library by its Netflix videoid and return Kodi DBID and mediatype"""
    try:
        # Obtain a file path for this videoid from add-on library database
        file_path, media_type = _get_videoid_file_path(videoid)
        # Ask to Kodi to find this file path in Kodi library database, and get all item details
        return _get_item_details_from_kodi(media_type, file_path)
    except (KeyError, IndexError, ItemNotFound, DBRecordNotExistError) as exc:
        raise ItemNotFound(f'The video with id {videoid} is not present in the Kodi library') from exc


def _get_videoid_file_path(videoid):
    """Get a file path of a file referred to the videoid (to tvshow/season will be taken a random file episode)"""
    if videoid.mediatype == VideoId.MOVIE:
        file_path = G.SHARED_DB.get_movie_filepath(videoid.value)
        media_type = videoid.mediatype
    elif videoid.mediatype == VideoId.EPISODE:
        file_path = G.SHARED_DB.get_episode_filepath(videoid.tvshowid,
                                                     videoid.seasonid,
                                                     videoid.episodeid)
        media_type = videoid.mediatype
    elif videoid.mediatype == VideoId.SHOW:
        file_path = G.SHARED_DB.get_random_episode_filepath_from_tvshow(videoid.value)
        media_type = VideoId.EPISODE
    elif videoid.mediatype == VideoId.SEASON:
        file_path = G.SHARED_DB.get_random_episode_filepath_from_season(videoid.tvshowid,
                                                                        videoid.seasonid)
        media_type = VideoId.EPISODE
    else:
        # Items of other mediatype are never in library
        raise ItemNotFound
    return file_path, media_type


def _get_item_details_from_kodi(mediatype, file_path):
    """Get a Kodi library item with details (from Kodi database) by searching with the file path"""
    # To ensure compatibility with previously exported items, make the filename legal
    file_path = xbmcvfs.makeLegalFilename(file_path)
    dir_path = os.path.dirname(xbmcvfs.translatePath(file_path))
    filename = os.path.basename(xbmcvfs.translatePath(file_path))
    # We get the data from Kodi library using filters, this is much faster than loading all episodes in memory.
    if file_path[:10] == 'special://':
        # If the path is special, search with real directory path and also special path
        special_dir_path = os.path.dirname(file_path)
        path_filter = {'or': [{'field': 'path', 'operator': 'startswith', 'value': dir_path},
                              {'field': 'path', 'operator': 'startswith', 'value': special_dir_path}]}
    else:
        path_filter = {'field': 'path', 'operator': 'startswith', 'value': dir_path}
    # Now build the all request and call the json-rpc function through get_library_items
    library_items = get_library_items(
        mediatype,
        {'and': [path_filter, {'field': 'filename', 'operator': 'is', 'value': filename}]}
    )
    if not library_items:
        raise ItemNotFound
    return get_library_item_details(mediatype, library_items[0][mediatype + 'id'])


def remove_videoid_from_kodi_library(videoid):
    """Remove an item from the Kodi library database (not related files)"""
    try:
        # Get a single file result by searching by videoid
        kodi_library_items = [get_library_item_by_videoid(videoid)]
        LOG.debug('Removing {} ({}) from Kodi library',
                  videoid,
                  kodi_library_items[0].get('showtitle', kodi_library_items[0]['title']))
        media_type = videoid.mediatype
        if videoid.mediatype in [VideoId.SHOW, VideoId.SEASON]:
            # Retrieve the all episodes in the export folder
            tvshow_path = os.path.dirname(kodi_library_items[0]['file'])
            filters = {'and': [
                {'field': 'path', 'operator': 'startswith',
                 'value': tvshow_path},
                {'field': 'filename', 'operator': 'endswith', 'value': '.strm'}
            ]}
            if videoid.mediatype == VideoId.SEASON:
                # Use the single file result to figure out what the season is,
                # then add a season filter to get only the episodes of the specified season
                filters['and'].append({'field': 'season', 'operator': 'is',
                                       'value': str(kodi_library_items[0]['season'])})
            kodi_library_items = get_library_items(VideoId.EPISODE, filters)
            media_type = VideoId.EPISODE
        rpc_params = {
            'movie': ['VideoLibrary.RemoveMovie', 'movieid'],
            # We should never remove an entire show
            # 'show': ['VideoLibrary.RemoveTVShow', 'tvshowid'],
            # Instead we delete all episodes listed in the JSON query above
            'show': ['VideoLibrary.RemoveEpisode', 'episodeid'],
            'season': ['VideoLibrary.RemoveEpisode', 'episodeid'],
            'episode': ['VideoLibrary.RemoveEpisode', 'episodeid']
        }
        list_rpc_params = []
        # Collect multiple json-rpc commands
        for item in kodi_library_items:
            params = rpc_params[media_type]
            list_rpc_params.append({params[1]: item[params[1]]})
        rpc_method = rpc_params[media_type][0]
        # Execute all the json-rpc commands in one call
        json_rpc_multi(rpc_method, list_rpc_params)
    except ItemNotFound:
        LOG.warn('Cannot remove {} from Kodi library, item not present', videoid)
    except KeyError as exc:
        from resources.lib.kodi import ui
        ui.show_notification(get_local_string(30120), time=7500)
        LOG.error('Cannot remove {} from Kodi library, mediatype not supported', exc)
