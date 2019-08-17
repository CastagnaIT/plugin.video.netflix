# -*- coding: utf-8 -*-
"""Navigation handler for library actions"""
from __future__ import unicode_literals

import resources.lib.api.shakti as api
import resources.lib.common as common
import resources.lib.kodi.library as library
import resources.lib.kodi.nfo as nfo
import resources.lib.kodi.ui as ui
from resources.lib.globals import g


class LibraryActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing LibraryActionExecutor: {}'
                     .format(params))
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
        if ui.ask_for_removal_confirmation():
            library.execute_library_tasks(videoid,
                                          [library.remove_item],
                                          common.get_local_string(30030))
            common.refresh_container()

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
            sync_mylist=self.params.get('sync_mylist', False),
            nfo_settings=nfo_settings)

    @common.inject_video_id(path_offset=1)
    def remove_silent(self, videoid):
        """Silently remove an item from the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        library.execute_library_tasks_silently(
            videoid, [library.remove_item],
            sync_mylist=self.params.get('sync_mylist', False))

    # Not used for now
    # @common.inject_video_id(path_offset=1)
    # def update_silent(self, videoid):
    #    """Silently update an item in the Kodi library
    #    (without GUI feedback). This will ignore the setting for syncing my
    #    list and Kodi library and do no sync, if not explicitly asked to."""
    #    library.execute_library_tasks_silently(
    #        videoid, [library.remove_item, library.export_item],
    #        sync_mylist=self.params.get('sync_mylist', False))

    def initial_mylist_sync(self, pathitems):
        """Perform an initial sync of My List and the Kodi library"""
        # pylint: disable=unused-argument
        do_it = ui.ask_for_confirmation(common.get_local_string(30122),
                                        common.get_local_string(30123))
        if not do_it or not g.ADDON.getSettingBool('mylist_library_sync'):
            return
        common.debug('Performing full sync from My List to Kodi library')
        library.purge()
        nfo_settings = nfo.NFOSettings()
        nfo_settings.show_export_dialog()
        for videoid in api.video_list(
                api.list_id_for_type('queue')).videoids:
            library.execute_library_tasks(videoid, [library.export_item],
                                          common.get_local_string(30018),
                                          sync_mylist=False,
                                          nfo_settings=nfo_settings)

    def purge(self, pathitems):
        """Delete all previously exported items from the Kodi library"""
        # pylint: disable=unused-argument
        if ui.ask_for_confirmation(common.get_local_string(30125),
                                   common.get_local_string(30126)):
            library.purge()

    def migrate(self, pathitems):
        """Migrate exported items from old library format to the new format"""
        for videoid in library.get_previously_exported_items():
            library.execute_library_tasks(videoid, [library.export_item],
                                          common.get_local_string(30018),
                                          sync_mylist=False)

    def export_all_new_episodes(self, pathitems):
        library.export_all_new_episodes()

    @common.inject_video_id(path_offset=1)
    def export_new_episodes(self, videoid):
        library.export_new_episodes(videoid)

    @common.inject_video_id(path_offset=1)
    def exclude_from_auto_update(self, videoid):
        library.exclude_show_from_auto_update(videoid, True)
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    def include_in_auto_update(self, videoid):
        library.exclude_show_from_auto_update(videoid, False)
        common.refresh_container()

    def mysql_test(self, pathitems):
        """Perform a MySQL database connection test"""
        # Todo: when menu action is called, py restart addon and global attempts
        #  to initialize the database and then the test is also performed
        #  in addition, you must also wait for the timeout to obtain any connection error
        #  Perhaps creating a particular modal dialog with connection parameters can help
        pass

    def set_autoupdate_device(self, pathitems):
        """Set the current device to manage auto-update of the shared-library (MySQL)"""
        g.SHARED_DB.set_value('auto_update_device_uuid', common.get_device_uuid())
        ui.show_notification(common.get_local_string(30209), time=8000)

    def check_autoupdate_device(self, pathitems):
        """Check if the current device manage the auto-updates of the shared-library (MySQL)"""
        uuid = g.SHARED_DB.get_value('auto_update_device_uuid')
        if uuid is None:
            msg = common.get_local_string(30212)
        else:
            current_device_uuid = common.get_device_uuid()
            msg = common.get_local_string(30210) \
                if current_device_uuid == uuid else common.get_local_string(30211)
        ui.show_notification(msg, time=8000)
