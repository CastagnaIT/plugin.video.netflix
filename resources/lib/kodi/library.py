# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import os
import re
from datetime import datetime, timedelta
from functools import wraps

import xbmc
import xbmcvfs

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui

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


def get_item(videoid):
    """Find an item in the Kodi library by its Netflix videoid and return
    Kodi DBID and mediatype"""
    # pylint: disable=broad-except
    try:
        library_entry, entry_type = _get_library_entry(videoid)
        return _get_item(entry_type, library_entry['file'])
    except (KeyError, AttributeError, IndexError, ItemNotFound):
        import traceback
        common.error(traceback.format_exc())
        raise ItemNotFound(
            'The video with id {} is not present in the Kodi library'
            .format(videoid))


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
        raise ItemNotFound('No items of type {} in library'
                           .format(videoid.mediatype))


def _any_child_library_entry(library_entry):
    """Return a random library entry that is a child of library_entry"""
    return common.any_value_except(library_entry, 'videoid')


def _get_item(mediatype, filename):
    exported_filepath = os.path.normcase(xbmc.translatePath(filename))
    for library_item in common.get_library_items(mediatype):
        if os.path.normcase(library_item['file']) == exported_filepath:
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
            common.debug('Triggering Kodi library scan')
            xbmc.executebuiltin('UpdateLibrary(video)')
    return kodi_library_update_wrapper


def _remove_from_kodi_library(videoid):
    """Remove an item from the Kodi library."""
    common.debug('Removing {} videoid from Kodi library'.format(videoid))
    try:
        kodi_library_item = get_item(videoid)
        rpc_params = {
            'movie': ['VideoLibrary.RemoveMovie', 'movieid'],
            'show': ['VideoLibrary.RemoveTVShow', 'tvshowid'],
            'episode': ['VideoLibrary.RemoveEpisode', 'episodeid']
        }[videoid.mediatype]
        common.json_rpc(rpc_params[0],
                        {rpc_params[1]: kodi_library_item[rpc_params[1]]})
    except ItemNotFound:
        common.debug('Cannot remove {} from Kodi library, item not present'
                     .format(videoid))
    except KeyError as exc:
        ui.show_notification(common.get_local_string(30120), time=7500)
        common.warn('Cannot remove {} from Kodi library, '
                    'Kodi does not support this (yet)'
                    .format(exc))


def purge():
    """Purge all items exported to Kodi library and delete internal library
    database"""
    common.debug('Purging library: {}'.format(g.library()))
    for library_item in g.library().values():
        execute_library_tasks(library_item['videoid'], remove_item,
                              common.get_local_string(30030),
                              sync_mylist=False)


def compile_tasks(videoid):
    """Compile a list of tasks for items based on the videoid"""
    common.debug('Compiling library tasks for {}'.format(videoid))
    metadata = api.metadata(videoid)
    if videoid.mediatype == common.VideoId.MOVIE:
        return _create_movie_task(videoid, metadata)
    elif videoid.mediatype in common.VideoId.TV_TYPES:
        return _create_tv_tasks(videoid, metadata)

    raise ValueError('Cannot handle {}'.format(videoid))


def _create_movie_task(videoid, metadata):
    """Create a task for a movie"""
    name = '{title} ({year})'.format(
        title=metadata['title'],
        year=metadata['year'])
    return [_create_item_task(name, FOLDER_MOVIES, videoid, name, name)]


def _create_tv_tasks(videoid, metadata):
    """Create tasks for a show, season or episode.
    If videoid represents a show or season, tasks will be generated for
    all contained seasons and episodes"""
    if videoid.mediatype == common.VideoId.SHOW:
        return _compile_show_tasks(videoid, metadata)
    elif videoid.mediatype == common.VideoId.SEASON:
        return _compile_season_tasks(videoid, metadata,
                                     common.find(videoid.seasonid,
                                                 metadata['seasons']))
    return [_create_episode_task(videoid, metadata)]


def _compile_show_tasks(videoid, metadata):
    """Compile a list of task items for all episodes of all seasons
    of a tvshow"""
    # This nested comprehension is nasty but neccessary. It flattens
    # the task lists for each season into one list
    return [task for season in metadata['seasons']
            for task in _compile_season_tasks(
                videoid.derive_season(season['id']), metadata, season)]


def _compile_season_tasks(videoid, metadata, season):
    """Compile a list of task items for all episodes in a season"""
    return [_create_episode_task(videoid.derive_episode(episode['id']),
                                 metadata, season, episode)
            for episode in season['episodes']]


def _create_episode_task(videoid, metadata, season=None, episode=None):
    """Export a single episode to the library"""
    showname = metadata['title']
    season = season or common.find(videoid.seasonid, metadata['seasons'])
    episode = episode or common.find(videoid.episodeid, season['episodes'])
    title = episode['title']
    filename = 'S{:02d}E{:02d}'.format(season['seq'], episode['seq'])
    title = ' - '.join((showname, filename, title))
    return _create_item_task(title, FOLDER_TV, videoid, showname, filename)


def _create_item_task(title, section, videoid, destination, filename):
    """Create a single task item"""
    return {
        'title': title,
        'section': section,
        'videoid': videoid,
        'destination': re.sub(ILLEGAL_CHARACTERS, '', destination),
        'filename': re.sub(ILLEGAL_CHARACTERS, '', filename)
    }


def export_item(item_task, library_home):
    """Create strm file for an item and add it to the library"""
    destination_folder = os.path.join(
        library_home, item_task['section'], item_task['destination'])
    export_filename = os.path.join(
        destination_folder, item_task['filename'] + '.strm')
    _add_to_library(item_task['videoid'], export_filename)
    _create_destination_folder(destination_folder)
    _write_strm_file(item_task, export_filename)
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


def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument, broad-except
    common.debug('Removing {} from library'.format(item_task['title']))
    if not is_in_library(item_task['videoid']):
        common.warn('cannot remove {}, item not in library'
                    .format(item_task['title']))
        return
    id_path = item_task['videoid'].to_list()
    exported_filename = xbmc.translatePath(
        common.get_path(id_path, g.library())['file'])
    parent_folder = os.path.dirname(exported_filename)
    try:
        xbmcvfs.delete(xbmc.translatePath(exported_filename))
        if not os.listdir(parent_folder):
            os.rmdir(parent_folder)
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
def execute_library_tasks(videoid, task_handler, title, sync_mylist=True):
    """Execute library tasks for videoid and show errors in foreground"""
    common.execute_tasks(title=title,
                         tasks=compile_tasks(videoid),
                         task_handler=task_handler,
                         notify_errors=True,
                         library_home=library_path())
    _sync_mylist(videoid, task_handler, sync_mylist)


@update_kodi_library
def execute_library_tasks_silently(videoid, task_handler, sync_mylist):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=broad-except
    for task in compile_tasks(videoid):
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
