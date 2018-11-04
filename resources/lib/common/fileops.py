# -*- coding: utf-8 -*-
"""Helper functions for file operations"""
from __future__ import unicode_literals

import os

import xbmc

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
    with open(translate_path(os.path.join(g.DATA_PATH, filename)),
              mode) as file_handle:
        file_handle.write(content.encode('utf-8'))


def load_file(filename, mode='r'):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    with open(translate_path(os.path.join(g.DATA_PATH, filename)),
              mode) as file_handle:
        return file_handle.read().decode('utf-8')


def list_dir(data_path=g.DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    return os.listdir(data_path)


def translate_path(path):
    """Translate path if it contains special:// and decode it to unicode"""
    return xbmc.translatePath(path).decode('utf-8')
