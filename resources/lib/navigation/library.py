# -*- coding: utf-8 -*-
"""Navigation handler for library actions"""
from __future__ import unicode_literals

import xbmc

from resources.lib. globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
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
        _execute_library_tasks(videoid, library.export_item,
                               common.get_local_string(30018))

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        _execute_library_tasks(videoid, library.remove_item,
                               common.get_local_string(30030))

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        _execute_library_tasks(videoid, library.update_item,
                               common.get_local_string(30061))

    @common.inject_video_id(path_offset=1)
    def export_silent(self, videoid):
        """Silently export an item to the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        # pylint: disable=broad-except
        _execute_library_tasks_silently(
            videoid, library.export_item,
            self.params.get('sync_mylist', False))

    @common.inject_video_id(path_offset=1)
    def remove_silent(self, videoid):
        """Silently remove an item from the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        _execute_library_tasks_silently(
            videoid, library.remove_item,
            self.params.get('sync_mylist', False))

    @common.inject_video_id(path_offset=1)
    def update_silent(self, videoid):
        """Silently update an item in the Kodi library
        (without GUI feedback). This will ignore the setting for syncing my
        list and Kodi library and do no sync, if not explicitly asked to."""
        _execute_library_tasks_silently(
            videoid, library.update_item,
            self.params.get('sync_mylist', False))


def _execute_library_tasks(videoid, task_handler, title):
    """Execute library tasks for videoid and show errors in foreground"""
    common.execute_tasks(title=title,
                         tasks=library.compile_tasks(videoid),
                         task_handler=task_handler,
                         notify_errors=True,
                         library_home=library.library_path())
    _sync_mylist(videoid, task_handler)
    xbmc.executebuiltin('UpdateLibrary(video)')


def _execute_library_tasks_silently(videoid, task_handler, sync_mylist):
    """Execute library tasks for videoid and don't show any GUI feedback"""
    # pylint: disable=broad-except
    for task in library.compile_tasks(videoid):
        try:
            task_handler(task, library.library_path())
        except Exception:
            import traceback
            common.error(traceback.format_exc())
            common.error('{} of {} failed'
                         .format(task_handler.__name__, task['title']))
    xbmc.executebuiltin('UpdateLibrary(video)')
    if sync_mylist:
        _sync_mylist(videoid, task_handler)


def _sync_mylist(videoid, task_handler):
    """Add or remove exported items to My List, if enabled in settings"""
    operation = {
        'export_item': 'add',
        'remove_item': 'remove'}.get(task_handler.__name__)
    if operation and g.ADDON.getSettingBool('mylist_library_sync'):
        common.debug('Syncing my list due to change of Kodi library')
        api.update_my_list(videoid, operation)
