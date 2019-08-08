# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

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

LIBRARY_HOME = 'library'
FOLDER_MOVIES = 'movies'
FOLDER_TV = 'shows'
ILLEGAL_CHARACTERS = '[<|>|"|?|$|!|:|#|*]'


class ItemNotFound(Exception):
    """The requested item could not be found in the Kodi library"""
    pass


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
    path = os.path.dirname(xbmc.translatePath(fname).decode("utf-8"))
    shortname = os.path.basename(xbmc.translatePath(fname).decode("utf-8"))
    # We get the data from Kodi library using filters.
    # This is much faster than loading all episodes in memory
    library_item = common.get_library_items(
        mediatype,
        {'and': [
            {'field': 'path', 'operator': 'startswith', 'value': path},
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
    elif videoid.mediatype == common.VideoId.SHOW:
        return g.SHARED_DB.tvshow_id_exists(videoid.value)
    elif videoid.mediatype == common.VideoId.SEASON:
        return g.SHARED_DB.season_id_exists(videoid.tvshowid,
                                            videoid.seasonid)
    elif videoid.mediatype == common.VideoId.EPISODE:
        return g.SHARED_DB.episode_id_exists(videoid.tvshowid,
                                             videoid.seasonid,
                                             videoid.episodeid)
    else:
        raise common.InvalidVideoId('videoid {} type not implemented'.format(videoid))


def show_excluded_from_auto_update(videoid):
    """Return true if the videoid is excluded from auto-update"""
    return g.SHARED_DB.get_tvshow_property(videoid.value, VidLibProp.exclude_update, False)


@common.time_execution(immediate=False)
def exclude_show_from_auto_update(videoid, exclude):
    """Set if a tvshow is excluded from auto-update"""
    g.SHARED_DB.set_tvshow_property(videoid.value, VidLibProp.exclude_update, exclude)


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
    common.debug('Removing {} videoid from Kodi library'.format(videoid))
    try:
        kodi_library_items = [get_item(videoid)]
        if videoid.mediatype == common.VideoId.SHOW or videoid.mediatype == common.VideoId.SEASON:
            # Retrieve the all episodes in the export folder
            filters = {'and': [
                {'field': 'path', 'operator': 'startswith', 'value': os.path.dirname(kodi_library_items[0]['file'])},
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
        common.debug('Cannot remove {} from Kodi library, item not present'
                     .format(videoid))
    except KeyError as exc:
        ui.show_notification(common.get_local_string(30120), time=7500)
        common.warn('Cannot remove {} from Kodi library, '
                    'Kodi does not support this (yet)'
                    .format(exc))


@common.time_execution(immediate=False)
def purge():
    """Purge all items exported to Kodi library and delete internal library database"""
    common.debug('Purging internal database and kodi library')
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


@common.time_execution(immediate=False)
def compile_tasks(videoid, task_handler, nfo_settings=None):
    """Compile a list of tasks for items based on the videoid"""
    common.debug('Compiling library tasks for {}'.format(videoid))

    if task_handler == export_item:
        metadata = api.metadata(videoid)
        if videoid.mediatype == common.VideoId.MOVIE:
            return _create_export_movie_task(videoid, metadata[0], nfo_settings)
        elif videoid.mediatype in common.VideoId.TV_TYPES:
            return _create_export_tv_tasks(videoid, metadata, nfo_settings)
        raise ValueError('Cannot handle {}'.format(videoid))

    if task_handler == export_new_item:
        metadata = api.metadata(videoid, True)
        return _create_new_episodes_tasks(videoid, metadata)

    if task_handler == remove_item:
        if videoid.mediatype == common.VideoId.MOVIE:
            return _create_remove_movie_task(videoid)
        elif videoid.mediatype == common.VideoId.SHOW:
            return _compile_remove_tvshow_tasks(videoid)
        elif videoid.mediatype == common.VideoId.SEASON:
            return _compile_remove_season_tasks(videoid)
        elif videoid.mediatype == common.VideoId.EPISODE:
            return _create_remove_episode_task(videoid)


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
        for i in range(len(metadata)):
            if metadata[i] and metadata[i].get('type', None) == 'show':
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


def _create_new_episodes_tasks(videoid, metadata):
    tasks = []
    if metadata and 'seasons' in metadata[0]:
        for season in metadata[0]['seasons']:
            nfo_export = g.SHARED_DB.get_tvshow_property(videoid.value,
                                                         VidLibProp.nfo_export, False)
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
                        common.debug('Auto exporting episode {}'.format(episode['id']))
            else:
                # The season does not exist, build task for the season
                tasks += _compile_export_season_tasks(
                    videoid=videoid.derive_season(season['id']),
                    show=metadata[0],
                    season=season,
                    nfo_settings=nfo_settings
                )
                common.debug('Auto exporting season {}'.format(season['id']))
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
    return [_create_remove_item_task(_episode_title_from_path(row[b'FilePath']),
                                     row[b'FilePath'],
                                     common.VideoId.from_dict(
                                         {'mediatype': common.VideoId.SHOW,
                                          'tvshowid': row[b'TvShowID'],
                                          'seasonid': row[b'SeasonID'],
                                          'episodeid': row[b'EpisodeID']}))
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
    dir = os.path.split(os.path.split(filepath)[0])[1]
    return '{} - {}'.format(dir, fname)


# We need to differentiate task_handler for task creation, but we use the same export method
def export_new_item(item_task, library_home):
    export_item(item_task, library_home)


@common.time_execution(immediate=False)
def export_item(item_task, library_home):
    """Create strm file for an item and add it to the library"""
    # Paths must be legal to ensure NFS compatibility
    destination_folder = xbmc.makeLegalFilename('/'.join(
        [library_home, item_task['section'], item_task['destination']]))
    _create_destination_folder(destination_folder)
    if item_task['is_strm']:
        export_filename = xbmc.makeLegalFilename('/'.join(
            [destination_folder.decode('utf-8'), item_task['filename'] + '.strm']))
        _add_to_library(item_task['videoid'], export_filename, (item_task['nfo_data'] is not None))
        _write_strm_file(item_task, export_filename)
    if item_task['nfo_data'] is not None:
        nfo_filename = xbmc.makeLegalFilename('/'.join(
            [destination_folder.decode('utf-8'), item_task['filename'] + '.nfo']))
        _write_nfo_file(item_task['nfo_data'], nfo_filename)
    common.debug('Exported {}'.format(item_task['title']))


def _create_destination_folder(destination_folder):
    """Create destination folder, ignore error if it already exists"""
    destination_folder = xbmc.translatePath(destination_folder)
    if not xbmcvfs.exists(destination_folder):
        xbmcvfs.mkdirs(destination_folder)


def _write_strm_file(item_task, export_filename):
    """Write the playable URL to a strm file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(export_filename), 'w')
    try:
        filehandle.write(common.build_url(videoid=item_task['videoid'],
                                          mode=g.MODE_PLAY).encode('utf-8'))
    finally:
        filehandle.close()


def _write_nfo_file(nfo_data, nfo_filename):
    """Write the NFO file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(nfo_filename), 'w')
    try:
        filehandle.write('<?xml version=\'1.0\' encoding=\'UTF-8\'?>'.encode('utf-8'))
        filehandle.write(ET.tostring(nfo_data, encoding='utf-8', method='xml'))
    finally:
        filehandle.close()


def _add_to_library(videoid, export_filename, nfo_export):
    """Add an exported file to the library"""
    if videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.set_tvshow(videoid.tvshowid, nfo_export, False)
        g.SHARED_DB.insert_season(videoid.tvshowid, videoid.seasonid)
        g.SHARED_DB.insert_episode(videoid.tvshowid, videoid.seasonid, videoid.value,
                                   export_filename.decode("utf-8"))
    elif videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.set_movie(videoid.value, export_filename.decode("utf-8"), nfo_export)


@common.time_execution(immediate=False)
def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument, broad-except

    common.debug('Removing {} from library'.format(item_task['title']))

    exported_filename = xbmc.translatePath(item_task['filepath'])
    videoid = item_task['videoid']
    common.debug('VideoId: {}'.format(videoid))
    try:
        parent_folder = xbmc.translatePath(os.path.dirname(exported_filename))
        xbmcvfs.delete(exported_filename.decode("utf-8"))
        # Remove the NFO files if exists
        nfo_file = os.path.splitext(exported_filename.decode("utf-8"))[0] + '.nfo'
        if xbmcvfs.exists(nfo_file):
            xbmcvfs.delete(nfo_file)
        dirs, files = xbmcvfs.listdir(parent_folder.decode("utf-8"))
        tvshow_nfo_file = xbmc.makeLegalFilename(
            '/'.join([parent_folder.decode("utf-8"), 'tvshow.nfo']))
        # Remove tvshow_nfo_file only when is the last file
        # (users have the option of removing even single seasons)
        if xbmcvfs.exists(tvshow_nfo_file) and not dirs and len(files) == 1:
            xbmcvfs.delete(tvshow_nfo_file)
            # Delete parent folder
            xbmcvfs.rmdir(parent_folder.decode("utf-8"))
        # Delete parent folder when empty
        if not dirs and not files:
            xbmcvfs.rmdir(parent_folder.decode("utf-8"))

        _remove_videoid_from_db(videoid)
    except ItemNotFound:
        common.debug('The video with id {} not exists in the database'.format(videoid))
    except Exception:
        common.debug('Cannot delete {}, file does not exist'.format(exported_filename))


def _remove_videoid_from_db(videoid):
    """Removes records from database in relation to a videoid"""
    if videoid.mediatype == common.VideoId.MOVIE:
        g.SHARED_DB.delete_movie(videoid.value)
    elif videoid.mediatype == common.VideoId.EPISODE:
        g.SHARED_DB.delete_episode(videoid.tvshowid, videoid.seasonid, videoid.episodeid)



def _export_all_new_episodes_running():
    update = g.SHARED_DB.get_value('library_export_new_episodes_running', False)
    if update:
        start_time = g.SHARED_DB.get_value('library_export_new_episode_start_time',
                                          data_type=datetime)
        start_time = common.strp(start_time, '%Y-%m-%d %H:%M')
        if datetime.now() >= start_time + timedelta(hours=6):
            g.SHARED_DB.set_value('library_export_new_episodes_running', False)
            common.warn('Canceling previous library update: duration >6 hours')
        else:
            common.debug('Export all new episodes is already running')
            return True
    return False


def export_all_new_episodes():
    """
    Update the local Kodi library with new episodes of every exported shows
    """
    if not _export_all_new_episodes_running():
        common.log('Starting to export new episodes for all tv shows')
        g.SHARED_DB.set_value('library_export_new_episodes_running', True)
        g.SHARED_DB.set_value('library_export_new_episode_start_time', datetime.now())

        for videoid_value in g.SHARED_DB.get_tvshows_id_list(VidLibProp.exclude_update, False):
            videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
            export_new_episodes(videoid, False)
            # add some randomness between show analysis to limit servers load and ban risks
            xbmc.sleep(random.randint(1000, 5001))

        g.SHARED_DB.set_value('library_export_new_episodes_running', False)
        common.debug('Notify service to update the library')
        common.send_signal(common.Signals.LIBRARY_UPDATE_REQUESTED)


def export_new_episodes(videoid, scan=True):
    """
    Export new episodes for a tv show by it's video id
    :param videoid: The videoid of the tv show to process
    :param scan: Whether or not to scan the library after exporting, useful for a single show
    :return: None
    """
    if videoid.mediatype == common.VideoId.SHOW:
        common.debug('Exporting new episodes for {}'.format(videoid))
        execute_library_tasks_silently(videoid, [export_new_item], False)
        if scan:
            common.debug('Notify service to update the library')
            common.send_signal(common.Signals.LIBRARY_UPDATE_REQUESTED)
    else:
        common.debug('{} is not a tv show, no new episodes will be exported'.format(videoid))


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
def execute_library_tasks_silently(videoid, task_handlers, sync_mylist, nfo_settings=None):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=broad-except
    for task_handler in task_handlers:
        for task in compile_tasks(videoid, task_handler, nfo_settings):
            try:
                task_handler(task, library_path())
            except Exception:
                import traceback
                common.error(traceback.format_exc())
                common.error('{} of {} failed'
                             .format(task_handler.__name__, task['title']))
        if sync_mylist and (task_handlers != [remove_item, export_item]):
            _sync_mylist(videoid, task_handler, sync_mylist)


def _sync_mylist(videoid, task_handler, enabled):
    """Add or remove exported items to My List, if enabled in settings"""
    operation = {
        'export_item': 'add',
        'remove_item': 'remove'}.get(task_handler.__name__)
    if enabled and operation and g.ADDON.getSettingBool('mylist_library_sync'):
        common.debug('Syncing my list due to change of Kodi library')
        api.update_my_list(videoid, operation)


def get_previously_exported_items():
    """Return a list of movie or tvshow VideoIds for items that were exported in
    the old storage format"""
    result = []
    videoid_pattern = re.compile('video_id=(\\d+)')
    for folder in _lib_folders(FOLDER_MOVIES) + _lib_folders(FOLDER_TV):
        for file in xbmcvfs.listdir(folder)[1]:
            filepath = xbmc.makeLegalFilename('/'.join([folder, file.decode('utf-8')]))
            if filepath.endswith('.strm'):
                common.debug('Trying to migrate {}'.format(filepath))
                try:
                    # Only get a VideoId from the first file in each folder.
                    # For shows, all episodes will result in the same VideoId
                    # and movies only contain one file
                    result.append(
                        _get_root_videoid(filepath, videoid_pattern))
                except (AttributeError, IndexError):
                    common.debug('Item does not conform to old format')
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
