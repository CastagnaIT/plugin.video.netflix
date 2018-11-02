# -*- coding: utf-8 -*-
"""Kodi library integration"""
from __future__ import unicode_literals

import os
import codecs
from datetime import datetime, timedelta

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api

LIBRARY_HOME = 'library'
FOLDER_MOVIES = 'movies'
FOLDER_TV = 'shows'


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
        exported_filepath = os.path.normcase(
            xbmc.translatePath(
                common.get_path(videoid.to_list(), g.library())['file']))
        for library_item in common.get_library_items(videoid.mediatype):
            if os.path.normcase(library_item['file']) == exported_filepath:
                return library_item
    except Exception:
        import traceback
        common.error(traceback.format_exc())
    # This is intentionally not raised in the except block!
    raise ItemNotFound(
        'The video with id {} is not present in the Kodi library'
        .format(videoid))


def list_contents():
    """Return a list of all top-level video IDs (movies, shows)
    contained in the library"""
    return g.library().keys()


def is_in_library(videoid):
    """Return True if the video is in the local Kodi library, else False"""
    return common.get_path_safe(videoid.to_list(), g.library()) is not None


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
        'destination': destination,
        'filename': filename
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


def _create_destination_folder(destination_folder):
    """Create destination folder, ignore error if it already exists"""
    try:
        os.makedirs(xbmc.translatePath(destination_folder))
    except OSError as exc:
        if exc.errno != os.errno.EEXIST:
            raise


def _write_strm_file(item_task, export_filename):
    """Write the playable URL to a strm file"""
    try:
        with codecs.open(xbmc.translatePath(export_filename),
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


def remove_item(item_task):
    """Remove an item from the library and delete if from disk"""
    id_path = item_task['videoid'].to_list()
    exported_filename = xbmc.translatePath(
        common.get_path(id_path, g.library())['file'])
    parent_folder = os.path.dirname(exported_filename)
    os.remove(xbmc.translatePath(exported_filename))
    if not os.listdir(parent_folder):
        os.remove(parent_folder)
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
