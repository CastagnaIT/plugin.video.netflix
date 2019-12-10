# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Kodi library integration: task management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
import re

import resources.lib.api.shakti as api
import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
from resources.lib.database.db_utils import (VidLibProp)
from resources.lib.globals import g
from resources.lib.kodi.library_items import (export_item, remove_item, export_new_item,
                                              FOLDER_MOVIES, FOLDER_TV, ILLEGAL_CHARACTERS)


@common.time_execution(immediate=False)
def compile_tasks(videoid, task_handler, nfo_settings=None):
    """Compile a list of tasks for items based on the videoid"""
    common.debug('Compiling library tasks for {}', videoid)
    task = None

    if task_handler == export_item:
        metadata = api.metadata(videoid)
        if videoid.mediatype == common.VideoId.MOVIE:
            task = _create_export_movie_task(videoid, metadata[0], nfo_settings)
        elif videoid.mediatype in common.VideoId.TV_TYPES:
            task = _create_export_tv_tasks(videoid, metadata, nfo_settings)
        else:
            raise ValueError('Cannot handle {}'.format(videoid))

    if task_handler == export_new_item:
        metadata = api.metadata(videoid, True)
        task = _create_new_episodes_tasks(videoid, metadata, nfo_settings)

    if task_handler == remove_item:
        if videoid.mediatype == common.VideoId.MOVIE:
            task = _create_remove_movie_task(videoid)
        if videoid.mediatype == common.VideoId.SHOW:
            task = _compile_remove_tvshow_tasks(videoid)
        if videoid.mediatype == common.VideoId.SEASON:
            task = _compile_remove_season_tasks(videoid)
        if videoid.mediatype == common.VideoId.EPISODE:
            task = _create_remove_episode_task(videoid)

    if task is None:
        common.debug('compile_tasks: task_handler {} did not match any task for {}',
                     task_handler, videoid)
    return task


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
