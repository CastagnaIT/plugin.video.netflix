# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    This file implements the Kodi xbmcgui module, either using stubs or alternative functionality

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
# pylint: disable=too-many-arguments,unused-argument
from __future__ import absolute_import, division, print_function, unicode_literals
import os
from xbmcextra import kodi_to_ansi

INPUT_ALPHANUM = 0
INPUT_TYPE_NUMBER = 1
ALPHANUM_HIDE_INPUT = 1


def getScreenHeight():
    """A stub implementation of the xbmcgui getScreenHeight() function"""
    return 1080


def getScreenWidth():
    """A stub implementation of the xbmcgui getScreenWidth() function"""
    return 1920


class Control:
    """A reimplementation of the xbmcgui Control class"""

    def __init__(self):
        """A stub constructor for the xbmcgui Control class"""


class ControlLabel:
    """A reimplementation of the xbmcgui ControlLabel class"""

    def __init__(self, x=0, y=0, width=0, height=0, label='', font=None, textColor=None, disabledColor=None, alignment=None, hasPath=False, angle=None):
        """A stub constructor for the xbmcgui ControlLabel class"""


class ControlGeneric(Control):
    """A reimplementation of the xbmcgui Control methods of all control classes"""

    def __init__(self):  # pylint: disable=useless-super-delegation,super-on-old-class
        """A stub constructor for the xbmcgui Control class"""
        super(ControlGeneric, self).__init__()

    @staticmethod
    def getLabel():
        """A stub implementation for the xbmcgui Control Label class getLabel() method"""
        return 'Label'

    @staticmethod
    def setLabel(label='', font=None, textColor=None, disabledColor=None, shadowColor=None, focusedColor=None, label2=''):
        """A stub implementation for the xbmcgui Control Label class getLabel() method"""

    @staticmethod
    def getText():
        """A stub implementation for the xbmcgui Control edit class getLabel() method"""
        return 'Label'

    @staticmethod
    def setText(value=''):
        """A stub implementation for the xbmcgui Control edit class getLabel() method"""

    @staticmethod
    def setType(type=0, heading=''):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui Control edit class getLabel() method"""

    @staticmethod
    def getInt():
        """A stub implementation for the xbmcgui Control slider class getLabel() method"""
        return 0

    @staticmethod
    def setInt(value=0, min=0, delta=1, max=1):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui Control slider class getLabel() method"""

    @staticmethod
    def controlRight(control):
        """A stub implementation for the xbmcgui Control class method"""

    @staticmethod
    def controlLeft(control):
        """A stub implementation for the xbmcgui Control class method"""


