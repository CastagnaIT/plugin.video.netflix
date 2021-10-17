# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Kodi library integration: task management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os
import re

import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
from resources.lib.common.exceptions import MetadataNotAvailable
from resources.lib.database.db_utils import VidLibProp
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.kodi.library_jobs import LibraryJobs
from resources.lib.kodi.library_utils import (get_episode_title_from_path, get_library_path,
                                              ILLEGAL_CHARACTERS, FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS)
from resources.lib.kodi.ui import show_library_task_errors
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


class LibraryTasks(LibraryJobs):
    """Compile the jobs for a videoid task and execute them"""

    def execute_library_task(self, videoid, task_type, nfo_settings=None, notify_errors=False):
        """
        Execute a library task for a videoid
        :param videoid: the videoid
        :param task_type: the type of task for the jobs (same used to execute the jobs)
        :param nfo_settings: the NFOSettings object containing the user's NFO settings
        :param notify_errors: if True a dialog box will be displayed at each error
        """
        list_errors = []
        # Preparation of jobs data for the task
        jobs_data = self.compile_jobs_data(videoid, task_type, nfo_settings)
        if not jobs_data:
            return
        total_jobs = len(jobs_data)
        # Execute the jobs for the task
        for index, job_data in enumerate(jobs_data):
            self._execute_job(task_type, job_data, list_errors)
            yield index, total_jobs, job_data['title']
        show_library_task_errors(notify_errors, list_errors)

    def execute_library_task_gui(self, videoid, task_type, title, nfo_settings=None, show_prg_dialog=True):
        """
        Execute a library task for a videoid, by showing a GUI progress bar/dialog
        :param videoid: the videoid
        :param task_type: the type of task for the jobs (same used to execute the jobs)
        :param title: title for the progress dialog/background progress bar
        :param nfo_settings: the NFOSettings object containing the user's NFO settings
        :param show_prg_dialog: if True show progress dialog, otherwise, a background progress bar
        """
        list_errors = []
        # Preparation of jobs data for the task
        jobs_data = self.compile_jobs_data(videoid, task_type, nfo_settings)
        # Set a progress bar
        progress_class = ui.ProgressDialog if show_prg_dialog else ui.ProgressBarBG
        with progress_class(show_prg_dialog, title, max_value=len(jobs_data)) as progress_bar:
            # Execute the jobs for the task
            for job_data in jobs_data:
                self._execute_job(task_type, job_data, list_errors)
                progress_bar.perform_step()
                progress_bar.set_message(f'{job_data["title"]} ({progress_bar.value}/{progress_bar.max_value})')
                if progress_bar.is_cancelled():
                    LOG.warn('Library operations interrupted by User')
                    break
                if self.monitor.abortRequested():
                    LOG.warn('Library operations interrupted by Kodi')
                    break
        show_library_task_errors(show_prg_dialog, list_errors)

    def _execute_job(self, job_handler, job_data, list_errors):
        if not job_data:  # No metadata or unexpected job case
            return
        try:
            job_handler(job_data, get_library_path())
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            LOG.error(traceback.format_exc())
            LOG.error('{} of {} ({}) failed', job_handler.__name__, job_data['videoid'], job_data['title'])
            list_errors.append({'title': job_data['title'],
                                'error': f'{type(exc).__name__}: {exc}'})

    @measure_exec_time_decorator(is_immediate=True)
    def compile_jobs_data(self, videoid, task_type, nfo_settings=None):
        """Compile a list of jobs data based on the videoid"""
        LOG.debug('Compiling list of jobs data for task handler "{}" and videoid "{}"',
                  task_type.__name__, videoid)
        jobs_data = None
        try:
            if task_type == self.export_item:
                metadata = self.ext_func_get_metadata(videoid)  # pylint: disable=not-callable
                if videoid.mediatype == common.VideoId.MOVIE:
                    jobs_data = [self._create_export_movie_job(videoid, metadata[0], nfo_settings)]
                if videoid.mediatype in common.VideoId.TV_TYPES:
                    jobs_data = self._create_export_tvshow_jobs(videoid, metadata, nfo_settings)

            if task_type == self.export_new_item:
                metadata = self.ext_func_get_metadata(videoid, True)  # pylint: disable=not-callable
                jobs_data = self._create_export_new_episodes_jobs(videoid, metadata, nfo_settings)

            if task_type == self.remove_item:
                if videoid.mediatype == common.VideoId.MOVIE:
                    jobs_data = [self._create_remove_movie_job(videoid)]
                if videoid.mediatype == common.VideoId.SHOW:
                    jobs_data = self._create_remove_tvshow_jobs(videoid)
                if videoid.mediatype == common.VideoId.SEASON:
                    jobs_data = self._create_remove_season_jobs(videoid)
                if videoid.mediatype == common.VideoId.EPISODE:
                    jobs_data = [self._create_remove_episode_job(videoid)]
        except MetadataNotAvailable:
            LOG.warn('Unavailable metadata for videoid "{}", list of jobs not compiled', videoid)
            return None
        if jobs_data is None:
            LOG.error('Unexpected job compile case for task type "{}" and videoid "{}", list of jobs not compiled',
                      task_type.__name__, videoid)
        return jobs_data

    def _create_export_movie_job(self, videoid, movie, nfo_settings):
        """Create job data to export a movie"""
        # Reset NFO export to false if we never want movies nfo
        filename = f'{movie["title"]} ({movie["year"]})'
        create_nfo_file = nfo_settings and nfo_settings.export_movie_enabled
        nfo_data = nfo.create_movie_nfo(movie) if create_nfo_file else None
        return self._build_export_job_data(True, create_nfo_file,
                                           videoid=videoid, title=movie['title'],
                                           root_folder_name=FOLDER_NAME_MOVIES,
                                           folder_name=filename,
                                           filename=filename,
                                           nfo_data=nfo_data)

    def _create_export_tvshow_jobs(self, videoid, metadata, nfo_settings):
        """
        Create jobs data to export a: tv show, season or episode.
        The data for the jobs will be generated by extrapolating every single episode.
        """
        if videoid.mediatype == common.VideoId.SHOW:
            tasks = self._get_export_tvshow_jobs(videoid, metadata[0], nfo_settings)
        elif videoid.mediatype == common.VideoId.SEASON:
            tasks = self._get_export_season_jobs(videoid,
                                                 metadata[0],
                                                 common.find(int(videoid.seasonid),
                                                             'id',
                                                             metadata[0]['seasons']),
                                                 nfo_settings)
        else:
            tasks = [self._create_export_episode_job(videoid, *metadata, nfo_settings=nfo_settings)]

        if nfo_settings and nfo_settings.export_full_tvshow:
            # Create tvshow.nfo file
            # In episode metadata, the show data is at 3rd position,
            # In show metadata, the show data is at 1st position.
            # Best is to enumerate values to find the correct key position
            key_index = -1
            for i, item in enumerate(metadata):
                if item and item.get('type', None) == 'show':
                    key_index = i
            if key_index > -1:
                tasks.append(self._build_export_job_data(False, True,
                                                         videoid=videoid, title='tvshow.nfo',
                                                         root_folder_name=FOLDER_NAME_SHOWS,
                                                         folder_name=metadata[key_index]['title'],
                                                         filename='tvshow',
                                                         nfo_data=nfo.create_show_nfo(metadata[key_index])))
        return tasks

    def _get_export_tvshow_jobs(self, videoid, show, nfo_settings):
        """Get jobs data to export a tv show (join all jobs data of the seasons)"""
        tasks = []
        for season in show['seasons']:
            tasks += self._get_export_season_jobs(videoid.derive_season(season['id']), show, season, nfo_settings)
        return tasks

    def _get_export_season_jobs(self, videoid, show, season, nfo_settings):
        """Get jobs data to export a season (join all jobs data of the episodes)"""
        return [self._create_export_episode_job(videoid.derive_episode(episode['id']),
                                                episode, season, show, nfo_settings)
                for episode in season['episodes']]

    def _create_export_episode_job(self, videoid, episode, season, show, nfo_settings):
        """Create job data to export a single episode"""
        filename = f'S{season["seq"]:02d}E{episode["seq"]:02d}'
        title = ' - '.join((show['title'], filename))
        create_nfo_file = nfo_settings and nfo_settings.export_tvshow_enabled
        nfo_data = nfo.create_episode_nfo(episode, season, show) if create_nfo_file else None
        return self._build_export_job_data(True, create_nfo_file,
                                           videoid=videoid, title=title,
                                           root_folder_name=FOLDER_NAME_SHOWS,
                                           folder_name=show['title'],
                                           filename=filename,
                                           nfo_data=nfo_data)

    def _build_export_job_data(self, create_strm_file, create_nfo_file, **kwargs):
        """Build the data used to execute an "export" job"""
        return {
            'create_strm_file': create_strm_file,  # True/False
            'create_nfo_file': create_nfo_file,  # True/False
            'videoid': kwargs['videoid'],
            'title': kwargs['title'],  # Progress dialog and debug purpose
            'root_folder_name': kwargs['root_folder_name'],
            'folder_name': re.sub(ILLEGAL_CHARACTERS, '', kwargs['folder_name']),
            'filename': re.sub(ILLEGAL_CHARACTERS, '', kwargs['filename']),
            'nfo_data': kwargs['nfo_data']
        }

    def _create_export_new_episodes_jobs(self, videoid, metadata, nfo_settings=None):
        """Create jobs data to export missing seasons and episodes"""
        tasks = []
        if metadata and 'seasons' in metadata[0]:
            for season in metadata[0]['seasons']:
                if not nfo_settings:
                    nfo_export = G.SHARED_DB.get_tvshow_property(videoid.value, VidLibProp['nfo_export'], False)
                    nfo_settings = nfo.NFOSettings(nfo_export)
                # Check and add missing seasons and episodes
                self._add_missing_items(tasks, season, videoid, metadata, nfo_settings)
        return tasks

    def _add_missing_items(self, tasks, season, videoid, metadata, nfo_settings):
        if G.SHARED_DB.season_id_exists(videoid.value, season['id']):
            # The season exists, try to find any missing episode
            for episode in season['episodes']:
                if not G.SHARED_DB.episode_id_exists(videoid.value, season['id'], episode['id']):
                    tasks.append(self._create_export_episode_job(
                        videoid=videoid.derive_season(season['id']).derive_episode(episode['id']),
                        episode=episode,
                        season=season,
                        show=metadata[0],
                        nfo_settings=nfo_settings
                    ))
                    LOG.debug('Exporting missing new episode {}', episode['id'])
        else:
            # The season does not exist, build task for the season
            tasks += self._get_export_season_jobs(
                videoid=videoid.derive_season(season['id']),
                show=metadata[0],
                season=season,
                nfo_settings=nfo_settings
            )
            LOG.debug('Exporting missing new season {}', season['id'])

    def _create_remove_movie_job(self, videoid):
        """Create a job data to remove a movie"""
        file_path = G.SHARED_DB.get_movie_filepath(videoid.value)
        title = os.path.splitext(os.path.basename(file_path))[0]
        return self._build_remove_job_data(title, file_path, videoid)

    def _create_remove_tvshow_jobs(self, videoid):
        """Create jobs data to remove a tv show (will result jobs data of all the episodes)"""
        row_results = G.SHARED_DB.get_all_episodes_ids_and_filepath_from_tvshow(videoid.value)
        return self._create_remove_jobs_from_rows(row_results)

    def _create_remove_season_jobs(self, videoid):
        """Create jobs data to remove a season (will result jobs data of all the episodes)"""
        row_results = G.SHARED_DB.get_all_episodes_ids_and_filepath_from_season(
            videoid.tvshowid, videoid.seasonid)
        return self._create_remove_jobs_from_rows(row_results)

    def _create_remove_episode_job(self, videoid):
        """Create a job data to remove an episode"""
        file_path = G.SHARED_DB.get_episode_filepath(
            videoid.tvshowid, videoid.seasonid, videoid.episodeid)
        return self._build_remove_job_data(get_episode_title_from_path(file_path),
                                           file_path, videoid)

    def _create_remove_jobs_from_rows(self, row_results):
        """Create jobs data to remove episodes, from the rows results of the database"""
        return [self._build_remove_job_data(get_episode_title_from_path(row['FilePath']),
                                            row['FilePath'],
                                            common.VideoId(tvshowid=row['TvShowID'],
                                                           seasonid=row['SeasonID'],
                                                           episodeid=row['EpisodeID']))
                for row in row_results]

    def _build_remove_job_data(self, title, file_path, videoid):
        """Build the data used to execute an "remove" job"""
        return {
            'title': title,  # Progress dialog and debug purpose
            'file_path': file_path,
            'videoid': videoid
        }
