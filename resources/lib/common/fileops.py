# -*- coding: utf-8 -*-
"""Helper functions for file operations"""
from __future__ import unicode_literals

import os

from .globals import DATA_PATH


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


def file_exists(filename, data_path=DATA_PATH):
    """
    Checks if a given file exists
    :param filename: The filename
    :return: True if so
    """
    return os.path.exists(data_path + filename)


def save_file(filename, content, data_path=DATA_PATH, mode='w'):
    """
    Saves the given content under given filename
    :param filename: The filename
    :param content: The content of the file
    """
    with open(data_path + filename, mode) as file_handle:
        file_handle.write(content.encode('utf-8'))


def load_file(filename, data_path=DATA_PATH, mode='r'):
    """
    Loads the content of a given filename
    :param filename: The file to load
    :return: The content of the file
    """
    with open(data_path + filename, mode) as file_handle:
        return file_handle.read()


def list_dir(data_path=DATA_PATH):
    """
    List the contents of a folder
    :return: The contents of the folder
    """
    return os.listdir(data_path)
