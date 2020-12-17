# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation handler for library actions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
import resources.lib.kodi.ui as ui
import resources.lib.kodi.library_utils as lib_utils
from resources.lib.globals import G
from resources.lib.kodi.library import get_library_cls
from resources.lib.utils.logging import LOG


# pylint: disable=no-self-use
class LibraryActionExecutor:
    """Executes actions"""

    def __init__(self, params):
        LOG.debug('Initializing "LibraryActionExecutor" with params: {}', params)
        self.params = params

    @common.inject_video_id(path_offset=1)
    def export(self, videoid):
        """Export an item to the Kodi library"""
        get_library_cls().export_to_library(videoid)
        common.container_refresh()

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        if not ui.ask_for_confirmation(common.get_local_string(30030),
                                       common.get_local_string(30124)):
            return
        get_library_cls().remove_from_library(videoid)
        common.container_refresh(use_delay=True)

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        get_library_cls().update_library(videoid)
        common.container_refresh()

    def sync_mylist(self, pathitems):  # pylint: disable=unused-argument
        """
        Perform a full sync of Netflix "My List" with the Kodi library
        """
        if not ui.ask_for_confirmation(common.get_local_string(30122),
                                       common.get_local_string(30123)):
            return
        get_library_cls().sync_library_with_mylist()

    def auto_upd_run_now(self, pathitems):  # pylint: disable=unused-argument
        """
        Perform an auto update of Kodi library to add new seasons/episodes of tv shows
        """
        if not ui.ask_for_confirmation(common.get_local_string(30065),
                                       common.get_local_string(30231)):
            return
        get_library_cls().auto_update_library(False)

    def sync_mylist_sel_profile(self, pathitems):  # pylint: disable=unused-argument
        """
        Select a profile for the synchronization of Kodi library with Netflix "My List"
        """
        if _check_auto_update_running():
            return
        preselect_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid',
                                               G.LOCAL_DB.get_guid_owner_profile())
        selected_guid = ui.show_profiles_dialog(title=common.get_local_string(30228),
                                                preselect_guid=preselect_guid)
        if not selected_guid:
            return
        G.SHARED_DB.set_value('sync_mylist_profile_guid', selected_guid)

    def purge(self, pathitems):  # pylint: disable=unused-argument
        """Delete all previously exported items from the Kodi library"""
        if _check_auto_update_running():
            return
        if not ui.ask_for_confirmation(common.get_local_string(30125),
                                       common.get_local_string(30126)):
            return
        get_library_cls().clear_library()

    def import_library(self, pathitems):  # pylint: disable=unused-argument
        """Import previous exported STRM files to add-on and/or convert them to the current STRM format type"""
        if _check_auto_update_running():
            return
        path = ui.show_browse_dialog(common.get_local_string(651), default_path=G.DATA_PATH)
        if path:
            if not ui.ask_for_confirmation(common.get_local_string(30140),
                                           common.get_local_string(20135)):
                return
            get_library_cls().import_library(path)

    @common.inject_video_id(path_offset=1)
    def export_new_episodes(self, videoid):
        get_library_cls().export_to_library_new_episodes(videoid)

    @common.inject_video_id(path_offset=1)
    def exclude_from_auto_update(self, videoid):
        lib_utils.set_show_excluded_from_auto_update(videoid, True)
        common.container_refresh()

    @common.inject_video_id(path_offset=1)
    def include_in_auto_update(self, videoid):
        lib_utils.set_show_excluded_from_auto_update(videoid, False)
        common.container_refresh()

    def mysql_test(self, pathitems):
        """Perform a MySQL database connection test"""
        # Todo: when menu action is called, py restart addon and global attempts
        #  to initialize the database and then the test is also performed
        #  in addition, you must also wait for the timeout to obtain any connection error
        #  Perhaps creating a particular modal dialog with connection parameters can help

    def set_autoupdate_device(self, pathitems):  # pylint: disable=unused-argument
        """Set the current device to manage auto-update of the shared-library (MySQL)"""
        if _check_auto_update_running():
            return
        random_uuid = common.get_random_uuid()
        G.LOCAL_DB.set_value('client_uuid', random_uuid)
        G.SHARED_DB.set_value('auto_update_device_uuid', random_uuid)
        ui.show_notification(common.get_local_string(30209), time=8000)

    def check_autoupdate_device(self, pathitems):  # pylint: disable=unused-argument
        """Check if the current device manage the auto-updates of the shared-library (MySQL)"""
        uuid = G.SHARED_DB.get_value('auto_update_device_uuid')
        if uuid is None:
            msg = common.get_local_string(30212)
        else:
            client_uuid = G.LOCAL_DB.get_value('client_uuid')
            msg = common.get_local_string(30210 if client_uuid == uuid else 30211)
        ui.show_notification(msg, time=8000)


def _check_auto_update_running():
    return lib_utils.is_auto_update_library_running(True)
