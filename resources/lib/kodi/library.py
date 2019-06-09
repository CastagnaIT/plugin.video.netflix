# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import os
import re
import sys

from datetime import datetime, timedelta
from functools import wraps

import xbmc
import xbmcvfs

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui
import resources.lib.kodi.nfo as nfo

import xml.etree.ElementTree as ET


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
        library_entry, entry_type = _get_library_entry(videoid)
        return _get_item(entry_type, library_entry['file'])
    except (KeyError, AttributeError, IndexError, ItemNotFound):
        raise ItemNotFound(
            'The video with id {} is not present in the Kodi library'
            .format(videoid))


@common.time_execution(immediate=False)
def _get_library_entry(videoid):
    """Get the first leaf-entry for videoid from the library.
    For shows and seasons this will return the first contained episode"""
    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.EPISODE]:
        return (common.get_path(videoid.to_list(), g.library()),
                videoid.mediatype)
    elif videoid.mediatype == common.VideoId.SHOW:
        return (
            _any_child_library_entry(
                _any_child_library_entry(g.library()[videoid.tvshowid])),
            common.VideoId.EPISODE)
    elif videoid.mediatype == common.VideoId.SEASON:
        return (
            _any_child_library_entry(
                g.library()[videoid.tvshowid][videoid.seasonid]),
            common.VideoId.EPISODE)
    else:
        # Items of other mediatype are never in library
        raise ItemNotFound


def _any_child_library_entry(library_entry):
    """Return a random library entry that is a child of library_entry"""
    return common.any_value_except(library_entry, 'videoid')


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
    return common.get_library_item_details(
         mediatype, library_item[mediatype + 'id'])
    raise ItemNotFound


def list_contents():
    """Return a list of all top-level video IDs (movies, shows)
    contained in the library"""
    return g.library().keys()


def is_in_library(videoid):
    """Return True if the video is in the local Kodi library, else False"""
    return common.get_path_safe(videoid.to_list(), g.library()) is not None


def update_kodi_library(library_operation):
    """Decorator that ensures an update of the Kodi libarary"""
    @wraps(library_operation)
    def kodi_library_update_wrapper(videoid, task_handler, *args, **kwargs):
        """Either trigger an update of the Kodi library or remove the
        items associated with videoid, depending on the invoked task_handler"""
        is_remove = task_handler == remove_item
        if is_remove:
            _remove_from_kodi_library(videoid)
        library_operation(videoid, task_handler, *args, **kwargs)
        if not is_remove:
            # Update kodi library through service
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
            # Retreive the all episodes in the export folder
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
    """Purge all items exported to Kodi library and delete internal library
    database"""
    common.debug('Purging library: {}'.format(g.library()))
    for library_item in g.library().values():
        execute_library_tasks(library_item['videoid'], remove_item,
                              common.get_local_string(30030),
                              sync_mylist=False)


@common.time_execution(immediate=False)
def compile_tasks(videoid, export_nfo=False):
    """Compile a list of tasks for items based on the videoid"""
    common.debug('Compiling library tasks for {}'.format(videoid))
    metadata = api.metadata(videoid)
    if videoid.mediatype == common.VideoId.MOVIE:
        return _create_movie_task(videoid, metadata[0], export_nfo)
    elif videoid.mediatype in common.VideoId.TV_TYPES:
        return _create_tv_tasks(videoid, metadata, export_nfo)

    raise ValueError('Cannot handle {}'.format(videoid))


def _create_movie_task(videoid, movie, export_nfo):
    """Create a task for a movie"""
    # Reset NFO export to false if we never want movies nfo
    if g.ADDON.getSettingInt('export_movie_nfo') == 0:
        export_nfo = False

    name = '{title} ({year})'.format(title=movie['title'], year=movie['year'])
    return [_create_item_task(name, FOLDER_MOVIES, videoid, name, name,
                              nfo.create_movie_nfo(movie) if export_nfo else None)]


