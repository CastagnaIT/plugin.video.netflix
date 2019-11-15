# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import absolute_import, division, unicode_literals

import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from functools import wraps

import xbmc
import xbmcvfs

import resources.lib.api.shakti as api
import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import (VidLibProp)
from resources.lib.globals import g

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

LIBRARY_HOME = 'library'
FOLDER_MOVIES = 'movies'
FOLDER_TV = 'shows'
ILLEGAL_CHARACTERS = '[<|>|"|?|$|!|:|#|*]'


class ItemNotFound(Exception):
    """The requested item could not be found in the Kodi library"""


def library_path():
    """Return the full path to the library"""
    return (g.ADDON.getSetting('customlibraryfolder')
            if g.ADDON.getSettingBool('enablelibraryfolder')
            else g.DATA_PATH)


@common.time_execution(immediate=False)
def get_item(videoid):
    """Find an item in the Kodi library by its Netflix videoid and return
    Kodi DBID and mediatype"""
    # pylint: disable=broad-except
    try:
        file_path, media_type = _get_library_entry(videoid)
        return _get_item(media_type, file_path)
    except (KeyError, AttributeError, IndexError, ItemNotFound):
        raise ItemNotFound(
            'The video with id {} is not present in the Kodi library'
            .format(videoid))


@common.time_execution(immediate=False)
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


@common.time_execution(immediate=False)
def _get_item(mediatype, filename):
    # To ensure compatibility with previously exported items,
    # make the filename legal
    fname = xbmc.makeLegalFilename(filename)
    untranslated_path = os.path.dirname(fname).decode("utf-8")
    translated_path = os.path.dirname(xbmc.translatePath(fname).decode("utf-8"))
    shortname = os.path.basename(xbmc.translatePath(fname).decode("utf-8"))
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


def list_contents():
    """Return a list of all video IDs (movies, shows)
    contained in the library"""
    return g.SHARED_DB.get_all_video_id_list()


def is_in_library(videoid):
    """Return True if the video is in the local Kodi library, else False"""
    if videoid.mediatype == common.VideoId.MOVIE:
        return g.SHARED_DB.movie_id_exists(videoid.value)
    if videoid.mediatype == common.VideoId.SHOW:
        return g.SHARED_DB.tvshow_id_exists(videoid.value)
    if videoid.mediatype == common.VideoId.SEASON:
        return g.SHARED_DB.season_id_exists(videoid.tvshowid,
                                            videoid.seasonid)
    if videoid.mediatype == common.VideoId.EPISODE:
        return g.SHARED_DB.episode_id_exists(videoid.tvshowid,
                                             videoid.seasonid,
                                             videoid.episodeid)
    raise common.InvalidVideoId('videoid {} type not implemented'.format(videoid))


def show_excluded_from_auto_update(videoid):
    """Return true if the videoid is excluded from auto-update"""
    return g.SHARED_DB.get_tvshow_property(videoid.value, VidLibProp['exclude_update'], False)


@common.time_execution(immediate=False)
def exclude_show_from_auto_update(videoid, exclude):
    """Set if a tvshow is excluded from auto-update"""
    g.SHARED_DB.set_tvshow_property(videoid.value, VidLibProp['exclude_update'], exclude)


def update_kodi_library(library_operation):
    """Decorator that ensures an update of the Kodi libarary"""

    @wraps(library_operation)
    def kodi_library_update_wrapper(videoid, task_handler, *args, **kwargs):
        """Either trigger an update of the Kodi library or remove the
        items associated with videoid, depending on the invoked task_handler"""
        is_remove = task_handler == [remove_item]
        if is_remove:
            _remove_from_kodi_library(videoid)
        library_operation(videoid, task_handler, *args, **kwargs)
        if not is_remove:
            # Update Kodi library through service
            # This prevents a second call to cancel the update
            common.debug('Notify service to update the library')
            common.send_signal(common.Signals.LIBRARY_UPDATE_REQUESTED)

    return kodi_library_update_wrapper


