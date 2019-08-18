# -*- coding: utf-8 -*-
"""Defines upgrade actions"""
from __future__ import unicode_literals

import os

import xbmc
import xbmcvfs

import resources.lib.common as common
import resources.lib.kodi.library as library
from resources.lib.globals import g

try:
    import cPickle as pickle
except ImportError:
    import pickle


def migrate_library_to_db():
    common.debug('Migrate library from file cache library.ndb2 to database')
    file_loc = [g.DATA_PATH, 'library.ndb2']
    library_file = xbmc.translatePath(os.path.join(*file_loc))

    if xbmcvfs.exists(library_file):
        handle = xbmcvfs.File(library_file, 'r')
        lib = pickle.loads(handle.read())
        handle.close()
        for item in lib['content'].values():
            videoid = item['videoid'].convert_old_videoid_type()
            if videoid.mediatype == common.VideoId.MOVIE:
                library.add_to_library(videoid, item['file'], False, False)
            elif videoid.mediatype == common.VideoId.SHOW:
                for season_key in item.keys():
                    if season_key not in ['videoid', 'nfo_export', 'exclude_from_update']:
                        for episode_key in item[season_key].keys():
                            if episode_key not in ['videoid', 'nfo_export']:
                                library.add_to_library(
                                    item[season_key][episode_key]['videoid'].convert_old_videoid_type(),
                                    item[season_key][episode_key]['file'],
                                    item.get('nfo_export', False),
                                    item.get('exclude_from_update', False))
        xbmcvfs.rename(library_file, library_file + '.bak')
