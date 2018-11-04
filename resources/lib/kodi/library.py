# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import os
import re
import codecs
from datetime import datetime, timedelta
from functools import wraps

import xbmc

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
        return (g.library()[videoid.tvshowid].values()[0].values()[0],
                common.VideoId.EPISODE)
    elif videoid.mediatype == common.VideoId.SHOW:
        return (g.library()[videoid.tvshowid][videoid.seasonid].values()[0],
                common.VideoId.EPISODE)
    else:
        raise ItemNotFound('No items of type {} in library'
                           .format(videoid.mediatype))


def _get_item(mediatype, filename):
    exported_filepath = os.path.normcase(common.translate_path(filename))
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


def compile_tasks(videoid):
    """Compile a list of tasks for items based on the videoid"""
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
    _create_destination_folder(destination_folder)
    _write_strm_file(item_task, export_filename)
    _add_to_library(item_task['videoid'], export_filename)
    common.debug('Exported {}'.format(item_task['title']))


def _create_destination_folder(destination_folder):
    """Create destination folder, ignore error if it already exists"""
    try:
        os.makedirs(common.translate_path(destination_folder))
    except OSError as exc:
        if exc.errno != os.errno.EEXIST:
            raise


def _write_strm_file(item_task, export_filename):
    """Write the playable URL to a strm file"""
    try:
        with codecs.open(common.translate_path(export_filename),
                         mode='w',
                         encoding='utf-8',
                         errors='replace') as filehandle:
            filehandle.write(
                common.build_url(videoid=item_task['videoid'],
                                 mode=g.MODE_PLAY))
    except OSError as exc:
        if exc.errno == os.errno.EEXIST:
            common.info('{} already exists, skipping export'
                        .format(export_filename))
        else:
            raise


def _add_to_library(videoid, export_filename):
    """Add an exported file to the library"""
    library_node = g.library()
    for id_item in videoid.to_list():
        if id_item not in library_node:
            library_node[id_item] = {}
        library_node = library_node[id_item]
    library_node['file'] = export_filename
    g.save_library()


def remove_item(item_task, library_home=None):
    """Remove an item from the library and delete if from disk"""
    # pylint: disable=unused-argument
    common.debug('Removing {} from library'.format(item_task['title']))
    if not is_in_library(item_task['videoid']):
        common.warn('cannot remove {}, item not in library'
                    .format(item_task['title']))
        return
    id_path = item_task['videoid'].to_list()
    exported_filename = common.translate_path(
        common.get_path(id_path, g.library())['file'])
    parent_folder = os.path.dirname(exported_filename)
    os.remove(common.translate_path(exported_filename))
    if not os.listdir(parent_folder):
        os.rmdir(parent_folder)
    common.remove_path(id_path, g.library())
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
