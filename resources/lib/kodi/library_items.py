# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Kodi library integration: items library

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
import re
import xml.etree.ElementTree as ET

import xbmc
import xbmcvfs

import resources.lib.api.api_requests as api
import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.api.exceptions import MetadataNotAvailable
from resources.lib.globals import g

try:  # Kodi >= 19
    from xbmcvfs import makeLegalFilename  # pylint: disable=ungrouped-imports
except ImportError:  # Kodi 18
    from xbmc import makeLegalFilename  # pylint: disable=ungrouped-imports

LIBRARY_HOME = 'library'
FOLDER_MOVIES = 'movies'
FOLDER_TV = 'shows'
ILLEGAL_CHARACTERS = '[<|>|"|?|$|!|:|#|*]'


class ItemNotFound(Exception):
    """The requested item could not be found in the Kodi library"""


def get_item(videoid):
    """Find an item in the Kodi library by its Netflix videoid and return Kodi DBID and mediatype"""
    try:
        file_path, media_type = _get_library_entry(videoid)
        return _get_item(media_type, file_path)
    except (KeyError, IndexError, ItemNotFound):
        raise ItemNotFound('The video with id {} is not present in the Kodi library'.format(videoid))


def _get_library_entry(videoid):
    if videoid.mediatype == common.VideoId.MOVIE:
        file_path = g.SHARED_DB.get_movie_filepath(videoid.value)
        media_type = videoid.mediatype
    elif videoid.mediatype == common.VideoId.EPISODE:
        file_path = g.SHARED_DB.get_episode_filepath(videoid.tvshowid,
                                                     videoid.seasonid,
                                                     videoid.episodeid)
        media_type = videoid.mediatype
    elif videoid.mediatype == common.VideoId.SHOW:
        file_path = g.SHARED_DB.get_random_episode_filepath_from_tvshow(videoid.value)
        media_type = common.VideoId.EPISODE
    elif videoid.mediatype == common.VideoId.SEASON:
        file_path = g.SHARED_DB.get_random_episode_filepath_from_season(videoid.tvshowid,
                                                                        videoid.seasonid)
        media_type = common.VideoId.EPISODE
    else:
        # Items of other mediatype are never in library
        raise ItemNotFound
    if file_path is None:
        raise ItemNotFound
    return file_path, media_type


def _get_item(mediatype, filename):
    # To ensure compatibility with previously exported items,
    # make the filename legal
    fname = makeLegalFilename(filename)
    untranslated_path = os.path.dirname(g.py2_decode(fname))
    translated_path = os.path.dirname(g.py2_decode(xbmc.translatePath(fname)))
    shortname = os.path.basename(g.py2_decode(xbmc.translatePath(fname)))
    # We get the data from Kodi library using filters.
    # This is much faster than loading all episodes in memory

    # First build the path filter, we may have to search in both special and translated path
    path_filter = {'field': 'path', 'operator': 'startswith', 'value': translated_path} \
        if fname[:10] != 'special://' \
        else {'or': [
            {'field': 'path', 'operator': 'startswith', 'value': translated_path},
            {'field': 'path', 'operator': 'startswith', 'value': untranslated_path}
        ]}

    # Now build the all request and call the json-rpc function through common.get_library_items
    library_item = common.get_library_items(
        mediatype,
        {'and': [
            path_filter,
            {'field': 'filename', 'operator': 'is', 'value': shortname}
        ]})[0]
    if not library_item:
        raise ItemNotFound
    return common.get_library_item_details(
        mediatype, library_item[mediatype + 'id'])


def get_previously_exported_items():
    """Return a list of movie or tvshow VideoIds for items that were exported in
    the old storage format"""
    result = []
    videoid_pattern = re.compile('video_id=(\\d+)')
    for folder in _lib_folders(FOLDER_MOVIES) + _lib_folders(FOLDER_TV):
        for filename in xbmcvfs.listdir(folder)[1]:
            filepath = g.py2_decode(makeLegalFilename('/'.join([folder, filename])))
            if filepath.endswith('.strm'):
                common.debug('Trying to migrate {}', filepath)
                try:
                    # Only get a VideoId from the first file in each folder.
                    # For shows, all episodes will result in the same VideoId
                    # and movies only contain one file
                    result.append(
                        _get_root_videoid(filepath, videoid_pattern))
                except MetadataNotAvailable:
                    common.warn('Metadata not available, item skipped')
                except (AttributeError, IndexError):
                    common.warn('Item does not conform to old format')
                break
    return result


def _lib_folders(section):
    section_dir = g.py2_decode(xbmc.translatePath(makeLegalFilename('/'.join([library_path(), section]))))
    return [g.py2_decode(makeLegalFilename('/'.join([section_dir, folder.decode('utf-8')])))
            for folder
            in xbmcvfs.listdir(section_dir)[0]]