def _create_tv_tasks(videoid, metadata, export_nfo):
    """Create tasks for a show, season or episode.
    If videoid represents a show or season, tasks will be generated for
    all contained seasons and episodes"""
    # Reset NFO export to false if we never want tv shows nfo
    if g.ADDON.getSettingInt('export_tv_nfo') == 0:
        export_nfo = False

    if videoid.mediatype == common.VideoId.SHOW:
        tasks = _compile_show_tasks(videoid, metadata[0], export_nfo)
    elif videoid.mediatype == common.VideoId.SEASON:
       tasks = _compile_season_tasks(videoid,
                                    metadata[0],
                                    common.find(int(videoid.seasonid),
                                                'id',
                                                metadata[0]['seasons']),
                                     export_nfo)
    else:
        tasks = [_create_episode_task(videoid, task_handler, *metadata, export_nfo=export_nfo)]

    # If we do want the tvshow.nfo file
    if (export_nfo and not g.ADDON.getSettingBool('export_tv_nfo_disable_tvshownfo')):
        tasks.append(_create_item_task('tvshow.nfo', FOLDER_TV, videoid,
                                       metadata[0]['title'],
                                       'tvshow',
                                       nfo.create_show_nfo(metadata[0]),
                                       False))
    return tasks


def _compile_show_tasks(videoid, show, export_nfo):
    """Compile a list of task items for all episodes of all seasons
    of a tvshow"""
    # This nested comprehension is nasty but neccessary. It flattens
    # the task lists for each season into one list
    return [task for season in show['seasons']
            for task in _compile_season_tasks(
                videoid.derive_season(season['id']), show, season, export_nfo)]


def _compile_season_tasks(videoid, show, season, export_nfo):
    """Compile a list of task items for all episodes in a season"""
    return [_create_episode_task(videoid.derive_episode(episode['id']),
                                 episode, season, show, export_nfo)
            for episode in season['episodes']]


def _create_episode_task(videoid, episode, season, show, export_nfo):
    """Export a single episode to the library"""
    filename = 'S{:02d}E{:02d}'.format(season['seq'], episode['seq'])
    title = ' - '.join((show['title'], filename, episode['title']))
    return _create_item_task(title, FOLDER_TV, videoid, show['title'],
                             filename,
                             nfo.create_episode_nfo(episode,season,show) if export_nfo else None)


def _create_item_task(title, section, videoid, destination, filename, nfo_data=None, is_strm=True):
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


@common.time_execution(immediate=False)
def export_item(item_task, library_home):
    """Create strm file for an item and add it to the library"""
    # Paths must be legal to ensure NFS compatibility
    destination_folder = xbmc.makeLegalFilename(os.path.join(
        library_home, item_task['section'], item_task['destination']))
    _create_destination_folder(destination_folder)
    if item_task['is_strm']:
        export_filename = xbmc.makeLegalFilename(os.path.join(
            destination_folder.decode('utf-8'), item_task['filename'] + '.strm'))
        _add_to_library(item_task['videoid'], export_filename)
        _write_strm_file(item_task, export_filename)
    if item_task['nfo_data'] is not None:
        nfo_filename = xbmc.makeLegalFilename(os.path.join(
            destination_folder.decode('utf-8'), item_task['filename'] + '.nfo'))
        _write_nfo_file(item_task['nfo_data'], nfo_filename)
    common.debug('Exported {}'.format(item_task['title']))

@common.time_execution(immediate=False)
def export_item_show_nfo(item_task, library_home):
    """Create tvshow.nfo file"""
    destination_folder = xbmc.makeLegalFilename(os.path.join(
        library_home, item_task['section'], item_task['destination']))
    export_filename = xbmc.makeLegalFilename(os.path.join(
        destination_folder.decode('utf-8'), item_task['filename'] + '.nfo'))


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


def _add_to_library(videoid, export_filename):
    """Add an exported file to the library"""
    library_node = g.library()
    for depth, id_item in enumerate(videoid.to_list()):
        if id_item not in library_node:
            # No entry yet at this level, create a new one and assign
            # it an appropriate videoid for later reference
            library_node[id_item] = {
                'videoid': videoid.derive_parent(depth)}
        library_node = library_node[id_item]
    library_node['file'] = export_filename
    library_node['videoid'] = videoid
    g.save_library()


