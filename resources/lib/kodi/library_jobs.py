# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Kodi library integration: jobs for a task

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
import re

import xbmc
import xbmcvfs

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.api.exceptions import MetadataNotAvailable
from resources.lib.globals import g
from resources.lib.kodi.library_utils import (get_library_subfolders, FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS,
                                              remove_videoid_from_db, insert_videoid_to_db)


class LibraryJobs(object):
    """Type of jobs for a task in order to execute library operations"""

    is_abort_requested = False
    """Will be True when Kodi will be closed"""

    # External functions
    ext_func_get_metadata = None
    ext_func_get_mylist_videoids_profile_switch = None
    ext_func_req_profiles_info = None

    monitor = xbmc.Monitor()

    def export_item(self, job_data, library_home):
        """Create strm file for an item and add it to the library"""
        # Paths must be legal to ensure NFS compatibility
        destination_folder = common.join_folders_paths(library_home,
                                                       job_data['root_folder_name'],
                                                       job_data['folder_name'])
        common.create_folder(destination_folder)
        if job_data['create_strm_file']:
            strm_file_path = common.join_folders_paths(destination_folder, job_data['filename'] + '.strm')
            insert_videoid_to_db(job_data['videoid'], strm_file_path, job_data['nfo_data'] is not None)
            common.write_strm_file(job_data['videoid'], strm_file_path)
        if job_data['create_nfo_file']:
            nfo_file_path = common.join_folders_paths(destination_folder, job_data['filename'] + '.nfo')
            common.write_nfo_file(job_data['nfo_data'], nfo_file_path)
        common.debug('Exported {}: {}', job_data['videoid'], job_data['title'])

    def export_new_item(self, job_data, library_home):
        """Used to export new episodes, but it is same operation of task_export_item"""
        # We need to differentiate this task handler from task_export_item
        # in order to manage the compilation of data separately
        self.export_item(job_data, library_home)

    def remove_item(self, job_data, library_home=None):  # pylint: disable=unused-argument
        """Remove an item from the Kodi library, delete it from disk, remove add-on database references"""
        videoid = job_data['videoid']
        common.debug('Removing {} ({}) from add-on library', videoid, job_data['title'])
        try:
            # Remove the STRM file exported
            exported_file_path = g.py2_decode(xbmc.translatePath(job_data['file_path']))
            common.delete_file_safe(exported_file_path)

            parent_folder = g.py2_decode(xbmc.translatePath(os.path.dirname(exported_file_path)))

            # Remove the NFO file of the related STRM file
            nfo_file = os.path.splitext(exported_file_path)[0] + '.nfo'
            common.delete_file_safe(nfo_file)

            dirs, files = common.list_dir(parent_folder)

            # Remove the tvshow NFO file (only when it is the last file in the folder)
            tvshow_nfo_file = common.join_folders_paths(parent_folder, 'tvshow.nfo')

            # (users have the option of removing even single seasons)
            if xbmcvfs.exists(tvshow_nfo_file) and not dirs and len(files) == 1:
                xbmcvfs.delete(tvshow_nfo_file)
                # Delete parent folder
                xbmcvfs.rmdir(parent_folder)

            # Delete parent folder when empty
            if not dirs and not files:
                xbmcvfs.rmdir(parent_folder)

            # Remove videoid records from add-on database
            remove_videoid_from_db(videoid)
        except common.ItemNotFound:
            common.warn('The videoid {} not exists in the add-on library database', videoid)
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            ui.show_addon_error_info(exc)

    # -------------------------- The follow functions not concern jobs for tasks

    def imports_videoids_from_existing_old_library(self):
        """
        Gets a list of VideoId of type movie and show from STRM files that were exported,
        from the old add-on version 13.x
        """
        videoid_pattern = re.compile('video_id=(\\d+)')
        for folder in get_library_subfolders(FOLDER_NAME_MOVIES) + get_library_subfolders(FOLDER_NAME_SHOWS):
            for filename in common.list_dir(folder)[1]:
                file_path = common.join_folders_paths(folder, filename)
                if file_path.endswith('.strm'):
                    common.debug('Trying to migrate {}', file_path)
                    try:
                        # Only get a VideoId from the first file in each folder.
                        # For shows, all episodes will result in the same VideoId
                        # and movies only contain one file
                        yield self._get_root_videoid(file_path, videoid_pattern)
                    except MetadataNotAvailable:
                        common.warn('Metadata not available, item skipped')
                    except (AttributeError, IndexError):
                        common.warn('Item does not conform to old format')
                    break

    def _get_root_videoid(self, filename, pattern):
        match = re.search(pattern,
                          xbmcvfs.File(filename, 'r').read().decode('utf-8').split('\n')[-1])
        # pylint: disable=not-callable
        metadata = self.ext_func_get_metadata(
            common.VideoId(videoid=match.groups()[0])
        )[0]
        if metadata['type'] == 'show':
            return common.VideoId(tvshowid=metadata['id']), metadata.get('title', 'Tv show')
        return common.VideoId(movieid=metadata['id']), metadata.get('title', 'Movie')