def _get_root_videoid(filename, pattern):
    match = re.search(pattern,
                      xbmcvfs.File(filename, 'r').read().decode('utf-8').split('\n')[-1])
    metadata = api.get_metadata(
        common.VideoId(videoid=match.groups()[0]))[0]
    if metadata['type'] == 'show':
        return common.VideoId(tvshowid=metadata['id'])
    return common.VideoId(movieid=metadata['id'])


# We need to differentiate task_handler for task creation, but we use the same export method
def export_new_item(item_task, library_home):
    export_item(item_task, library_home)


def export_item(item_task, library_home):
    """Create strm file for an item and add it to the library"""
    # Paths must be legal to ensure NFS compatibility
    destination_folder = g.py2_decode(makeLegalFilename('/'.join(
        [library_home, item_task['section'], item_task['destination']])))
    _create_destination_folder(destination_folder)
    if item_task['is_strm']:
        export_filename = g.py2_decode(makeLegalFilename('/'.join(
            [destination_folder, item_task['filename'] + '.strm'])))
        _add_to_library(item_task['videoid'], export_filename, (item_task['nfo_data'] is not None))
        _write_strm_file(item_task, export_filename)
    if item_task['nfo_data'] is not None:
        nfo_filename = g.py2_decode(makeLegalFilename('/'.join(
            [destination_folder, item_task['filename'] + '.nfo'])))
        _write_nfo_file(item_task['nfo_data'], nfo_filename)
    common.debug('Exported {}', item_task['title'])


def _create_destination_folder(destination_folder):
    """Create destination folder, ignore error if it already exists"""
    if not common.folder_exists(destination_folder):
        xbmcvfs.mkdirs(destination_folder)


def _add_to_library(videoid, export_filename, nfo_export, exclude_update=False):
    """Add an exported file to the library"""
    if videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.set_tvshow(videoid.tvshowid, nfo_export, exclude_update)
        g.SHARED_DB.insert_season(videoid.tvshowid, videoid.seasonid)
        g.SHARED_DB.insert_episode(videoid.tvshowid, videoid.seasonid,
                                   videoid.value, export_filename)
    elif videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.set_movie(videoid.value, export_filename, nfo_export)


def _write_strm_file(item_task, export_filename):
    """Write the playable URL to a strm file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(export_filename), 'wb')
    try:
        filehandle.write(bytearray(common.build_url(videoid=item_task['videoid'],
                                                    mode=g.MODE_PLAY).encode('utf-8')))
    finally:
        filehandle.close()


def _write_nfo_file(nfo_data, nfo_filename):
    """Write the NFO file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(nfo_filename), 'wb')
    try:
        filehandle.write(bytearray('<?xml version=\'1.0\' encoding=\'UTF-8\'?>'.encode('utf-8')))
        filehandle.write(bytearray(ET.tostring(nfo_data, encoding='utf-8', method='xml')))
    finally:
        filehandle.close()


def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument, broad-except

    common.info('Removing {} from library', item_task['title'])

    exported_filename = g.py2_decode(xbmc.translatePath(item_task['filepath']))
    videoid = item_task['videoid']
    common.debug('VideoId: {}', videoid)
    try:
        parent_folder = g.py2_decode(xbmc.translatePath(os.path.dirname(exported_filename)))
        if xbmcvfs.exists(exported_filename):
            xbmcvfs.delete(exported_filename)
        else:
            common.warn('Cannot delete {}, file does not exist', exported_filename)
        # Remove the NFO files if exists
        nfo_file = os.path.splitext(exported_filename)[0] + '.nfo'
        if xbmcvfs.exists(nfo_file):
            xbmcvfs.delete(nfo_file)
        dirs, files = xbmcvfs.listdir(parent_folder)
        tvshow_nfo_file = g.py2_decode(makeLegalFilename('/'.join([parent_folder, 'tvshow.nfo'])))
        # Remove tvshow_nfo_file only when is the last file
        # (users have the option of removing even single seasons)
        if xbmcvfs.exists(tvshow_nfo_file) and not dirs and len(files) == 1:
            xbmcvfs.delete(tvshow_nfo_file)
            # Delete parent folder
            xbmcvfs.rmdir(parent_folder)
        # Delete parent folder when empty
        if not dirs and not files:
            xbmcvfs.rmdir(parent_folder)

        _remove_videoid_from_db(videoid)
    except ItemNotFound:
        common.warn('The video with id {} not exists in the database', videoid)
    except Exception as exc:
        import traceback
        common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        ui.show_addon_error_info(exc)


def _remove_videoid_from_db(videoid):
    """Removes records from database in relation to a videoid"""
    if videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.delete_movie(videoid.value)
    elif videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.delete_episode(videoid.tvshowid, videoid.seasonid, videoid.episodeid)


def library_path():
    """Return the full path to the library"""
    return (g.ADDON.getSetting('customlibraryfolder')
            if g.ADDON.getSettingBool('enablelibraryfolder')
            else g.DATA_PATH)
