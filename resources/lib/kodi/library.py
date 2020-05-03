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

import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.api.paths import MAX_PATH_REQUEST_SIZE
from resources.lib.globals import g
from resources.lib.kodi.library_items import (export_item, remove_item, export_new_item, get_item,
                                              ItemNotFound, FOLDER_MOVIES, FOLDER_TV, library_path)
from resources.lib.kodi.library_tasks import compile_tasks, execute_tasks

try:  # Kodi >= 19
    from xbmcvfs import makeLegalFilename  # pylint: disable=ungrouped-imports
except ImportError:  # Kodi 18
    from xbmc import makeLegalFilename  # pylint: disable=ungrouped-imports


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


def list_contents(perpetual_range_start):
    """Return a chunked list of all video IDs (movies, shows) contained in the library"""
    perpetual_range_start = int(perpetual_range_start) if perpetual_range_start else 0
    number_of_requests = 2
    video_id_list = g.SHARED_DB.get_all_video_id_list()
    count = 0
    chunked_video_list = []
    perpetual_range_selector = {}

    for index, chunk in enumerate(common.chunked_list(video_id_list, MAX_PATH_REQUEST_SIZE)):
        if index >= perpetual_range_start:
            if number_of_requests == 0:
                if len(video_id_list) > count:
                    # Exists others elements
                    perpetual_range_selector['_perpetual_range_selector'] = {'next_start': perpetual_range_start + 1}
                break
            chunked_video_list.append(chunk)
            number_of_requests -= 1
        count += len(chunk)

    if perpetual_range_start > 0:
        previous_start = perpetual_range_start - 1
        if '_perpetual_range_selector' in perpetual_range_selector:
            perpetual_range_selector['_perpetual_range_selector']['previous_start'] = previous_start
        else:
            perpetual_range_selector['_perpetual_range_selector'] = {'previous_start': previous_start}
    return chunked_video_list, perpetual_range_selector


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
               nfo_settings=nfo_settings)
    else:
        common.debug('{} is not a tv show, no new episodes will be exported', videoid)


@update_kodi_library
def execute_library_tasks(videoid, task_handlers, title, nfo_settings=None):
    """Execute library tasks for videoid and show errors in foreground"""
    for task_handler in task_handlers:
        execute_tasks(title=title,
                      tasks=compile_tasks(videoid, task_handler, nfo_settings),
                      task_handler=task_handler,
                      notify_errors=True,
                      library_home=library_path())


@update_kodi_library
def execute_library_tasks_silently(videoid, task_handlers, title=None, nfo_settings=None):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=unused-argument
    for task_handler in task_handlers:
        for task in compile_tasks(videoid, task_handler, nfo_settings):
            try:
                task_handler(task, library_path())
            except Exception:  # pylint: disable=broad-except
                import traceback
                common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
                common.error('{} of {} failed', task_handler.__name__, task['title'])


def sync_mylist_to_library():
    """
    Perform a full sync of Netflix "My List" with the Kodi library
    by deleting everything that was previously exported
    """
    common.info('Performing full sync of Netflix "My List" with the Kodi library')
    purge()
    nfo_settings = nfo.NFOSettings()
    nfo_settings.show_export_dialog()

    mylist_video_id_list, mylist_video_id_list_type = common.make_call('get_mylist_videoids_profile_switch')
    for index, video_id in enumerate(mylist_video_id_list):
        videoid = common.VideoId(
            **{('movieid' if (mylist_video_id_list_type[index] == 'movie') else 'tvshowid'): video_id})
        execute_library_tasks(videoid, [export_item],
                              common.get_local_string(30018),
                              nfo_settings=nfo_settings)


@common.time_execution(immediate=False)
def purge():
    """Purge all items exported to Kodi library and delete internal library database"""
    common.info('Purging internal database and kodi library')
    for videoid_value in g.SHARED_DB.get_movies_id_list():
        videoid = common.VideoId.from_path([common.VideoId.MOVIE, videoid_value])
        execute_library_tasks(videoid, [remove_item],
                              common.get_local_string(30030))
    for videoid_value in g.SHARED_DB.get_tvshows_id_list():
        videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
        execute_library_tasks(videoid, [remove_item],
                              common.get_local_string(30030))
    # If for some reason such as improper use of the add-on, unexpected error or other
    # has caused inconsistencies with the contents of the database or stored files,
    # make sure that everything is removed
    g.SHARED_DB.purge_library()
    for folder_name in [FOLDER_MOVIES, FOLDER_TV]:
        section_dir = xbmc.translatePath(
            makeLegalFilename('/'.join([library_path(), folder_name])))
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
