# -*- coding: utf-8 -*-
# Copyright: (c) 2019, Dag Wieers (@dagwieers) <dag@wieers.com>
# GNU General Public License v3.0 (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
''' This file implements the Kodi xbmcvfs module, either using stubs or alternative functionality '''

from __future__ import absolute_import, division, print_function, unicode_literals
import os
import shutil


def File(path, flags='r'):
    ''' A reimplementation of the xbmcvfs File() function '''
    try:
        return open(path, flags)
    except IOError:
        try:  # Python 3
            from io import StringIO
        except ImportError:  # Python 2
            from StringIO import StringIO
        return StringIO('')


def Stat(path):
    ''' A reimplementation of the xbmcvfs Stat() function '''

    class stat:  # pylint: disable=too-few-public-methods
        ''' A reimplementation of the xbmcvfs stat class '''

        def __init__(self, path):
            ''' The constructor xbmcvfs stat class '''
            self._stat = os.stat(path)

        def st_mtime(self):
            ''' The xbmcvfs stat class st_mtime method '''
            return self._stat.st_mtime

    return stat(path)


def copy(source, destination):
    ''' A reimplementation of the xbmcvfs copy() function '''
    return shutil.copyfile(source, destination)


def delete(path):
    ''' A reimplementation of the xbmcvfs delete() function '''

    try:
        os.remove(path)
    except OSError:
        pass


def exists(path):
    ''' A reimplementation of the xbmcvfs exists() function '''
    return os.path.exists(path)


def listdir(path):
    ''' A reimplementation of the xbmcvfs listdir() function '''
    files = []
    dirs = []
    for f in os.listdir(path):
        if os.path.isfile(f):
            files.append(f)
        if os.path.isdir(f):
            dirs.append(f)
    return dirs, files


def mkdir(path):
    ''' A reimplementation of the xbmcvfs mkdir() function '''
    return os.mkdir(path)


def mkdirs(path):
    ''' A reimplementation of the xbmcvfs mkdirs() function '''
    return os.makedirs(path)


def rename(file, newFileName):  # pylint: disable=redefined-builtin
    ''' A reimplementation of the xbmcvfs rename() function '''
    return os.rename(file, newFileName)


def rmdir(path):
    ''' A reimplementation of the xbmcvfs rmdir() function '''
    return os.rmdir(path)
