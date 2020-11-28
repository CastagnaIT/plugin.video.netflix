# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    This file implements the Kodi xbmc module, either using stubs or alternative functionality

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
# pylint: disable=unused-argument

from __future__ import absolute_import, division, print_function, unicode_literals

import sys
import os
import json
import time
from xbmcextra import global_settings, import_language

ISO_639_1 = 0
ISO_639_2 = 1
ENGLISH_NAME = 2

LOGDEBUG = 'Debug'
LOGINFO = 'Info'
LOGNOTICE = 'Notice'
LOGWARNING = 'Warning'
LOGERROR = 'Error'
LOGSEVERE = 'Severe'
LOGFATAL = 'Fatal'
LOGNONE = 'None'

INFO_LABELS = {
    'System.BuildVersion': '18.2',
    'Container.FolderPath': 'plugin://plugin.video.netflix/',
}

REGIONS = {
    'datelong': '%A, %e %B %Y',
    'dateshort': '%Y-%m-%d',
}

GLOBAL_SETTINGS = global_settings()
PO = import_language(language=GLOBAL_SETTINGS.get('locale.language'))


class Keyboard:
    """A stub implementation of the xbmc Keyboard class"""

    def __init__(self, line='', heading=''):
        """A stub constructor for the xbmc Keyboard class"""

    def doModal(self, autoclose=0):
        """A stub implementation for the xbmc Keyboard class doModal() method"""

    def isConfirmed(self):
        """A stub implementation for the xbmc Keyboard class isConfirmed() method"""
        return True

    def getText(self):
        """A stub implementation for the xbmc Keyboard class getText() method"""
        return 'unittest'


class Monitor:
    """A stub implementation of the xbmc Monitor class"""
    def __init__(self, line='', heading=''):
        """A stub constructor for the xbmc Monitor class"""

    def abortRequested(self):
        """A stub implementation for the xbmc Keyboard class abortRequested() method"""
        return False

    def waitForAbort(self, timeout=0):
        """A stub implementation for the xbmc Keyboard class waitForAbort() method"""
        return


class Player:
    """A stub implementation of the xbmc Player class"""
    def __init__(self):
        self._count = 0

    def pause(self):
        """A stub implementation for the xbmc Player class pause() method"""

    def play(self, item='', listitem=None, windowed=False, startpos=-1):
        """A stub implementation for the xbmc Player class play() method"""

    def isPlaying(self):
        """A stub implementation for the xbmc Player class isPlaying() method"""
        # Return True four times out of five
        self._count += 1
        return bool(self._count % 5 != 0)

    def isPlayingVideo(self):
        """A stub implementation for the xbmc Player class isPlayingVideo() method"""
        # Return True four times out of five
        self._count += 1
        return bool(self._count % 5 != 0)

    def seekTime(self, seekTime):
        """A stub implementation for the xbmc Player class seekTime() method"""

    def showSubtitles(self, bVisible):
        """A stub implementation for the xbmc Player class showSubtitles() method"""
        return

    def setAudioStream(self):
        """A stub implementation for the xbmc Player class setAudioStream() method"""

    def setSubtitleStream(self):
        """A stub implementation for the xbmc Player class setSubtitleStream() method"""


def convertLanguage(language, format):  # pylint: disable=redefined-builtin
    """A reimplementation of the xbmc convertLanguage() function"""
    if format == ISO_639_1:
        return 'en'
    if format == ISO_639_2:
        return 'eng'
    return 'English'


def executebuiltin(string, wait=False):
    """A stub implementation of the xbmc executebuiltin() function"""
    return


def executeJSONRPC(jsonrpccommand):
    """A reimplementation of the xbmc executeJSONRPC() function"""
    command = json.loads(jsonrpccommand)
    if command.get('method') == 'Settings.GetSettingValue':
        key = command.get('params').get('setting')
        return json.dumps(dict(id=1, jsonrpc='2.0', result=dict(value=GLOBAL_SETTINGS.get(key))))
    print("Error in executeJSONRPC, method '{method}' is not implemented".format(**command), file=sys.stderr)
    return json.dumps(dict(error=dict(code=-1, message='Not implemented'), id=1, jsonrpc='2.0'))


def getCondVisibility(string):
    """A reimplementation of the xbmc getCondVisibility() function"""
    if string == 'system.platform.android':
        return False
    return True


def getGlobalIdleTime():
    """A reimplementation of the xbmc getGlobalIdleTime() function"""
    return 0


def getInfoLabel(key):
    """A reimplementation of the xbmc getInfoLabel() function"""
    return INFO_LABELS.get(key)


def getLanguage(format=None, region=None):  # pylint: disable=redefined-builtin
    """A reimplementation of the xbmc getLanguage() function"""
    if format == ISO_639_1:
        return 'en'
    if format == ISO_639_2:
        return 'eng'
    return 'English'


def getLocalizedString(msgctxt):
    """A reimplementation of the xbmc getLocalizedString() function"""
    for entry in PO:
        if entry.msgctxt == '#%s' % msgctxt:
            return entry.msgstr or entry.msgid
    return 'smurf'


def getRegion(key):
    """A reimplementation of the xbmc getRegion() function"""
    return REGIONS.get(key)


def log(msg, level):
    """A reimplementation of the xbmc log() function"""
    print('[32;1m%s: [32;0m%s[0m' % (level, msg))


def makeLegalFilename(filename, fatX=None):  # Kodi 18
    """A reimplementation of the xbmc makeLegalFilename() function"""
    if fatX:
        return filename
    return os.path.basename(filename)


def setContent(self, content):
    """A stub implementation of the xbmc setContent() function"""
    return


def sleep(seconds):
    """A reimplementation of the xbmc sleep() function"""
    time.sleep(seconds)


def translatePath(path):
    """A stub implementation of the xbmc translatePath() function"""
    if path.startswith('special://home'):
        return path.replace('special://home', os.path.join(os.getcwd(), 'test'))
    if path.startswith('special://profile'):
        return path.replace('special://profile', os.path.join(os.getcwd(), 'tests/usedata'))
    if path.startswith('special://userdata'):
        return path.replace('special://userdata', os.path.join(os.getcwd(), 'tests/userdata'))
    return path