def _remove_from_kodi_library(videoid):
    """Remove an item from the Kodi library."""
    common.info('Removing {} videoid from Kodi library', videoid)
    try:
        kodi_library_items = [get_item(videoid)]
        if videoid.mediatype == common.VideoId.SHOW or videoid.mediatype == common.VideoId.SEASON:
            # Retrieve the all episodes in the export folder
            filters = {'and': [
                {'field': 'path', 'operator': 'startswith',
                 'value': os.path.dirname(kodi_library_items[0]['file'])},
                {'field': 'filename', 'operator': 'endswith', 'value': '.strm'}
            ]}
            if videoid.mediatype == common.VideoId.SEASON:
                # Add a season filter in case we just want to remove a season
                filters['and'].append({'field': 'season', 'operator': 'is',
                                       'value': str(kodi_library_items[0]['season'])})
            kodi_library_items = common.get_library_items(common.VideoId.EPISODE, filters)
        for item in kodi_library_items:
            rpc_params = {
                'movie': ['VideoLibrary.RemoveMovie', 'movieid'],
                # We should never remove an entire show
                # 'show': ['VideoLibrary.RemoveTVShow', 'tvshowid'],
                # Instead we delete all episodes listed in the JSON query above
                'show': ['VideoLibrary.RemoveEpisode', 'episodeid'],
                'season': ['VideoLibrary.RemoveEpisode', 'episodeid'],
                'episode': ['VideoLibrary.RemoveEpisode', 'episodeid']
            }[videoid.mediatype]
            common.debug(item)
            common.json_rpc(rpc_params[0],
                            {rpc_params[1]: item[rpc_params[1]]})
    except ItemNotFound:
        common.warn('Cannot remove {} from Kodi library, item not present', videoid)
    except KeyError as exc:
        ui.show_notification(common.get_local_string(30120), time=7500)
        common.warn('Cannot remove {} from Kodi library, Kodi does not support this (yet)', exc)


@common.time_execution(immediate=False)
def purge():
    """Purge all items exported to Kodi library and delete internal library database"""
    common.info('Purging internal database and kodi library')
    for videoid_value in g.SHARED_DB.get_movies_id_list():
        videoid = common.VideoId.from_path([common.VideoId.MOVIE, videoid_value])
        execute_library_tasks(videoid, [remove_item],
                              common.get_local_string(30030),
                              sync_mylist=False)
    for videoid_value in g.SHARED_DB.get_tvshows_id_list():
        videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
        execute_library_tasks(videoid, [remove_item],
                              common.get_local_string(30030),
                              sync_mylist=False)
    # If for some reason such as improper use of the add-on, unexpected error or other
    # has caused inconsistencies with the contents of the database or stored files,
    # make sure that everything is removed
    g.SHARED_DB.purge_library()
    for folder_name in [FOLDER_MOVIES, FOLDER_TV]:
        section_dir = xbmc.translatePath(
            xbmc.makeLegalFilename('/'.join([library_path(), folder_name])))
        common.delete_folder_contents(section_dir, delete_subfolders=True)


@common.time_execution(immediate=False)
def compile_tasks(videoid, task_handler, nfo_settings=None):
    """Compile a list of tasks for items based on the videoid"""
    common.debug('Compiling library tasks for {}', videoid)

    if task_handler == export_item:
        metadata = api.metadata(videoid)
        if videoid.mediatype == common.VideoId.MOVIE:
            return _create_export_movie_task(videoid, metadata[0], nfo_settings)
        if videoid.mediatype in common.VideoId.TV_TYPES:
            return _create_export_tv_tasks(videoid, metadata, nfo_settings)
        raise ValueError('Cannot handle {}'.format(videoid))

    if task_handler == export_new_item:
        metadata = api.metadata(videoid, True)
        return _create_new_episodes_tasks(videoid, metadata, nfo_settings)

    if task_handler == remove_item:
        if videoid.mediatype == common.VideoId.MOVIE:
            return _create_remove_movie_task(videoid)
        if videoid.mediatype == common.VideoId.SHOW:
            return _compile_remove_tvshow_tasks(videoid)
        if videoid.mediatype == common.VideoId.SEASON:
            return _compile_remove_season_tasks(videoid)
        if videoid.mediatype == common.VideoId.EPISODE:
            return _create_remove_episode_task(videoid)

    common.debug('compile_tasks: task_handler {} did not match any task for {}',
                 task_handler, videoid)
    return None


