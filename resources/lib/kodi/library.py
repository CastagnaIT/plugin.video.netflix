# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import os
import codecs

import xbmc

import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.api.shakti as api
from resources.lib.navigation import InvalidPathError

FILE_PROPS = [
    'title', 'genre', 'year', 'rating', 'duration', 'playcount', 'director',
    'tagline', 'plot', 'plotoutline', 'originaltitle', 'writer', 'studio',
    'mpaa', 'cast', 'country', 'runtime', 'set', 'showlink', 'season',
    'episode', 'showtitle', 'file', 'resume', 'tvshowid', 'setid', 'tag',
    'art', 'uniqueid']

LIBRARY_HOME = 'library'
FOLDER_MOVIES = 'movies'
FOLDER_TV = 'shows'

__LIBRARY__ = None

class ItemNotFound(Exception):
    """The requested item could not be found in the Kodi library"""
    pass

def _library():
    # pylint: disable=global-statement
    global __LIBRARY__
    if not __LIBRARY__:
        try:
            __LIBRARY__ = cache.get(cache.CACHE_LIBRARY, 'library')
        except cache.CacheMiss:
            __LIBRARY__ = {}
    return __LIBRARY__

def library_path():
    """Return the full path to the library"""
    return (common.ADDON.getSetting('customlibraryfolder')
            if common.ADDON.getSettingBool('enablelibraryfolder')
            else common.DATA_PATH)

def save_library():
    """Save the library to disk via cache"""
    if __LIBRARY__ is not None:
        cache.add(cache.CACHE_LIBRARY, 'library', __LIBRARY__,
                  ttl=cache.TTL_INFINITE, to_disk=True)

def get_item(videoid, include_props=False):
    """Find an item in the Kodi library by its Netflix videoid and return
    Kodi DBID and mediatype"""
    try:
        filepath = common.get_path(videoid.to_list(), _library())['file']
        params = {'file': filepath, 'media': 'video'}
        if include_props:
            params['properties'] = FILE_PROPS
        return common.json_rpc('Files.GetFileDetails', params)['filedetails']
    except:
        raise ItemNotFound(
            'The video with id {} is not present in the Kodi library'
            .format(videoid))

def is_in_library(videoid):
    """Return True if the video is in the local Kodi library, else False"""
    return common.get_path_safe(videoid.to_list(), _library()) is not None

def _export_movie(videoid):
    """Export a movie to the library"""
    metadata = api.metadata(videoid)
    name = '{title} ({year})'.format(
        title=metadata['video']['title'],
        year=2018)
    _export_item(videoid, library_path(), FOLDER_MOVIES, name, name)

def _export_tv(videoid):
    """Export a complete TV show to the library"""
    metadata = api.metadata(videoid)
    if videoid.mediatype == common.VideoId.SHOW:
        for season in metadata['video']['seasons']:
            _export_season(
                videoid.derive_season(season['id']), metadata, season)
    elif videoid.mediatype == common.VideoId.SEASON:
        _export_season(
            videoid, metadata, common.find_season(videoid.seasonid, metadata))
    else:
        _export_episode(
            videoid, metadata, common.find_season(videoid.seasonid, metadata),
            common.find_episode(videoid.episodeid, metadata))

def _export_season(videoid, metadata, season):
    """Export a complete season to the library"""
    for episode in season['episodes']:
        _export_episode(
            videoid.derive_episode(episode['id']), metadata, season, episode)

def _export_episode(videoid, metadata, season, episode):
    """Export a single episode to the library"""
    showname = metadata['video']['title']
    filename = 'S{:02d}E{:02d}'.format(season['seq'], episode['seq'])
    _export_item(videoid, library_path(), FOLDER_TV, showname, filename)

def _export_item(videoid, library, section, destination, filename):
    """Create strm file for an item and add it to the library"""
    destination_folder = os.path.join(library, section, destination)
    export_filename = os.path.join(destination_folder, filename + '.strm')
    try:
        os.makedirs(xbmc.translatePath(destination_folder))
        with codecs.open(xbmc.translatePath(export_filename),
                         mode='w',
                         encoding='utf-8',
                         errors='replace') as filehandle:
            filehandle.write(
                common.build_url(videoid=videoid, mode=common.MODE_PLAY))
    except OSError as exc:
        if exc.errno == os.errno.EEXIST:
            common.info('{} already exists, skipping export'
                        .format(export_filename))
        else:
            raise
    _add_to_library(videoid, export_filename)

def _add_to_library(videoid, export_filename):
    """Add an exported file to the library"""
    library_node = _library()
    for id_item in videoid.to_list():
        if id_item not in library_node:
            library_node[id_item] = {}
        library_node = library_node[id_item]
    library_node['file'] = export_filename
    save_library()

def _remove_tv(videoid):
    metadata = api.metadata(videoid)
    if videoid.mediatype == common.VideoId.SHOW:
        for season in metadata['video']['seasons']:
            _remove_season(
                videoid.derive_season(season['id']), season)
    elif videoid.mediatype == common.VideoId.SEASON:
        _remove_season(
            videoid, common.find_season(videoid.seasonid, metadata))
    else:
        _remove_item(videoid)

def _remove_season(videoid, season):
    for episode in season['episodes']:
        _remove_item(videoid.derive_episode(episode['id']))

def _remove_item(videoid):
    exported_filename = xbmc.translatePath(
        common.get_path(videoid.to_list, _library())['file'])
    parent_folder = os.path.dirname(exported_filename)
    os.remove(xbmc.translatePath(exported_filename))
    if not os.listdir(parent_folder):
        os.remove(parent_folder)
    common.remove_path(videoid.to_list(), _library())
    save_library()

def execute(pathitems, params):
    """Execute an action as specified by the path"""
    try:
        executor = ActionExecutor(params).__getattribute__(pathitems[0])
    except (AttributeError, IndexError):
        raise InvalidPathError('Unknown action {}'.format('/'.join(pathitems)))

    common.debug('Invoking action executor {}'.format(executor.__name__))

    if len(pathitems) > 1:
        executor(pathitems=pathitems[1:])
    else:
        executor()

class ActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing action executor: {}'.format(params))
        self.params = params

    @common.inject_video_id(path_offset=0)
    def export(self, videoid):
        """Export an item to the Kodi library"""
        if videoid.mediatype == common.VideoId.MOVIE:
            _export_movie(videoid)
        elif videoid.mediatype in [common.VideoId.SHOW,
                                   common.VideoId.SEASON,
                                   common.VideoId.EPISODE]:
            _export_tv(videoid)
        else:
            raise ValueError('Cannot export {}'.format(videoid))

    @common.inject_video_id(path_offset=0)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        if videoid.mediatype == common.VideoId.MOVIE:
            _remove_item(videoid)
        elif videoid.mediatype in [common.VideoId.SHOW,
                                   common.VideoId.SEASON,
                                   common.VideoId.EPISODE]:
            _remove_tv(videoid)
        else:
            raise ValueError('Cannot remove {}'.format(videoid))

    @common.inject_video_id(path_offset=0)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        # TODO: Implement library updates
        pass
