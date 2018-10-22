# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import resources.lib.common as common

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
        __LIBRARY__ = common.PersistentStorage('library')
    return __LIBRARY__

def find_item(videoid, include_props=False):
    """Find an item in the Kodi library by its Netflix videoid and return
    Kodi DBID and mediatype"""
    try:
        filepath = (_library()[videoid[0]][videoid[1]][videoid[2]]['file']
                    if isinstance(videoid, tuple)
                    else _library()[videoid])
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
    try:
        find_item(videoid)
    except ItemNotFound:
        return False
    return True