def _create_export_movie_task(videoid, movie, nfo_settings):
    """Create a task for a movie"""
    # Reset NFO export to false if we never want movies nfo
    name = '{title} ({year})'.format(title=movie['title'], year=movie['year'])
    return [_create_export_item_task(name, FOLDER_MOVIES, videoid, name, name,
                                     nfo.create_movie_nfo(movie) if
                                     nfo_settings and nfo_settings.export_movie_enabled else None)]


def _create_export_tv_tasks(videoid, metadata, nfo_settings):
    """Create tasks for a show, season or episode.
    If videoid represents a show or season, tasks will be generated for
    all contained seasons and episodes"""
    if videoid.mediatype == common.VideoId.SHOW:
        tasks = _compile_export_show_tasks(videoid, metadata[0], nfo_settings)
    elif videoid.mediatype == common.VideoId.SEASON:
        tasks = _compile_export_season_tasks(videoid,
                                             metadata[0],
                                             common.find(int(videoid.seasonid),
                                                         'id',
                                                         metadata[0]['seasons']),
                                             nfo_settings)
    else:
        tasks = [_create_export_episode_task(videoid, *metadata, nfo_settings=nfo_settings)]

    if nfo_settings and nfo_settings.export_full_tvshow:
        # Create tvshow.nfo file
        # In episode metadata, show data is at 3rd position,
        # while it's at first position in show metadata.
        # Best is to enumerate values to find the correct key position
        key_index = -1
        for i, item in enumerate(metadata):
            if item and item.get('type', None) == 'show':
                key_index = i
        if key_index > -1:
            tasks.append(_create_export_item_task('tvshow.nfo', FOLDER_TV, videoid,
                                                  metadata[key_index]['title'],
                                                  'tvshow',
                                                  nfo.create_show_nfo(metadata[key_index]),
                                                  False))
    return tasks


def _compile_export_show_tasks(videoid, show, nfo_settings):
    """Compile a list of task items for all episodes of all seasons
    of a tvshow"""
    # This nested comprehension is nasty but necessary. It flattens
    # the task lists for each season into one list
    return [task for season in show['seasons']
            for task in _compile_export_season_tasks(
                videoid.derive_season(season['id']), show, season, nfo_settings)]


def _compile_export_season_tasks(videoid, show, season, nfo_settings):
    """Compile a list of task items for all episodes in a season"""
    return [_create_export_episode_task(videoid.derive_episode(episode['id']),
                                        episode, season, show, nfo_settings)
            for episode in season['episodes']]


def _create_export_episode_task(videoid, episode, season, show, nfo_settings):
    """Export a single episode to the library"""
    filename = 'S{:02d}E{:02d}'.format(season['seq'], episode['seq'])
    title = ' - '.join((show['title'], filename, episode['title']))
    return _create_export_item_task(
        title, FOLDER_TV, videoid, show['title'], filename,
        nfo.create_episode_nfo(episode, season, show)
        if nfo_settings and nfo_settings.export_tvshow_enabled else None)


def _create_export_item_task(title, section, videoid, destination, filename, nfo_data=None,
                             is_strm=True):
    """Create a single task item"""
    return {
        'title': title,
        'section': section,
        'videoid': videoid,
        'destination': re.sub(ILLEGAL_CHARACTERS, '', destination),
        'filename': re.sub(ILLEGAL_CHARACTERS, '', filename),
        'nfo_data': nfo_data,
        'is_strm': is_strm
    }


