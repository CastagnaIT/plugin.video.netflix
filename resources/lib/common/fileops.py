# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for file operations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import os
import xml.etree.ElementTree as ET

import xbmc
import xbmcvfs

from resources.lib.globals import G
from .misc_utils import build_url

try:  # Kodi >= 19
    from xbmcvfs import makeLegalFilename  # pylint: disable=ungrouped-imports
except ImportError:  # Kodi 18
    from xbmc import makeLegalFilename  # pylint: disable=ungrouped-imports


def check_folder_path(path):
    """
    Check if folder path ends with path delimiter
    If not correct it (makes sure xbmcvfs.exists is working correct)
    """
    end = ''
    if '/' in path and not path.endswith('/'):
        end = '/'
    if '\\' in path and not path.endswith('\\'):
        end = '\\'
    return path + end


def folder_exists(path):
    """
    Checks if a given path exists
    :param path: The path
    :return: True if exists
    """
    return xbmcvfs.exists(check_folder_path(path))


def create_folder(path):
    """
    Create a folder if not exists
    :param path: The path
    """
    if not folder_exists(path):
        xbmcvfs.mkdirs(path)


def file_exists(file_path):
    """
    Checks if a given file exists
    :param file_path: File path to check
    :return: True if exists
    """
    return xbmcvfs.exists(xbmc.translatePath(file_path))


def copy_file(from_path, to_path):
    """
    Copy a file to destination
    :param from_path: File path to copy
    :param to_path: Destination file path
    :return: True if copied
    """
    try:
        return xbmcvfs.copy(xbmc.translatePath(from_path),
                            xbmc.translatePath(to_path))
    finally:
        pass


def save_file_def(filename, content, mode='wb'):
    """
    Saves the given content under given filename, in the default add-on data folder
    :param filename: The filename
    :param content: The content of the file
    :param mode: optional mode options
    """
    save_file(os.path.join(G.DATA_PATH, filename), content, mode)


def save_file(file_path, content, mode='wb'):
    """
    Saves the given content under given filename path
    :param file_path: The filename path
    :param content: The content of the file
    :param mode: optional mode options
    """
    file_handle = xbmcvfs.File(xbmc.translatePath(file_path), mode)
    try:
        file_handle.write(bytearray(content))
    finally:
        file_handle.close()


def load_file_def(filename, mode='rb'):
    """
    Loads the content of a given filename, from the default add-on data folder
    :param filename: The file to load
    :param mode: optional mode options
    :return: The content of the file
    """
    return load_file(os.path.join(G.DATA_PATH, filename), mode)


def load_file(file_path, mode='rb'):
    """
    Loads the content of a given filename
    :param file_path: The file path to load
    :param mode: optional mode options
    :return: The content of the file
    """
    file_handle = xbmcvfs.File(xbmc.translatePath(file_path), mode)
    try:
        return file_handle.readBytes().decode('utf-8')
    finally:
        file_handle.close()


def delete_file_safe(file_path):
    if xbmcvfs.exists(file_path):
        try:
            xbmcvfs.delete(file_path)
        finally:
            pass


def delete_file(filename):
    file_path = xbmc.translatePath(os.path.join(G.DATA_PATH, filename))
    try:
        xbmcvfs.delete(file_path)
    finally:
        pass


def list_dir(path=G.DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder as tuple (directories, files)
    """
    return xbmcvfs.listdir(path)


def delete_folder_contents(path, delete_subfolders=False):
    """
    Delete all files in a folder
    :param path: Path to perform delete contents
    :param delete_subfolders: If True delete also all subfolders
    """
    directories, files = list_dir(xbmc.translatePath(path))
    for filename in files:
        xbmcvfs.delete(os.path.join(path, G.py2_decode(filename)))
    if not delete_subfolders:
        return
    for directory in directories:
        delete_folder_contents(os.path.join(path, G.py2_decode(directory)), True)
        # Give time because the system performs previous op. otherwise it can't delete the folder
        xbmc.sleep(80)
        xbmcvfs.rmdir(os.path.join(path, G.py2_decode(directory)))


def delete_folder(path):
    """Delete a folder with all his contents"""
    delete_folder_contents(path, True)
    # Give time because the system performs previous op. otherwise it can't delete the folder
    xbmc.sleep(80)
    xbmcvfs.rmdir(xbmc.translatePath(path))


def write_strm_file(videoid, file_path):
    """Write a playable URL to a STRM file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(file_path), 'wb')
    try:
        filehandle.write(bytearray(build_url(videoid=videoid,
                                             mode=G.MODE_PLAY_STRM).encode('utf-8')))
    finally:
        filehandle.close()


def write_nfo_file(nfo_data, file_path):
    """Write a NFO file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(file_path), 'wb')
    try:
        filehandle.write(bytearray('<?xml version=\'1.0\' encoding=\'UTF-8\'?>'.encode('utf-8')))
        filehandle.write(bytearray(ET.tostring(nfo_data, encoding='utf-8', method='xml')))
    finally:
        filehandle.close()


def join_folders_paths(*args):
    """Join multiple folder paths in a safe way"""
    # Avoid the use of os.path.join, in some cases with special chars like % break the path
    return G.py2_decode(makeLegalFilename('/'.join(args)))
