# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2020 Stefano Gottardo
    Kodi library integration

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os
from datetime import datetime

import xbmcvfs

import resources.lib.utils.api_requests as api
import resources.lib.common as common
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import VidLibProp
from resources.lib.globals import G
from resources.lib.kodi.library_tasks import LibraryTasks
from resources.lib.kodi.library_utils import (request_kodi_library_update, get_library_path,
                                              FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS,
                                              is_auto_update_library_running, request_kodi_library_scan_decorator,
                                              get_library_subfolders, delay_anti_ban)
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


# Reasons that led to the creation of a class for the library operations:
# - Time-consuming update functionality like "full sync of kodi library", "auto update", "export" (large tv show)
#    from context menu or settings, can not be performed within of the service side or will cause IPC timeouts
#    and could block IPC access for other actions at same time.
# - The scheduled update operation for the library must be performed within the service, with the goal of:
#    - Avoid tons of IPC calls that cause the continuous display of the loading screens while using Kodi
#      to do other things at same time
#    - Avoid use the IPC can improve the time for completion and so improve a bit the cpu use
# - Allows you to check when Kodi will be closed and avoid the force close of the add-on
# - A class allows you to choice to retrieve the data from Netflix by using IPC or directly nfsession.
# The time needed to initialize the class at each operation (about 30ms) is a small cost compared to the advantages.


def get_library_cls():
    """
    Get the library class to do library operations
    FUNCTION NOT TO BE USED IN ADD-ON SERVICE INSTANCE
    """
    # This build a instance of library class by assigning access to external functions through IPC
    return Library(api.get_metadata, api.get_mylist_videoids_profile_switch, None)