def _create_new_episodes_tasks(videoid, metadata, nfo_settings=None):
    tasks = []
    if metadata and 'seasons' in metadata[0]:
        for season in metadata[0]['seasons']:
            if not nfo_settings:
                nfo_export = g.SHARED_DB.get_tvshow_property(videoid.value,
                                                             VidLibProp['nfo_export'], False)
                nfo_settings = nfo.NFOSettings(nfo_export)

            if g.SHARED_DB.season_id_exists(videoid.value, season['id']):
                # The season exists, try to find any missing episode
                for episode in season['episodes']:
                    if not g.SHARED_DB.episode_id_exists(
                            videoid.value, season['id'], episode['id']):
                        tasks.append(_create_export_episode_task(
                            videoid=videoid.derive_season(
                                season['id']).derive_episode(episode['id']),
                            episode=episode,
                            season=season,
                            show=metadata[0],
                            nfo_settings=nfo_settings
                        ))
                        common.debug('Auto exporting episode {}', episode['id'])
            else:
                # The season does not exist, build task for the season
                tasks += _compile_export_season_tasks(
                    videoid=videoid.derive_season(season['id']),
                    show=metadata[0],
                    season=season,
                    nfo_settings=nfo_settings
                )
                common.debug('Auto exporting season {}', season['id'])
    return tasks


def _create_remove_movie_task(videoid):
    filepath = g.SHARED_DB.get_movie_filepath(videoid.value)
    title = os.path.splitext(os.path.basename(filepath))[0]
    return [_create_remove_item_task(title, filepath, videoid)]


def _compile_remove_tvshow_tasks(videoid):
    row_results = g.SHARED_DB.get_all_episodes_ids_and_filepath_from_tvshow(videoid.value)
    return _create_remove_tv_tasks(row_results)


def _compile_remove_season_tasks(videoid):
    row_results = g.SHARED_DB.get_all_episodes_ids_and_filepath_from_season(
        videoid.tvshowid, videoid.seasonid)
    return _create_remove_tv_tasks(row_results)


def _create_remove_episode_task(videoid):
    filepath = g.SHARED_DB.get_episode_filepath(
        videoid.tvshowid, videoid.seasonid, videoid.episodeid)
    return [_create_remove_item_task(
        _episode_title_from_path(filepath),
        filepath, videoid)]


def _create_remove_tv_tasks(row_results):
    return [_create_remove_item_task(_episode_title_from_path(row['FilePath']),
                                     row['FilePath'],
                                     common.VideoId.from_dict(
                                         {'mediatype': common.VideoId.SHOW,
                                          'tvshowid': row['TvShowID'],
                                          'seasonid': row['SeasonID'],
                                          'episodeid': row['EpisodeID']}))
            for row in row_results]


def _create_remove_item_task(title, filepath, videoid):
    """Create a single task item"""
    return {
        'title': title,
        'filepath': filepath,
        'videoid': videoid
    }


def _episode_title_from_path(filepath):
    fname = os.path.splitext(os.path.basename(filepath))[0]
    path = os.path.split(os.path.split(filepath)[0])[1]
    return '{} - {}'.format(path, fname)


# We need to differentiate task_handler for task creation, but we use the same export method
def export_new_item(item_task, library_home):
    export_item(item_task, library_home)


@common.time_execution(immediate=False)
def export_item(item_task, library_home):
    """Create strm file for an item and add it to the library"""
    # Paths must be legal to ensure NFS compatibility
    destination_folder = g.py2_decode(xbmc.makeLegalFilename('/'.join(
        [library_home, item_task['section'], item_task['destination']])))
    _create_destination_folder(destination_folder)
    if item_task['is_strm']:
        export_filename = g.py2_decode(xbmc.makeLegalFilename('/'.join(
            [destination_folder, item_task['filename'] + '.strm'])))
        add_to_library(item_task['videoid'], export_filename, (item_task['nfo_data'] is not None))
        _write_strm_file(item_task, export_filename)
    if item_task['nfo_data'] is not None:
        nfo_filename = g.py2_decode(xbmc.makeLegalFilename('/'.join(
            [destination_folder, item_task['filename'] + '.nfo'])))
        _write_nfo_file(item_task['nfo_data'], nfo_filename)
    common.debug('Exported {}', item_task['title'])


