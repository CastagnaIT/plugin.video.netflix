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

from resources.lib.globals import g
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


def file_exists(filename, data_path=g.DATA_PATH):
    """
    Checks if a given file exists
    :param filename: The filename
    :return: True if exists
    """
    return xbmcvfs.exists(xbmc.translatePath(os.path.join(data_path, filename)))


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


def save_file(filename, content, mode='wb'):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    file_handle = xbmcvfs.File(
        xbmc.translatePath(os.path.join(g.DATA_PATH, filename)), mode)
    try:
        file_handle.write(bytearray(content))
    finally:
        file_handle.close()


def load_file(filename, mode='rb'):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    file_handle = xbmcvfs.File(
        xbmc.translatePath(os.path.join(g.DATA_PATH, filename)), mode)
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
    file_path = xbmc.translatePath(os.path.join(g.DATA_PATH, filename))
    try:
        xbmcvfs.delete(file_path)
    finally:
        pass


def list_dir(path=g.DATA_PATH):
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
        xbmcvfs.delete(os.path.join(path, filename))
    if not delete_subfolders:
        return
    for directory in directories:
        delete_folder_contents(os.path.join(path, directory), True)
        # Give time because the system performs previous op. otherwise it can't delete the folder
        xbmc.sleep(80)
        xbmcvfs.rmdir(os.path.join(path, directory))


def delete_ndb_files(data_path=g.DATA_PATH):
    """Delete all .ndb files in a folder"""
    for filename in list_dir(xbmc.translatePath(data_path))[1]:
        if filename.endswith('.ndb'):
            xbmcvfs.delete(os.path.join(g.DATA_PATH, filename))


def write_strm_file(videoid, file_path):
    """Write a playable URL to a STRM file"""
    filehandle = xbmcvfs.File(xbmc.translatePath(file_path), 'wb')
    try:
        filehandle.write(bytearray(build_url(videoid=videoid,
                                             mode=g.MODE_PLAY).encode('utf-8')))
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
    return g.py2_decode(makeLegalFilename('/'.join(args)))
