# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Kodi library integration: jobs for a task

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os
import re

import xbmc
import xbmcvfs

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common.exceptions import MetadataNotAvailable, ItemNotFound
from resources.lib.globals import G
from resources.lib.kodi.library_utils import remove_videoid_from_db, insert_videoid_to_db
from resources.lib.utils.logging import LOG


class LibraryJobs:
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
        LOG.debug('Exported {}: {}', job_data['videoid'], job_data['title'])

    def export_new_item(self, job_data, library_home):
        """Used to export new episodes, but it is same operation of task_export_item"""
        # We need to differentiate this task handler from task_export_item
        # in order to manage the compilation of data separately
        self.export_item(job_data, library_home)

    def remove_item(self, job_data, library_home=None):  # pylint: disable=unused-argument
        """Remove an item from the Kodi library, delete it from disk, remove add-on database references"""
        videoid = job_data['videoid']
        LOG.debug('Removing {} ({}) from add-on library', videoid, job_data['title'])
        try:
            # Remove the STRM file exported
            exported_file_path = xbmcvfs.translatePath(job_data['file_path'])
            common.delete_file_safe(exported_file_path)

            parent_folder = xbmcvfs.translatePath(os.path.dirname(exported_file_path))

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
        except ItemNotFound:
            LOG.warn('The videoid {} not exists in the add-on library database', videoid)
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            LOG.error(traceback.format_exc())
            ui.show_addon_error_info(exc)

    # -------------------------- The follow functions not concern jobs for tasks

    def import_videoid_from_existing_strm(self, folder_path, folder_name):
        """
        Get a VideoId from an existing STRM file that was exported
        """
        for filename in common.list_dir(folder_path)[1]:
            if not filename.endswith('.strm'):
                continue
            file_path = common.join_folders_paths(folder_path, filename)
            # Only get a VideoId from the first file in each folder.
            # For tv shows all episodes will result in the same VideoId, the movies only contain one file.
            file_content = common.load_file(file_path)
            if not file_content:
                LOG.warn('Import error: folder "{}" skipped, STRM file empty or corrupted', folder_name)
                return None
            if 'action=play_video' in file_content:
                LOG.debug('Trying to import (v0.13.x): {}', file_path)
                return self._import_videoid_old(file_content, folder_name)
            LOG.debug('Trying to import: {}', file_path)
            return self._import_videoid(file_content, folder_name)

    def _import_videoid_old(self, file_content, folder_name):
        try:
            # The STRM file in add-on v13.x is different and can contains two lines, example:
            #   #EXTINF:-1,Tv show title - "meta data ..."
            #   plugin://plugin.video.netflix/?video_id=12345678&action=play_video
            # Get last line and extract the videoid value
            match = re.search(r'video_id=(\d+)', file_content.split('\n')[-1])
            # Create a videoid of UNSPECIFIED type (we do not know the real type of videoid)
            videoid = common.VideoId(videoid=match.groups()[0])
            # Try to get the videoid metadata:
            # - To know if the videoid still exists on netflix
            # - To get the videoid type
            # - To get the Tv show videoid, in the case of STRM of an episode
            metadata = self.ext_func_get_metadata(videoid)[0]  # pylint: disable=not-callable
            # Generate the a good videoid
            if metadata['type'] == 'show':
                return common.VideoId(tvshowid=metadata['id'])
            return common.VideoId(movieid=metadata['id'])
        except MetadataNotAvailable:
            LOG.warn('Import error: folder {} skipped, metadata not available', folder_name)
            return None
        except (AttributeError, IndexError):
            LOG.warn('Import error: folder {} skipped, STRM not conform to v0.13.x format', folder_name)
            return None

    def _import_videoid(self, file_content, folder_name):
        file_content = file_content.strip('\t\n\r')
        if G.BASE_URL not in file_content:
            LOG.warn('Import error: folder "{}" skipped, unrecognized plugin name in STRM file', folder_name)
            raise ImportWarning
        file_content = file_content.replace(G.BASE_URL, '')
        # file_content should result as, example:
        # - Old STRM path: '/play/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used before ver 1.7.0)
        # - New STRM path: '/play_strm/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used from ver 1.7.0)
        pathitems = file_content.strip('/').split('/')
        if G.MODE_PLAY not in pathitems and G.MODE_PLAY_STRM not in pathitems:
            LOG.warn('Import error: folder "{}" skipped, unsupported play path in STRM file', folder_name)
            raise ImportWarning
        pathitems = pathitems[1:]
        try:
            if pathitems[0] == common.VideoId.SHOW:
                # Get always VideoId of tvshow type (not season or episode)
                videoid = common.VideoId.from_path(pathitems[:2])
            else:
                videoid = common.VideoId.from_path(pathitems)
            # Try to get the videoid metadata, to know if the videoid still exists on netflix
            self.ext_func_get_metadata(videoid)  # pylint: disable=not-callable
            return videoid
        except MetadataNotAvailable:
            LOG.warn('Import error: folder {} skipped, metadata not available for videoid {}',
                     folder_name, pathitems[1])
            return None