def _create_destination_folder(destination_folder):
    """Create destination folder, ignore error if it already exists"""
    destination_folder = xbmc.translatePath(destination_folder)
    if not xbmcvfs.exists(destination_folder):
        xbmcvfs.mkdirs(destination_folder)


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


def add_to_library(videoid, export_filename, nfo_export, exclude_update=False):
    """Add an exported file to the library"""
    if videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.set_tvshow(videoid.tvshowid, nfo_export, exclude_update)
        g.SHARED_DB.insert_season(videoid.tvshowid, videoid.seasonid)
        g.SHARED_DB.insert_episode(videoid.tvshowid, videoid.seasonid,
                                   videoid.value, export_filename)
    elif videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.set_movie(videoid.value, export_filename, nfo_export)


@common.time_execution(immediate=False)
def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument, broad-except

    common.info('Removing {} from library', item_task['title'])

    exported_filename = xbmc.translatePath(item_task['filepath'])
    videoid = item_task['videoid']
    common.debug('VideoId: {}', videoid)
    try:
        parent_folder = xbmc.translatePath(os.path.dirname(exported_filename))
        if xbmcvfs.exists(exported_filename):
            xbmcvfs.delete(exported_filename)
        else:
            common.warn('Cannot delete {}, file does not exist', g.py2_decode(exported_filename))
        # Remove the NFO files if exists
        nfo_file = os.path.splitext(g.py2_decode(exported_filename))[0] + '.nfo'
        if xbmcvfs.exists(nfo_file):
            xbmcvfs.delete(nfo_file)
        dirs, files = xbmcvfs.listdir(parent_folder)
        tvshow_nfo_file = xbmc.makeLegalFilename(
            '/'.join([g.py2_decode(parent_folder), 'tvshow.nfo']))
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
        common.error(traceback.format_exc())
        ui.show_addon_error_info(exc)


def _remove_videoid_from_db(videoid):
    """Removes records from database in relation to a videoid"""
    if videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.delete_movie(videoid.value)
    elif videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.delete_episode(videoid.tvshowid, videoid.seasonid, videoid.episodeid)


def _is_auto_update_library_running():
    update = g.SHARED_DB.get_value('library_auto_update_is_running', False)
    if update:
        start_time = g.SHARED_DB.get_value('library_auto_update_start_time',
                                           datetime.utcfromtimestamp(0))
        if datetime.now() >= start_time + timedelta(hours=6):
            g.SHARED_DB.set_value('library_auto_update_is_running', False)
            common.warn('Canceling previous library update: duration >6 hours')
        else:
            common.debug('Library auto update is already running')
            return True
    return False


def sync_mylist_to_library():
    """
    Perform a full sync of Netflix "My List" with the Kodi library
    by deleting everything that was previously exported
    """
    common.info('Performing full sync of Netflix "My List" with the Kodi library')
    purge()
    nfo_settings = nfo.NFOSettings()
    nfo_settings.show_export_dialog()
    for videoid in _get_mylist_videoids():
        execute_library_tasks(videoid, [export_item],
                              common.get_local_string(30018),
                              sync_mylist=False,
                              nfo_settings=nfo_settings)


