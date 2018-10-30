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
    def export(self, videoid):
        """Export an item to the Kodi library"""
        common.execute_tasks(title=common.get_local_string(650),
                             tasks=library.compile_tasks(videoid),
                             task_handler=library.export_item,
                             notify_errors=True,
                             library_home=library.library_path())

    @common.inject_video_id(path_offset=1)
    def export_silent(self, videoid):
        """Export an item to the Kodi library"""
        # pylint: disable=bare-except
        for task in library.compile_tasks(videoid):
            try:
                library.export_item(task, library.library_path())
            except:
                import traceback
                common.error(traceback.format_exc())
                common.error('Export of {} failed'.format(task['title']))

    @common.inject_video_id(path_offset=1)
    def remove(self, videoid):
        """Remove an item from the Kodi library"""
        common.execute_tasks(title=common.get_local_string(650),
                             tasks=library.compile_tasks(videoid),
                             task_handler=library.remove_item,
                             notify_errors=True)

    @common.inject_video_id(path_offset=1)
    def update(self, videoid):
        """Update an item in the Kodi library"""
        common.execute_tasks(title=common.get_local_string(650),
                             tasks=library.compile_tasks(videoid),
                             task_handler=library.update_item,
                             notify_errors=True,
                             library_home=library.library_path())