class Library(LibraryTasks):
    """Kodi library integration"""

    def __init__(self, func_get_metadata, func_get_mylist_videoids_profile_switch, func_req_profiles_info):
        # External functions
        self.ext_func_get_metadata = func_get_metadata
        self.ext_func_get_mylist_videoids_profile_switch = func_get_mylist_videoids_profile_switch
        self.ext_func_req_profiles_info = func_req_profiles_info

    @request_kodi_library_scan_decorator
    def export_to_library(self, videoid, show_prg_dialog=True):
        """
        Export an item to the Kodi library
        :param videoid: the videoid
        :param show_prg_dialog: if True show progress dialog, otherwise, a background progress bar
        """
        LOG.info('Start exporting {} to the library', videoid)
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype)
        self.execute_library_task_gui(videoid,
                                      self.export_item,
                                      title=common.get_local_string(30018),
                                      nfo_settings=nfo_settings,
                                      show_prg_dialog=show_prg_dialog)

    @request_kodi_library_scan_decorator
    def export_to_library_new_episodes(self, videoid, show_prg_dialog=True):
        """
        Export new episodes for a tv show by it's videoid
        :param videoid: The videoid of the tv show to process
        :param show_prg_dialog: if True show progress dialog, otherwise, a background progress bar
        """
        LOG.info('Start exporting new episodes for {}', videoid)
        if videoid.mediatype != common.VideoId.SHOW:
            LOG.warn('{} is not a tv show, the operation is cancelled', videoid)
            return
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype)
        self.execute_library_task_gui(videoid,
                                      self.export_new_item,
                                      title=common.get_local_string(30198),
                                      nfo_settings=nfo_settings,
                                      show_prg_dialog=show_prg_dialog)

    @request_kodi_library_scan_decorator
    def update_library(self, videoid, show_prg_dialog=True):
        """
        Update items in the Kodi library
        :param videoid: the videoid
        :param show_prg_dialog: if True show progress dialog, otherwise, a background progress bar
        """
        LOG.info('Start updating {} in the library', videoid)
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype)
        self.execute_library_task_gui(videoid,
                                      self.remove_item,
                                      title=common.get_local_string(30061),
                                      nfo_settings=nfo_settings,
                                      show_prg_dialog=show_prg_dialog)
        self.execute_library_task_gui(videoid,
                                      self.export_item,
                                      title=common.get_local_string(30061),
                                      nfo_settings=nfo_settings,
                                      show_prg_dialog=show_prg_dialog)

    def remove_from_library(self, videoid, show_prg_dialog=True):
        """
        Remove an item from the Kodi library
        :param videoid: the videoid
        :param show_prg_dialog: if True show progress dialog, otherwise, a background progress bar
        """
        LOG.info('Start removing {} from library', videoid)
        common.remove_videoid_from_kodi_library(videoid)
        self.execute_library_task_gui(videoid,
                                      self.remove_item,
                                      title=common.get_local_string(30030),
                                      show_prg_dialog=show_prg_dialog)

    def sync_library_with_mylist(self):
        """
        Perform a full sync of Kodi library with Netflix "My List",
        by deleting everything that was previously exported
        """
        LOG.info('Performing sync of Kodi library with My list')
        # Clear all the library
        self.clear_library()
        # Start the sync
        self.auto_update_library(True, show_nfo_dialog=True, clear_on_cancel=True)

    @measure_exec_time_decorator(is_immediate=True)
    def clear_library(self, show_prg_dialog=True):
        """
        Delete all exported items to the library
        :param show_prg_dialog: if True, will be show a progress dialog window
        """
        LOG.info('Start deleting exported library items')
        # This will clear all the add-on library data, to prevents possible inconsistencies when for some reason
        # such as improper use of the add-on, unexpected error or other has broken the library database data or files
        with ui.ProgressDialog(show_prg_dialog, common.get_local_string(30245), max_value=3) as progress_dlg:
            progress_dlg.perform_step()
            progress_dlg.set_wait_message()
            G.SHARED_DB.purge_library()
            for folder_name in [FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS]:
                progress_dlg.perform_step()
                progress_dlg.set_wait_message()
                section_root_dir = common.join_folders_paths(get_library_path(), folder_name)
                common.delete_folder_contents(section_root_dir, delete_subfolders=True)
        # Clean the Kodi library database
        common.clean_library(show_prg_dialog, get_library_path())

    def auto_update_library(self, sync_with_mylist, show_prg_dialog=True, show_nfo_dialog=False, clear_on_cancel=False,
                            update_profiles=False):
        """
        Perform an auto update of the exported items in to Kodi library.
        - The main purpose is check if there are new seasons/episodes.
        - In the case "Sync Kodi library with My list" feature is enabled, will be also synchronized with My List.
        :param sync_with_mylist: if True, sync the Kodi library with Netflix My List
        :param show_prg_dialog: if True, will be show a progress dialog window and the errors will be notified to user
        :param show_nfo_dialog: if True, ask to user if want export NFO files (override custom NFO actions for videoid)
        :param clear_on_cancel: if True, when the user cancel the operations will be cleared the entire library
        :param update_profiles: if True, before perform sync_with_mylist will be updated the profiles
        """
        if is_auto_update_library_running(show_prg_dialog):
            return
        LOG.info('Start auto-updating of Kodi library {}', '(with sync of My List)' if sync_with_mylist else '')
        G.SHARED_DB.set_value('library_auto_update_is_running', True)
        G.SHARED_DB.set_value('library_auto_update_start_time', datetime.now())
        try:
            # Get the full list of the exported tvshows/movies as id (VideoId.value)
            exp_tvshows_videoids_values = G.SHARED_DB.get_tvshows_id_list()
            exp_movies_videoids_values = G.SHARED_DB.get_movies_id_list()

            # Get the exported tv shows (to be updated) as dict (key=videoid, value=type of task)
            videoids_tasks = {
                common.VideoId.from_path([common.VideoId.SHOW, videoid_value]): self.export_new_item
                for videoid_value in G.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'], False)
            }
            if sync_with_mylist and update_profiles:
                # Before do the sync with My list try to update the profiles in the database,
                # to do a sanity check of the features that are linked to the profiles
                self.ext_func_req_profiles_info(update_database=True)  # pylint: disable=not-callable
                sync_with_mylist = G.ADDON.getSettingBool('lib_sync_mylist')
            # If enabled sync the Kodi library with Netflix My List
            if sync_with_mylist:
                self._sync_my_list_ops(videoids_tasks, exp_tvshows_videoids_values, exp_movies_videoids_values)

            # Show a warning message when there are more than 100 titles to be updated, making too many metadata
            # requests may cause blocking of http communication from the server or temporary ban of the account
            if show_prg_dialog:
                total_titles_upd = sum(task != self.remove_item for task in videoids_tasks.values())
                if total_titles_upd >= 100 and not ui.ask_for_confirmation(
                        common.get_local_string(30122),
                        common.get_local_string(30059).format(total_titles_upd)):
                    return
            # Start the update operations
            ret = self._update_library(videoids_tasks, exp_tvshows_videoids_values, show_prg_dialog, show_nfo_dialog,
                                       clear_on_cancel)
            if not ret:
                return
            request_kodi_library_update(scan=True, clean=True)
            # Save date for completed operation to compute next update schedule (used in library_updater.py)
            G.SHARED_DB.set_value('library_auto_update_last_start', datetime.now())
            LOG.info('Auto update of the Kodi library completed')
            if not G.ADDON.getSettingBool('lib_auto_upd_disable_notification'):
                ui.show_notification(common.get_local_string(30220), time=5000)
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            LOG.error('An error has occurred in the library auto update: {}', exc)
            LOG.error(traceback.format_exc())
        finally:
            G.SHARED_DB.set_value('library_auto_update_is_running', False)

    def _sync_my_list_ops(self, videoids_tasks, exp_tvshows_videoids_values, exp_movies_videoids_values):
        # Get videoids from the My list (of the chosen profile)
        # pylint: disable=not-callable
        mylist_video_id_list, mylist_video_id_list_type = self.ext_func_get_mylist_videoids_profile_switch()

        # Check if tv shows have been removed from the My List
        for videoid_value in exp_tvshows_videoids_values:
            if str(videoid_value) in mylist_video_id_list:
                continue
            # The tv show no more exist in My List so remove it from library
            videoid = common.VideoId.from_path([common.VideoId.SHOW, videoid_value])
            videoids_tasks.update({videoid: self.remove_item})

        # Check if movies have been removed from the My List
        for videoid_value in exp_movies_videoids_values:
            if str(videoid_value) in mylist_video_id_list:
                continue
            # The movie no more exist in My List so remove it from library
            videoid = common.VideoId.from_path([common.VideoId.MOVIE, videoid_value])
            videoids_tasks.update({videoid: self.remove_item})

        # Add to library the missing tv shows / movies of My List
        for index, videoid_value in enumerate(mylist_video_id_list):
            if (int(videoid_value) not in exp_tvshows_videoids_values and
                    int(videoid_value) not in exp_movies_videoids_values):
                is_movie = mylist_video_id_list_type[index] == 'movie'
                videoid = common.VideoId(**{('movieid' if is_movie else 'tvshowid'): videoid_value})
                videoids_tasks.update({videoid: self.export_item if is_movie else self.export_new_item})

    def _update_library(self, videoids_tasks, exp_tvshows_videoids_values, show_prg_dialog, show_nfo_dialog,
                        clear_on_cancel):
        # If set ask to user if want to export NFO files (override user custom NFO settings for videoids)
        nfo_settings_override = None
        if show_nfo_dialog:
            nfo_settings_override = nfo.NFOSettings()
            nfo_settings_override.show_export_dialog()
        # Get the exported tvshows, but to be excluded from the updates
        excluded_videoids_values = G.SHARED_DB.get_tvshows_id_list(VidLibProp['exclude_update'], True)
        # Start the update operations
        with ui.ProgressDialog(show_prg_dialog, max_value=len(videoids_tasks)) as progress_bar:
            for videoid, task_handler in videoids_tasks.items():
                # Check if current videoid is excluded from updates
                if int(videoid.value) in excluded_videoids_values:
                    continue
                # Get the NFO settings for the current videoid
                if not nfo_settings_override and int(videoid.value) in exp_tvshows_videoids_values:
                    # User custom NFO setting
                    # it is possible that the user has chosen not to export NFO files for a specific tv show
                    nfo_export = G.SHARED_DB.get_tvshow_property(videoid.value,
                                                                 VidLibProp['nfo_export'], False)
                    nfo_settings = nfo.NFOSettings(nfo_export)
                else:
                    nfo_settings = nfo_settings_override or nfo.NFOSettings()
                # Execute the task
                for index, total_tasks, title in self.execute_library_task(videoid,
                                                                           task_handler,
                                                                           nfo_settings=nfo_settings,
                                                                           notify_errors=show_prg_dialog):
                    label_partial_op = f' ({index + 1}/{total_tasks})' if total_tasks > 1 else ''
                    progress_bar.set_message(title + label_partial_op)
                if progress_bar.is_cancelled():
                    LOG.warn('Auto update of the Kodi library interrupted by User')
                    if clear_on_cancel:
                        self.clear_library(True)
                    return False
                if self.monitor.abortRequested():
                    LOG.warn('Auto update of the Kodi library interrupted by Kodi')
                    return False
                progress_bar.perform_step()
                progress_bar.set_wait_message()
                delay_anti_ban()
        return True

    def import_library(self, path):
        """
        Imports an already existing exported STRM library into the add-on library database,
        allows you to restore an existing library, by avoiding to recreate it from scratch.
        This operations also update the missing tv shows seasons and episodes, and automatically
        converts old STRM format type from add-on version 0.13.x or before 1.7.0 to new format.
        """
        # If set ask to user if want to export NFO files
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog()
        LOG.info('Start importing Kodi library')
        remove_folders = []  # List of failed imports paths to be optionally removed
        remove_titles = []  # List of failed imports titles to be optionally removed
        # Start importing STRM files
        folders = get_library_subfolders(FOLDER_NAME_MOVIES, path) + get_library_subfolders(FOLDER_NAME_SHOWS, path)
        with ui.ProgressDialog(True, max_value=len(folders)) as progress_bar:
            for folder_path in folders:
                folder_name = os.path.basename(xbmcvfs.translatePath(folder_path))
                progress_bar.set_message(folder_name)
                try:
                    videoid = self.import_videoid_from_existing_strm(folder_path, folder_name)
                    if videoid is None:
                        # Failed to import, add folder to remove list
                        remove_folders.append(folder_path)
                        remove_titles.append(folder_name)
                        continue
                    # Successfully imported, Execute the task
                    for index, total_tasks, title in self.execute_library_task(videoid,
                                                                               self.export_item,
                                                                               nfo_settings=nfo_settings,
                                                                               notify_errors=True):
                        label_partial_op = f' ({index + 1}/{total_tasks})' if total_tasks > 1 else ''
                        progress_bar.set_message(title + label_partial_op)
                    if progress_bar.is_cancelled():
                        LOG.warn('Import library interrupted by User')
                        return
                    if self.monitor.abortRequested():
                        LOG.warn('Import library interrupted by Kodi')
                        return
                except ImportWarning:
                    # Ignore it, something was wrong in STRM file (see _import_videoid in library_jobs.py)
                    pass
                progress_bar.perform_step()
                progress_bar.set_wait_message()
                delay_anti_ban()
        ret = self._import_library_remove(remove_titles, remove_folders)
        request_kodi_library_update(scan=True, clean=ret)

    def _import_library_remove(self, remove_titles, remove_folders):
        if not remove_folders:
            return False
        # If there are STRM files that it was not possible to import them,
        # we will ask to user if you want to delete them
        tot_folders = len(remove_folders)
        if tot_folders > 50:
            remove_titles = remove_titles[:50] + ['...']
        message = common.get_local_string(30246).format(tot_folders) + '[CR][CR]' + ', '.join(remove_titles)
        if not ui.ask_for_confirmation(common.get_local_string(30140), message):
            return False
        # Delete all folders
        LOG.info('Start deleting folders')
        with ui.ProgressDialog(True, max_value=tot_folders) as progress_bar:
            for file_path in remove_folders:
                progress_bar.set_message(f'{progress_bar.value}/{tot_folders}')
                LOG.debug('Deleting folder: {}', file_path)
                common.delete_folder(file_path)
                progress_bar.perform_step()
        return True
