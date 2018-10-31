# -*- coding: utf-8 -*-
"""Navigation handler for library actions"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.kodi.library as library


class LibraryActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing LibraryActionExecutor: {}'
                     .format(params))
        self.params = params

    @common.inject_video_id(path_offset=1)
    def export_silent(self, videoid):
        """Export an item to the Kodi library"""
        # pylint: disable=broad-except
        for task in library.compile_tasks(videoid):
            try:
                library.export_item(task, library.library_path())
            except Exception:
                import traceback
                common.error(traceback.format_exc())
                common.error('Export of {} failed'.format(task['title']))

    @common.inject_video_id(path_offset=1)
    def export(self, videoid):
        """Export an item to the Kodi library"""
        _execute_library_tasks(videoid, library.export_item,
                               common.get_local_string(650))

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        _execute_library_tasks(videoid, library.remove_item,
                               common.get_local_string(650))

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        _execute_library_tasks(videoid, library.update_item,
                               common.get_local_string(650))


def _execute_library_tasks(videoid, task_handler, title):
    """Execute library tasks for videoid and show errors in foreground"""
    common.execute_tasks(title=title,
                         tasks=library.compile_tasks(videoid),
                         task_handler=task_handler,
                         notify_errors=True,
                         library_home=library.library_path())