@common.time_execution(immediate=False)
def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument, broad-except
    if item_task['is_strm'] == True: # We don't take care of a tvshow.nfo task if we are running an update
        common.debug('Removing {} from library'.format(item_task['title']))
        if not is_in_library(item_task['videoid']):
            common.warn('cannot remove {}, item not in library'
                        .format(item_task['title']))
            return
        id_path = item_task['videoid'].to_list()
        exported_filename = xbmc.translatePath(
            common.get_path(id_path, g.library())['file']).decode("utf-8")
        parent_folder = os.path.dirname(exported_filename)
        try:
            xbmcvfs.delete(xbmc.translatePath(exported_filename).decode("utf-8"))
            # Remove the NFO file if exists
            nfo = os.path.splitext(xbmc.translatePath(exported_filename).decode("utf-8"))[0]+'.nfo'
            if xbmcvfs.exists(nfo):
                xbmcvfs.delete(nfo)
            dirs, files = xbmcvfs.listdir(xbmc.translatePath(parent_folder).decode("utf-8"))
            tvshownfo = xbmc.makeLegalFilename(
                os.path.join(
                    xbmc.translatePath(parent_folder).decode("utf-8"),'tvshow.nfo'))
            # We may want tvshow.nfo to be removed on update:
            # - If export NFO is off
            # - If ignore tvshow.nfo is enabled
            # - If export_tv_nfo is set to Never
            if ((not g.ADDON.getSettingBool('enable_nfo_export') or
                 g.ADDON.getSettingInt('export_tv_nfo') == 0 or
                 g.ADDON.getSettingBool('export_tv_nfo_disable_tvshownfo'))
                and xbmcvfs.exists(tvshownfo)):
                xbmcvfs.delete(tvshownfo)
            # On some file system, it's not possible to remove a folder if not empty
            # So we need to remove the tvshow.nfo if it's the last file
            if not dirs and len(files) == 1 and files[0] == 'tvshow.nfo':
                xbmcvfs.delete(tvshownfo)
                # tvshow.nfo was the last file so we remove the parent folder
                # avoiding a call to xbmcvfs.listdir again
                xbmcvfs.rmdir(xbmc.translatePath(parent_folder).decode("utf-8"))
            # Fix parent folder not removed
            if not dirs and not files: # the destination folder is empty
                xbmcvfs.rmdir(xbmc.translatePath(parent_folder).decode("utf-8"))
        except Exception:
            common.debug('Cannot delete {}, file does not exist'
                         .format(exported_filename))
        common.remove_path(id_path, g.library(), lambda e: e.keys() == ['videoid'])
        g.save_library()


def update_item(item_task, library_home):
    """Remove and then re-export an item to the Kodi library"""
    remove_item(item_task)
    export_item(item_task, library_home)


def _update_running():
    update = g.ADDON.getSetting('update_running') or None
    if update:
        starttime = common.strp(update, '%Y-%m-%d %H:%M')
        if (starttime + timedelta(hours=6)) <= datetime.now():
            g.ADDON.setSetting('update_running', 'false')
            common.warn('Canceling previous library update: duration >6 hours')
        else:
            common.debug('DB Update already running')
            return True
    return False


def update_library():
    """
    Update the local Kodi library with new episodes of exported shows
    """
    if not _update_running():
        common.info('Triggering library update')
        xbmc.executebuiltin(
            ('XBMC.RunPlugin(plugin://{}/?action=export-new-episodes'
             '&inbackground=True)')
            .format(g.ADDON_ID))


@update_kodi_library
def execute_library_tasks(videoid, task_handler, title, sync_mylist=True, export_nfo=False):
    """Execute library tasks for videoid and show errors in foreground"""
    common.execute_tasks(title=title,
                         tasks=compile_tasks(videoid, export_nfo),
                         task_handler=task_handler,
                         notify_errors=True,
                         library_home=library_path())
    _sync_mylist(videoid, task_handler, sync_mylist)


@update_kodi_library
def execute_library_tasks_silently(videoid, task_handler, sync_mylist, export_nfo=False):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=broad-except
    for task in compile_tasks(videoid, export_nfo):
        try:
            task_handler(task, library_path())
        except Exception:
            import traceback
            common.error(traceback.format_exc())
            common.error('{} of {} failed'
                         .format(task_handler.__name__, task['title']))
    if sync_mylist:
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
            filepath = os.path.join(folder, file.decode('utf-8'))
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
    section_dir = xbmc.translatePath(os.path.join(library_path(), section))
    return [os.path.join(section_dir, folder.decode('utf-8'))
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
