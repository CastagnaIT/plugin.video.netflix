# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation handler for library actions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
import resources.lib.kodi.library as library
import resources.lib.kodi.library_autoupdate as library_au
import resources.lib.kodi.library_items as library_items
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.globals import g


class LibraryActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing "LibraryActionExecutor" with params: {}', params)
        self.params = params

    @common.inject_video_id(path_offset=1)
    def export(self, videoid):
        """Export an item to the Kodi library"""
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype)
        library.execute_library_tasks(videoid,
                                      [library.export_item],
                                      common.get_local_string(30018),
                                      nfo_settings=nfo_settings)

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        if ui.ask_for_confirmation(common.get_local_string(30030), common.get_local_string(30124)):
            library.execute_library_tasks(videoid,
                                          [library.remove_item],
                                          common.get_local_string(30030))
            common.refresh_container(use_delay=True)

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype)
        library.execute_library_tasks(videoid,
                                      [library.remove_item, library.export_item],
                                      common.get_local_string(30061),
                                      nfo_settings=nfo_settings)
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    def export_silent(self, videoid):
        """Silently export an item to the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to.
        Will only ask for NFO export based on user settings"""
        # pylint: disable=broad-except
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog(videoid.mediatype, common.get_local_string(30191))
        library.execute_library_tasks_silently(
            videoid, [library.export_item],
            nfo_settings=nfo_settings)

    @common.inject_video_id(path_offset=1)
    def remove_silent(self, videoid):
        """Silently remove an item from the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        library.execute_library_tasks_silently(
            videoid, [library.remove_item])

    # Not used for now
    # @common.inject_video_id(path_offset=1)
    # def update_silent(self, videoid):
    #    """Silently update an item in the Kodi library
    #    (without GUI feedback). This will ignore the setting for syncing my
    #    list and Kodi library and do no sync, if not explicitly asked to."""
    #    library.execute_library_tasks_silently(
    #        videoid, [library.remove_item, library.export_item])

    def sync_mylist(self, pathitems):  # pylint: disable=unused-argument
        """
        Perform a full sync of Netflix "My List" with the Kodi library
        """
        if not ui.ask_for_confirmation(common.get_local_string(30122),
                                       common.get_local_string(30123)):
            return
        library.sync_mylist_to_library()

    def auto_upd_run_now(self, pathitems):  # pylint: disable=unused-argument
        """
        Perform an auto update of Kodi library to add new seasons/episodes of tv shows
        """
        if not ui.ask_for_confirmation(common.get_local_string(30065),
                                       common.get_local_string(30231)):
            return
        library_au.auto_update_library(False, False)

    def _get_mylist_profile_guid(self):
        return g.SHARED_DB.get_value('sync_mylist_profile_guid',
                                     g.LOCAL_DB.get_guid_owner_profile())

    def sync_mylist_sel_profile(self, pathitems):  # pylint: disable=unused-argument
        """
        Set the current profile for the synchronization of Netflix "My List" with the Kodi library
        """
        g.SHARED_DB.set_value('sync_mylist_profile_guid', g.LOCAL_DB.get_active_profile_guid())
        profile_name = g.LOCAL_DB.get_profile_config('profileName', '')
        ui.show_notification(common.get_local_string(30223).format(profile_name), time=10000)

    def sync_mylist_shw_profile(self, pathitems):  # pylint: disable=unused-argument
        """
        Show the name of profile chosen
        for the synchronization of Netflix "My List" with the Kodi library
        """
        profile_guid = self._get_mylist_profile_guid()
        profile_name = g.LOCAL_DB.get_profile_config('profileName', '', profile_guid)
        ui.show_ok_dialog('Netflix',
                          common.get_local_string(30223).format(profile_name))

    def purge(self, pathitems):  # pylint: disable=unused-argument
        """Delete all previously exported items from the Kodi library"""
        if ui.ask_for_confirmation(common.get_local_string(30125),
                                   common.get_local_string(30126)):
            library.purge()

    def migrate(self, pathitems):  # pylint: disable=unused-argument
        """Migrate exported items from old library format to the new format"""
        for videoid in library_items.get_previously_exported_items():
            library.execute_library_tasks(videoid, [library.export_item],
                                          common.get_local_string(30018))

    @common.inject_video_id(path_offset=1)
    def export_new_episodes(self, videoid):
        library.export_new_episodes(videoid)

    @common.inject_video_id(path_offset=1)
    def exclude_from_auto_update(self, videoid):
        library_au.exclude_show_from_auto_update(videoid, True)
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    def include_in_auto_update(self, videoid):
        library_au.exclude_show_from_auto_update(videoid, False)
        common.refresh_container()

    def mysql_test(self, pathitems):
        """Perform a MySQL database connection test"""
        # Todo: when menu action is called, py restart addon and global attempts
        #  to initialize the database and then the test is also performed
        #  in addition, you must also wait for the timeout to obtain any connection error
        #  Perhaps creating a particular modal dialog with connection parameters can help

    def set_autoupdate_device(self, pathitems):  # pylint: disable=unused-argument
        """Set the current device to manage auto-update of the shared-library (MySQL)"""
        random_uuid = common.get_random_uuid()
        g.LOCAL_DB.set_value('client_uuid', random_uuid)
        g.SHARED_DB.set_value('auto_update_device_uuid', random_uuid)
        ui.show_notification(common.get_local_string(30209), time=8000)

    def check_autoupdate_device(self, pathitems):  # pylint: disable=unused-argument
        """Check if the current device manage the auto-updates of the shared-library (MySQL)"""
        uuid = g.SHARED_DB.get_value('auto_update_device_uuid')
        if uuid is None:
            msg = common.get_local_string(30212)
        else:
            client_uuid = g.LOCAL_DB.get_value('client_uuid')
            msg = common.get_local_string(30210) \
                if client_uuid == uuid else common.get_local_string(30211)
        ui.show_notification(msg, time=8000)
