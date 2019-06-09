# -*- coding: utf-8 -*-
"""Navigation handler for library actions"""
from __future__ import unicode_literals


from resources.lib. globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui
import resources.lib.kodi.library as library


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
        library.execute_library_tasks(videoid, library.export_item,
                                      common.get_local_string(30018),
                                      export_nfo=self._export_nfo(videoid.mediatype))

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        if ui.ask_for_removal_confirmation():
            library.execute_library_tasks(videoid, library.remove_item,
                                          common.get_local_string(30030))
            common.refresh_container()

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        library.execute_library_tasks(videoid, library.update_item,
                                      common.get_local_string(30061),
                                      export_nfo=self._export_nfo(videoid.mediatype))
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    def export_silent(self, videoid):
        """Silently export an item to the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to.
        Will only ask for NFO export"""
        # pylint: disable=broad-except
        library.execute_library_tasks_silently(
            videoid, library.export_item,
            self.params.get('sync_mylist', False),
            export_nfo=self._export_nfo(videoid.mediatype,
                                        common.get_local_string(30293)))

    @common.inject_video_id(path_offset=1)
    def remove_silent(self, videoid):
        """Silently remove an item from the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        library.execute_library_tasks_silently(
            videoid, library.remove_item,
            self.params.get('sync_mylist', False))

    # Not used for now
    #@common.inject_video_id(path_offset=1)
    #def update_silent(self, videoid):
    #    """Silently update an item in the Kodi library
    #    (without GUI feedback). This will ignore the setting for syncing my
    #    list and Kodi library and do no sync, if not explicitly asked to."""
    #    library.execute_library_tasks_silently(
    #        videoid, library.update_item,
    #        self.params.get('sync_mylist', False))

    def initial_mylist_sync(self, pathitems):
        """Perform an initial sync of My List and the Kodi library"""
        # pylint: disable=unused-argument
        do_it = ui.ask_for_confirmation(common.get_local_string(30122),
                                        common.get_local_string(30123))
        if not do_it or not g.ADDON.getSettingBool('mylist_library_sync'):
            return

        common.debug('Performing full sync from My List to Kodi library')
        library.purge()
        for videoid in api.video_list( # What list is used there?
                api.list_id_for_type('queue')).videoids:
            library.execute_library_tasks(videoid, library.export_item,
                                          common.get_local_string(30018),
                                          sync_mylist=False,
                                          export_nfo=self._export_nfo())

    def purge(self, pathitems):
        """Delete all previously exported items from the Kodi library"""
        # pylint: disable=unused-argument
        if ui.ask_for_confirmation(common.get_local_string(30125),
                                   common.get_local_string(30126)):
            library.purge()

    def migrate(self, pathitems):
        """Migrate exported items from old library format to the new format"""
        for videoid in library.get_previously_exported_items():
            library.execute_library_tasks(videoid, library.export_item,
                                          common.get_local_string(30018),
                                          sync_mylist=False)

    def _export_nfo(self, mediatype=None, title=common.get_local_string(30282)):
        if g.ADDON.getSettingBool('enable_nfo_export'):
            # Default case, we want NFO, unless we ask.
            # If set to 'Never', it will be reset to false in the task compilation anyway
            # to allow asking only once in case of massive export (i.e. first library sync)
            export_nfo = True
            if ((mediatype == common.VideoId.MOVIE and g.ADDON.getSettingInt('export_movie_nfo') == 2) or
                (mediatype in common.VideoId.TV_TYPES and g.ADDON.getSettingInt('export_tv_nfo') == 2)):
                export_nfo = ui.ask_for_confirmation(title, common.get_local_string(30283))
            elif mediatype == None: # Massive export
                typelist = []
                if g.ADDON.getSettingInt('export_movie_nfo') == 2:
                    typelist.append(common.get_local_string(30291))
                if g.ADDON.getSettingInt('export_tv_nfo') == 2:
                    typelist.append(common.get_local_string(30292))
                if typelist is not None:
                    message = ' {} '.format(common.get_local_string(1397)).join(typelist)
                    message = common.get_local_string(30289).format(message)
                    export_nfo = ui.ask_for_confirmation(title, message)
                else:
                    export_nfo = False
        else:
            export_nfo = False
        return export_nfo
