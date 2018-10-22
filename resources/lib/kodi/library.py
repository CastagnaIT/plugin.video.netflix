# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.cache as cache
from resources.lib.navigation import InvalidPathError

FILE_PROPS = [
    'title', 'genre', 'year', 'rating', 'duration', 'playcount', 'director',
    'tagline', 'plot', 'plotoutline', 'originaltitle', 'writer', 'studio',
    'mpaa', 'cast', 'country', 'runtime', 'set', 'showlink', 'season',
    'episode', 'showtitle', 'file', 'resume', 'tvshowid', 'setid', 'tag',
    'art', 'uniqueid']

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

def save_library():
    """Save the library to disk via cache"""
    cache.add(cache.CACHE_LIBRARY, 'library', __LIBRARY__,
              ttl=cache.TTL_INFINITE, to_disk=True)

def get_item(videoid, include_props=False):
    """Find an item in the Kodi library by its Netflix videoid and return
    Kodi DBID and mediatype"""
    try:
        filepath = common.get_path(videoid, _library())['file']
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
    return common.get_path_safe(videoid, _library()) is not None

def execute(pathitems, params):
    """Execute an action as specified by the path"""
    try:
        executor = ActionExecutor(params).__getattribute__(pathitems[0])
    except (AttributeError, IndexError):
        raise InvalidPathError('Unknown action {}'.format('/'.join(pathitems)))

    common.debug('Invoking action executor {}'.format(executor.__name__))

    if len(pathitems) > 1:
        executor((pathitems[1:]))
    else:
        executor()

class ActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing action executor: {}'.format(params))
        self.params = params

    def export(self, pathitems):
        """Export an item to the Kodi library"""
        # TODO: Implement library export
        pass

    def remove(self, pathitems):
        """Remove an item from the Kodi library"""
        # TODO: Implement library removal
        pass

    def update(self, pathitems):
        """Update an item in the Kodi library"""
        # TODO: Implement library updates
        pass
