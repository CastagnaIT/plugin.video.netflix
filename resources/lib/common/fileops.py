# -*- coding: utf-8 -*-
"""Helper functions for file operations"""
from __future__ import absolute_import, division, unicode_literals

import os

from resources.lib.globals import g


def check_folder_path(path):
    """
    Check if folderpath ends with path delimator
    If not correct it (makes sure xbmcvfs.exists is working correct)
    """
    end = ''
    if '/' in path and not path.endswith('/'):
        end = '/'
    if '\\' in path and not path.endswith('\\'):
        end = '\\'
    return path + end


def file_exists(filename, data_path=g.DATA_PATH):
    """
    Checks if a given file exists
    :param filename: The filename
    :return: True if exists
    """
    from xbmc import translatePath
    from xbmcvfs import exists
    return exists(translatePath(os.path.join(data_path, filename)))


def copy_file(from_path, to_path):
    """
    Copy a file to destination
    :param from_path: File path to copy
    :param to_path: Destination file path
    :return: True if copied
    """
    from xbmc import translatePath
    from xbmcvfs import copy
    try:
        return copy(translatePath(from_path), translatePath(to_path))
    finally:
        pass


def save_file(filename, content, mode='wb'):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    from xbmc import translatePath
    from xbmcvfs import File
    file_handle = File(
        translatePath(os.path.join(g.DATA_PATH, filename)), mode)
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
    from xbmc import translatePath
    from xbmcvfs import File
    file_handle = File(
        translatePath(os.path.join(g.DATA_PATH, filename)), mode)
    try:
        return file_handle.readBytes().decode('utf-8')
    finally:
        file_handle.close()


def delete_file(filename):
    from xbmc import translatePath
    from xbmcvfs import delete
    file_path = translatePath(os.path.join(g.DATA_PATH, filename))
    try:
        delete(file_path)
    finally:
        pass


def list_dir(data_path=g.DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    from xbmc import translatePath
    from xbmcvfs import listdir
    return listdir(translatePath(data_path))


def delete_folder_contents(path, delete_subfolders=False):
    """
    Delete all files in a folder
    :param path: Path to perform delete contents
    :param delete_subfolders: If True delete also all subfolders
    """
    from xbmcvfs import delete
    directories, files = list_dir(path)
    for filename in files:
        delete(os.path.join(path, filename))
    if not delete_subfolders:
        return
    from xbmc import sleep
    from xbmcvfs import rmdir
    for directory in directories:
        delete_folder_contents(os.path.join(path, directory), True)
        # Give time because the system performs previous op. otherwise it can't delete the folder
        sleep(80)
        rmdir(os.path.join(path, directory))


def delete_ndb_files(data_path=g.DATA_PATH):
    """Delete all .ndb files in a folder"""
    from xbmcvfs import delete
    for filename in list_dir(data_path)[1]:
        if filename.endswith('.ndb'):
            delete(os.path.join(g.DATA_PATH, filename))