def auto_update_library(sync_with_mylist, silent):
    """
    Perform an auto update of the exported items to Kodi library,
    so check if there is new seasons/episodes.
    If sync_with_mylist is enabled the Kodi library will be also synchronized
    with the Netflix "My List".
    :param sync_with_mylist: True to enable sync with My List
    :param silent: don't display user interface while performing an operation
    :return: None
    """
    if _is_auto_update_library_running():
        return
    execute_lib_tasks_method = execute_library_tasks_silently if silent else execute_library_tasks
    common.info(
        'Starting auto update library - check updates for tv shows (sync with My List is {})',
        sync_with_mylist)
    g.SHARED_DB.set_value('library_auto_update_is_running', True)
    g.SHARED_DB.set_value('library_auto_update_start_time', datetime.now())
    try:
        videoids_to_update = []

        # Get My List videoids of the chosen profile
        mylist_videoids = _get_mylist_videoids() if sync_with_mylist else []
        # Get the list of the exported items to Kodi library
        exported_tvshows_videoids_values = g.SHARED_DB.get_tvshows_id_list()
        exported_movies_videoids_values = g.SHARED_DB.get_movies_id_list()

        if sync_with_mylist:
            # Check if tv shows have been removed from the My List
            for videoid_value in exported_tvshows_videoids_values:
                if any(videoid.value == unicode(videoid_value) for videoid in mylist_videoids):
                    continue
                # The tv show no more exist in My List so remove it from library
                videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
                execute_lib_tasks_method(videoid, [remove_item], sync_mylist=False)

            # Check if movies have been removed from the My List
            for videoid_value in exported_movies_videoids_values:
                if any(videoid.value == unicode(videoid_value) for videoid in mylist_videoids):
                    continue
                # The movie no more exist in My List so remove it from library
                videoid = common.VideoId.from_path([common.VideoId.MOVIE, videoid_value])
                execute_lib_tasks_method(videoid, [remove_item], sync_mylist=False)

            # Add missing tv shows / movies of My List to library
            for videoid in mylist_videoids:
                if videoid.value not in exported_tvshows_videoids_values and \
                   videoid.value not in exported_movies_videoids_values:
                    videoids_to_update.append(videoid)

        # Add the exported tv shows to be updated to the list..
        tvshows_videoids_to_upd = [common.VideoId.from_path([common.VideoId.SHOW,
                                                             videoid_value]) for
                                   videoid_value in
                                   g.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'],
                                                                   False)]
        # ..and avoids any duplication caused by possible unexpected errors
        videoids_to_update.extend(list(set(tvshows_videoids_to_upd) - set(videoids_to_update)))

        # Add missing tv shows/movies or update existing tv shows
        _update_library(videoids_to_update, exported_tvshows_videoids_values, silent)

        common.debug('Auto update of the library completed')
        g.SHARED_DB.set_value('library_auto_update_is_running', False)
        if not g.ADDON.getSettingBool('lib_auto_upd_disable_notification'):
            ui.show_notification(common.get_local_string(30220), time=5000)
        common.debug('Notify service to communicate to Kodi of update the library')
        common.send_signal(common.Signals.LIBRARY_UPDATE_REQUESTED)
    except Exception:  # pylint: disable=broad-except
        import traceback
        common.error('An error has occurred in the library auto update')
        common.error(traceback.format_exc())
        g.SHARED_DB.set_value('library_auto_update_is_running', False)


def _update_library(videoids_to_update, exported_tvshows_videoids_values, silent):
    execute_lib_tasks_method = execute_library_tasks_silently if silent else execute_library_tasks
    # Get the list of the Tv Shows exported to exclude from updates
    excluded_videoids_values = g.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'],
                                                               True)
    for videoid in videoids_to_update:
        # Check if current videoid is excluded from updates
        if videoid.value in excluded_videoids_values:
            continue
        if videoid.value in exported_tvshows_videoids_values:
            # It is possible that the user has chosen not to export NFO files for a tv show
            nfo_export = g.SHARED_DB.get_tvshow_property(videoid.value,
                                                         VidLibProp['nfo_export'], False)
            nfo_settings = nfo.NFOSettings(nfo_export)
        else:
            nfo_settings = nfo.NFOSettings()
        if videoid.mediatype == common.VideoId.SHOW:
            export_new_episodes(videoid, silent, nfo_settings)
        if videoid.mediatype == common.VideoId.MOVIE:
            execute_lib_tasks_method(videoid, [export_item],
                                     sync_mylist=False,
                                     nfo_settings=nfo_settings)
        # Add some randomness between operations to limit servers load and ban risks
        xbmc.sleep(random.randint(1000, 5001))


def _get_mylist_videoids():
    """Get My List videoids of an chosen profile"""
    return api.mylist_items_switch_profiles()


