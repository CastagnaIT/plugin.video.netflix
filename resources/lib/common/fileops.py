# -*- coding: utf-8 -*-
"""Helper functions for file operations"""
from __future__ import unicode_literals

import os

import xbmc
import xbmcvfs

from resources.lib.globals import g

from .logging import debug


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
    :return: True if so
    """
    return os.path.exists(data_path + filename)


def save_file(filename, content, mode='w'):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    file_handle = xbmcvfs.File(
        xbmc.translatePath(os.path.join(g.DATA_PATH, filename)), mode)
    try:
        file_handle.write(content.encode('utf-8'))
    finally:
        file_handle.close()


def load_file(filename, mode='r'):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    file_handle = xbmcvfs.File(
        xbmc.translatePath(os.path.join(g.DATA_PATH, filename)), mode)
    try:
        return file_handle.read().decode('utf-8')
    finally:
        file_handle.close()


def delete_file(filename):
    file_path = xbmc.translatePath(os.path.join(g.DATA_PATH, filename))
    try:
        xbmcvfs.delete(file_path)
    finally:
        pass


def list_dir(data_path=g.DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    return xbmcvfs.listdir(xbmc.translatePath(data_path))


def delete_folder_contents(path):
    """Delete all files in a folder"""
    for filename in list_dir(path)[1]:
        xbmcvfs.delete(filename)


def delete_ndb_files(data_path=g.DATA_PATH):
    """Delete all .ndb files in a folder"""
    for filename in list_dir(data_path)[1]:
        if filename.endswith('.ndb'):
            xbmcvfs.delete(os.path.join(g.DATA_PATH, filename))