class Dialog:
    """A reimplementation of the xbmcgui Dialog class"""

    def __init__(self):
        """A stub constructor for the xbmcgui Dialog class"""

    @staticmethod
    def notification(heading, message, icon=None, time=None, sound=None):
        """A working implementation for the xbmcgui Dialog class notification() method"""
        heading = kodi_to_ansi(heading)
        message = kodi_to_ansi(message)
        print('\033[37;100mNOTIFICATION:\033[35;0m [%s] \033[35;0m%s\033[39;0m' % (heading, message))

    @staticmethod
    # ok(heading, line1, line2=None, line3=None):  # Kodi 18
    def ok(heading, message):
        """A stub implementation for the xbmcgui Dialog class ok() method"""
        heading = kodi_to_ansi(heading)
        message = kodi_to_ansi(message)
        print('\033[37;100mOK:\033[35;0m [%s] \033[35;0m%s\033[39;0m' % (heading, message))

    @staticmethod
    # def yesno(heading, line1, line2=None, line3=None, nolabel=None, yeslabel=None, autoclose=0):  # Kodi 18
    def yesno(heading, message, nolabel=None, yeslabel=None, customlabel=None, autoclose=0):
        """A stub implementation for the xbmcgui Dialog class yesno() method"""
        heading = kodi_to_ansi(heading)
        message = kodi_to_ansi(message)
        print('\033[37;100mYESNO:\033[35;0m [%s] \033[35;0m%s\033[39;0m' % (heading, message))
        return True

    @staticmethod
    def textviewer(heading, text=None, usemono=None):
        """A stub implementation for the xbmcgui Dialog class textviewer() method"""
        heading = kodi_to_ansi(heading)
        text = kodi_to_ansi(text)
        print('\033[37;100mTEXTVIEWER:\033[35;0m [%s]\n\033[35;0m%s\033[39;0m' % (heading, text))

    def input(self, heading, defaultt='', type=0, option=0, autoclose=0):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui Dialog class input() method"""
        print('\033[37;100mINPUT:\033[39;0m [%s]' % (heading))
        if heading == 'E-mail':
            return os.environ.get('NETFLIX_USERNAME')
        if heading == 'Password':
            return os.environ.get('NETFLIX_PASSWORD')
        if heading == 'Search term':
            return 'Family'
        return 'Foobar'

    def select(self, heading, autoclose=None, preselect=None, useDetails=False):
        """A stub implementation for the xbmcgui Dialog class select() method"""
        return -1

    @staticmethod
    # def numeric(type, heading, defaultt=''):  # Kodi 18
    def numeric(type, heading, defaultt='', bHiddenInput=False):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui Dialog class numeric() method"""
        return

    @staticmethod
    def contextmenu(list):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui Dialog class contextmenu() method"""
        return


class DialogProgress:
    """A reimplementation of the xbmcgui DialogProgress"""

    def __init__(self):
        """A stub constructor for the xbmcgui DialogProgress class"""
        self.percent = 0

    @staticmethod
    def close():
        """A stub implementation for the xbmcgui DialogProgress class close() method"""
        print()

    @staticmethod
    # def create(heading, line1=None, line2=None, line3=None):  # Kodi 18
    def create(heading, message=None):
        """A stub implementation for the xbmcgui DialogProgress class create() method"""
        heading = kodi_to_ansi(heading)
        if message:
            message = kodi_to_ansi(message)
            print('\033[37;100mPROGRESS:\033[35;0m [%s] \033[35;0m%s\033[39;0m' % (heading, message))
        else:
            print('\033[37;100mPROGRESS:\033[39;0m [%s]' % heading)

    @staticmethod
    def iscanceled():
        """A stub implementation for the xbmcgui DialogProgress class iscanceled() method"""

    # def update(self, percent, line1=None, line2=None, line3=None):  # Kodi 18
    def update(self, percent, message=None):
        """A stub implementation for the xbmcgui DialogProgress class update() method"""
        if (percent - 5) < self.percent:
            return
        self.percent = percent
        message = kodi_to_ansi(message)
        if message:
            print('\033[37;100mPROGRESS:\033[35;0m [%d%%] \033[35;0m%s\033[39;0m' % (percent, message))
        else:
            print('\033[1G\033[37;100mPROGRESS:\033[35;0m [%d%%]\033[39;0m' % (percent), end='')


class DialogBusy:
    """A reimplementation of the xbmcgui DialogBusy"""

    def __init__(self):
        """A stub constructor for the xbmcgui DialogBusy class"""

    @staticmethod
    def close():
        """A stub implementation for the xbmcgui DialogBusy class close() method"""

    @staticmethod
    def create():
        """A stub implementation for the xbmcgui DialogBusy class create() method"""


class ListItem:
    """A reimplementation of the xbmcgui ListItem class"""

    # def __init__(self, label='', label2='', iconImage='', thumbnailImage='', path='', offscreen=False):  # Kodi 18
    def __init__(self, label='', label2='', path='', offscreen=False):
        """A stub constructor for the xbmcgui ListItem class"""
        self.label = kodi_to_ansi(label)
        self.label2 = kodi_to_ansi(label2)
        self.path = path

    @staticmethod
    def addContextMenuItems(items, replaceItems=False):
        """A stub implementation for the xbmcgui ListItem class addContextMenuItems() method"""
        return

    @staticmethod
    def addStreamInfo(stream_type, stream_values):
        """A stub implementation for the xbmcgui ListItem class addStreamInfo() method"""
        return

    @staticmethod
    def select(selected):
        """A stub implementation for the xbmcgui ListItem class select() method"""
        return

    @staticmethod
    def setLabel(label):
        """A stub implementation for the xbmcgui ListItem class setLabel() method"""

    @staticmethod
    def setArt(key):
        """A stub implementation for the xbmcgui ListItem class setArt() method"""
        return

    @staticmethod
    def setContentLookup(enable):
        """A stub implementation for the xbmcgui ListItem class setContentLookup() method"""
        return

    @staticmethod
    def setInfo(type, infoLabels):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcgui ListItem class setInfo() method"""
        return

    @staticmethod
    def setMimeType(mimetype):
        """A stub implementation for the xbmcgui ListItem class setMimeType() method"""
        return

    @staticmethod
    def getProperty(key):
        """A stub implementation for the xbmcgui ListItem class getProperty() method"""
        return 'test'

    @staticmethod
    def setProperty(key, value):
        """A stub implementation for the xbmcgui ListItem class setProperty() method"""
        return

    @staticmethod
    def setProperties(values):
        """A stub implementation for the xbmcgui ListItem class setProperties() method"""
        return

    @staticmethod
    def setSubtitles(subtitleFiles):
        """A stub implementation for the xbmcgui ListItem class setSubtitles() method"""
        return


class Window:
    """A reimplementation of the xbmcgui Window"""

    def __init__(self, timeout=0):
        """A stub constructor for the xbmcgui Window class"""

    def clearProperty(self, key):
        """A stub implementation for the xbmcgui Window class clearProperty() method"""

    def close(self):
        """A stub implementation for the xbmcgui Window class close() method"""

    def getControl(self, controlId):
        """A stub implementation for the xbmcgui Window class getControl() method"""
        return ControlGeneric()

    def getProperty(self, key):
        """A stub implementation for the xbmcgui Window class getProperty() method"""
        print('xbmcgui getProperty {key}'.format(key=key))
        return ''

    def setProperty(self, key, value):
        """A stub implementation for the xbmcgui Window class setProperty() method"""


class WindowXMLDialog(Window):
    """A reimplementation of the xbmcgui WindowXMLDialog"""