def export_new_episodes(videoid, silent=False, nfo_settings=None):
    """
    Export new episodes for a tv show by it's video id
    :param videoid: The videoid of the tv show to process
    :param scan: Whether or not to scan the library after exporting, useful for a single show
    :param silent: don't display user interface while exporting
    :param nfo_settings: the nfo settings
    :return: None
    """

    method = execute_library_tasks_silently if silent else execute_library_tasks

    if videoid.mediatype == common.VideoId.SHOW:
        common.debug('Exporting new episodes for {}', videoid)
        method(videoid, [export_new_item],
               title=common.get_local_string(30198),
               sync_mylist=False,
               nfo_settings=nfo_settings)
    else:
        common.debug('{} is not a tv show, no new episodes will be exported', videoid)


@update_kodi_library
def execute_library_tasks(videoid, task_handlers, title, sync_mylist=True, nfo_settings=None):
    """Execute library tasks for videoid and show errors in foreground"""
    for task_handler in task_handlers:
        common.execute_tasks(title=title,
                             tasks=compile_tasks(videoid, task_handler, nfo_settings),
                             task_handler=task_handler,
                             notify_errors=True,
                             library_home=library_path())

        # Exclude update operations
        if task_handlers != [remove_item, export_item]:
            _sync_mylist(videoid, task_handler, sync_mylist)


@update_kodi_library
def execute_library_tasks_silently(videoid, task_handlers, title=None,
                                   sync_mylist=False, nfo_settings=None):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=unused-argument
    for task_handler in task_handlers:
        for task in compile_tasks(videoid, task_handler, nfo_settings):
            try:
                task_handler(task, library_path())
            except Exception:  # pylint: disable=broad-except
                import traceback
                common.error(traceback.format_exc())
                common.error('{} of {} failed', task_handler.__name__, task['title'])
        if sync_mylist and (task_handlers != [remove_item, export_item]):
            _sync_mylist(videoid, task_handler, sync_mylist)


def _sync_mylist(videoid, task_handler, enabled):
    """Add or remove exported items to My List, if enabled in settings"""
    operation = {
        'export_item': 'add',
        'remove_item': 'remove'}.get(task_handler.__name__)
    if enabled and operation and g.ADDON.getSettingBool('mylist_library_sync'):
        common.info('Syncing my list due to change of Kodi library')
        api.update_my_list(videoid, operation)


def get_previously_exported_items():
    """Return a list of movie or tvshow VideoIds for items that were exported in
    the old storage format"""
    result = []
    videoid_pattern = re.compile('video_id=(\\d+)')
    for folder in _lib_folders(FOLDER_MOVIES) + _lib_folders(FOLDER_TV):
        for filename in xbmcvfs.listdir(folder)[1]:
            filepath = xbmc.makeLegalFilename('/'.join([folder, filename])).decode('utf-8')
            if filepath.endswith('.strm'):
                common.debug('Trying to migrate {}', filepath)
                try:
                    # Only get a VideoId from the first file in each folder.
                    # For shows, all episodes will result in the same VideoId
                    # and movies only contain one file
                    result.append(
                        _get_root_videoid(filepath, videoid_pattern))
                except (AttributeError, IndexError):
                    common.warn('Item does not conform to old format')
                break
    return result


def _lib_folders(section):
    section_dir = xbmc.translatePath(
        xbmc.makeLegalFilename('/'.join([library_path(), section])))
    return [xbmc.makeLegalFilename('/'.join([section_dir, folder.decode('utf-8')]))
            for folder
            in xbmcvfs.listdir(section_dir)[0]]


def _get_root_videoid(filename, pattern):
    match = re.search(pattern,
                      xbmcvfs.File(filename, 'r').read().decode('utf-8').split('\n')[-1])
    metadata = api.metadata(
        common.VideoId(videoid=match.groups()[0]))[0]
    if metadata['type'] == 'show':
        return common.VideoId(tvshowid=metadata['id'])
    return common.VideoId(movieid=metadata['id'])
