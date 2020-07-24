# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Defines upgrade actions to the frontend and backend, to be performed by upgrade_controller

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os

import xbmc
import xbmcvfs

from resources.lib.common.fileops import delete_folder_contents, list_dir, join_folders_paths, load_file, save_file
from resources.lib.common.logging import debug, error, warn
from resources.lib.globals import g
from resources.lib.kodi import ui
from resources.lib.kodi.library_utils import get_library_subfolders, FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS


def delete_cache_folder():
    # Delete cache folder in the add-on userdata (no more needed with the new cache management)
    cache_path = os.path.join(g.DATA_PATH, 'cache')
    if not os.path.exists(g.py2_decode(xbmc.translatePath(cache_path))):
        return
    debug('Deleting the cache folder from add-on userdata folder')
    try:
        delete_folder_contents(cache_path, True)
        xbmc.sleep(80)
        xbmcvfs.rmdir(cache_path)
    except Exception:  # pylint: disable=broad-except
        import traceback
        error(g.py2_decode(traceback.format_exc(), 'latin-1'))


def migrate_library():
    # Migrate the Kodi library to the new format of STRM path
    # - Old STRM: '/play/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used before ver 1.7.0)
    # - New STRM: '/play_strm/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used from ver 1.7.0)
    folders = get_library_subfolders(FOLDER_NAME_MOVIES) + get_library_subfolders(FOLDER_NAME_SHOWS)
    if not folders:
        return
    debug('Start migrating STRM files')
    try:
        with ui.ProgressDialog(True,
                               title='Migrating library to new format',
                               max_value=len(folders)) as progress_bar:
            for folder_path in folders:
                folder_name = os.path.basename(g.py2_decode(xbmc.translatePath(folder_path)))
                progress_bar.set_message('PLEASE WAIT - Migrating: ' + folder_name)
                _migrate_strm_files(folder_path)
    except Exception as exc:  # pylint: disable=broad-except
        error('Migrating failed: {}', exc)
        import traceback
        error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        ui.show_ok_dialog('Migrating library to new format',
                          ('Library migration has failed.[CR]'
                           'Before try play a Netflix video from library, you must run manually the library migration, '
                           'otherwise you will have add-on malfunctions.[CR][CR]'
                           'Open add-on settings on "Library" section, and select "Import existing library".'))


def _migrate_strm_files(folder_path):
    # Change path in STRM files
    for filename in list_dir(folder_path)[1]:
        if not filename.endswith('.strm'):
            continue
        file_path = join_folders_paths(folder_path, filename)
        file_content = load_file(file_path)
        if not file_content:
            warn('Migrate error: "{}" skipped, STRM file empty or corrupted', file_path)
            continue
        if 'action=play_video' in file_content:
            warn('Migrate error: "{}" skipped, STRM file type of v0.13.x', file_path)
            continue
        file_content = file_content.strip('\t\n\r').replace('/play/', '/play_strm/')
        save_file(file_path, file_content.encode('utf-8'))
