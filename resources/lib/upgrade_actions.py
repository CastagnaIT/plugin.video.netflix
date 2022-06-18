# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Defines upgrade actions to the frontend and backend, to be performed by upgrade_controller

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os

import xbmc
import xbmcvfs

from resources.lib.common import CmpVersion
from resources.lib.common.fileops import (list_dir, join_folders_paths, load_file, save_file, copy_file, delete_file)
from resources.lib.globals import G, remove_ver_suffix
from resources.lib.kodi import ui
from resources.lib.kodi.library_utils import get_library_subfolders, FOLDER_NAME_MOVIES, FOLDER_NAME_SHOWS
from resources.lib.utils.logging import LOG


def rename_cookie_file():
    # The file "COOKIE_xxxxxx..." will be renamed to "COOKIES"
    list_files = list_dir(G.DATA_PATH)[1]
    for filename in list_files:
        if 'COOKIE_' in filename:
            copy_file(join_folders_paths(G.DATA_PATH, filename),
                      join_folders_paths(G.DATA_PATH, 'COOKIES'))
            xbmc.sleep(80)
            delete_file(filename)


def migrate_library():
    # Migrate the Kodi library to the new format of STRM path
    # - Old STRM: '/play/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used before ver 1.7.0)
    # - New STRM: '/play_strm/show/xxxxxxxx/season/xxxxxxxx/episode/xxxxxxxx/' (used from ver 1.7.0)
    folders = get_library_subfolders(FOLDER_NAME_MOVIES) + get_library_subfolders(FOLDER_NAME_SHOWS)
    if not folders:
        return
    LOG.debug('Start migrating STRM files')
    try:
        with ui.ProgressDialog(True,
                               title='Migrating library to new format',
                               max_value=len(folders)) as progress_bar:
            for folder_path in folders:
                folder_name = os.path.basename(xbmcvfs.translatePath(folder_path))
                progress_bar.set_message(f'PLEASE WAIT - Migrating: {folder_name}')
                _migrate_strm_files(folder_path)
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('Migrating failed: {}', exc)
        import traceback
        LOG.error(traceback.format_exc())
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
            LOG.warn('Migrate error: "{}" skipped, STRM file empty or corrupted', file_path)
            continue
        if 'action=play_video' in file_content:
            LOG.warn('Migrate error: "{}" skipped, STRM file type of v0.13.x', file_path)
            continue
        file_content = file_content.strip('\t\n\r').replace('/play/', '/play_strm/')
        save_file(file_path, file_content.encode('utf-8'))


def migrate_repository():
    if not xbmc.getCondVisibility('System.hasAddon(repository.castagnait)'):
        return
    from xbmcaddon import Addon
    # Sometime kodi append suffix "+matrix" to the version also when the addon version string not include it
    if CmpVersion(remove_ver_suffix(Addon('repository.castagnait').getAddonInfo('version'))) >= '2.0.0':
        return
    LOG.info('Upgrading add-on repository "repository.castagnait" to version 2.0.0')
    repo_folder = G.ADDON_DATA_PATH.replace('plugin.video.netflix', 'repository.castagnait')
    data = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<addon id="repository.castagnait" name="CastagnaIT Repository" version="2.0.0" provider-name="castagnait">\n'
        '<extension point="xbmc.addon.repository" name="CastagnaIT Repository">\n'
        '<dir minversion="18.0.0">\n'
        '<info compressed="false">https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi18/addons.xml</info>\n'
        '<checksum>https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi18/addons.xml.md5</checksum>\n'
        '<datadir zip="true">https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi18</datadir>\n'
        '<hashes>false</hashes>\n'
        '</dir>\n'
        '<dir minversion="19.0.0">\n'
        '<info compressed="false">https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi19/addons.xml</info>\n'
        '<checksum>https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi19/addons.xml.md5</checksum>\n'
        '<datadir zip="true">https://github.com/CastagnaIT/repository.castagnait/raw/kodi/kodi19</datadir>\n'
        '<hashes>false</hashes>\n'
        '</dir>\n'
        '</extension>\n'
        '<extension point="xbmc.addon.metadata">\n'
        '<summary>CastagnaIT Repository</summary>\n'
        '<description>Castagna IT repository</description>\n'
        '<platform>all</platform>\n'
        '<assets>\n'
        '<icon>icon.jpg</icon>\n'
        '</assets>\n'
        '</extension>\n'
        '</addon>\n')
    try:
        save_file(repo_folder + 'addon.xml', data.encode('utf-8'))
        xbmc.executebuiltin('UpdateLocalAddons')
    except Exception:  # pylint: disable=broad-except
        LOG.error('Failed to upgrade add-on repository')
