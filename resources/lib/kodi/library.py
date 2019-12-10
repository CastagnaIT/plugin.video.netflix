# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Kodi library integration

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
from functools import wraps

import xbmc

import resources.lib.api.shakti as api
import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.globals import g
from resources.lib.kodi.library_items import (export_item, remove_item, export_new_item, get_item,
                                              ItemNotFound, FOLDER_MOVIES, FOLDER_TV, library_path)
from resources.lib.kodi.library_tasks import compile_tasks


def update_kodi_library(library_operation):
    """Decorator that ensures an update of the Kodi library"""

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


def export_new_episodes(videoid, silent=False, nfo_settings=None):
    """
    Export new episodes for a tv show by it's video id
    :param videoid: The videoid of the tv show to process
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
    if enabled and operation and g.ADDON.getSettingBool('lib_sync_mylist'):
        common.info('Syncing my list due to change of Kodi library')
        api.update_my_list(videoid, operation)


def sync_mylist_to_library():
    """
    Perform a full sync of Netflix "My List" with the Kodi library
    by deleting everything that was previously exported
    """
    common.info('Performing full sync of Netflix "My List" with the Kodi library')
    purge()
    nfo_settings = nfo.NFOSettings()
    nfo_settings.show_export_dialog()
    for videoid in api.mylist_items_switch_profiles():
        execute_library_tasks(videoid, [export_item],
                              common.get_local_string(30018),
                              sync_mylist=False,
                              nfo_settings=nfo_settings)


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
