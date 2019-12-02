# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    This file implements the Kodi xbmcaddon module, either using stubs or alternative functionality

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import json
from xbmcextra import addon_settings, global_settings, import_language, read_addon_xml

GLOBAL_SETTINGS = global_settings()
ADDON_SETTINGS = addon_settings()
ADDON_INFO = read_addon_xml('addon.xml')
ADDON_ID = list(ADDON_INFO)[0]
PO = import_language(language=GLOBAL_SETTINGS.get('locale.language'))


class Addon:
    """A reimplementation of the xbmcaddon Addon class"""

    def __init__(self, id=ADDON_ID):  # pylint: disable=redefined-builtin
        """A stub constructor for the xbmcaddon Addon class"""
        self.id = id

    def getAddonInfo(self, key):
        """A working implementation for the xbmcaddon Addon class getAddonInfo() method"""
        STUB_INFO = dict(id=self.id, name=self.id, version='2.3.4', type='kodi.inputstream', profile='special://userdata')
        return ADDON_INFO.get(self.id, STUB_INFO).get(key)

    @staticmethod
    def getLocalizedString(msgctxt):
        """A working implementation for the xbmcaddon Addon class getLocalizedString() method"""
        for entry in PO:
            if entry.msgctxt == '#%s' % msgctxt:
                return entry.msgstr or entry.msgid
        return 'vrttest'

    def getSetting(self, key):
        """A working implementation for the xbmcaddon Addon class getSetting() method"""
        return ADDON_SETTINGS.get(self.id, ADDON_SETTINGS).get(key, '')

    def getSettingBool(self, key):
        """A working implementation for the xbmcaddon Addon class getSettingBool() method"""
        return bool(self.getSetting(key) or True)

    def getSettingInt(self, key):
        """A working implementation for the xbmcaddon Addon class getSettingInt() method"""
        return int(self.getSetting(key) or 0)

    def getSettingString(self, key):
        """A working implementation for the xbmcaddon Addon class getSettingString() method"""
        return str(self.getSetting(key) or '')

    @staticmethod
    def openSettings():
        """A stub implementation for the xbmcaddon Addon class openSettings() method"""

    def setSetting(self, key, value):
        """A stub implementation for the xbmcaddon Addon class setSetting() method"""
        if self.id in ADDON_SETTINGS:
            ADDON_SETTINGS[self.id][key] = value
        else:
            ADDON_SETTINGS[key] = value
        with open('test/userdata/addon_settings.json', 'w') as fd:
            json.dump(ADDON_SETTINGS, fd, sort_keys=True, indent=4)

    def setSettingBool(self, key, value):
        """A stub implementation for the xbmcaddon Addon class setSettingBool() method"""
        self.setSetting(key, bool(value))

    def setSettingInt(self, key, value):
        """A stub implementation for the xbmcaddon Addon class setSettingInt() method"""
        self.setSetting(key, int(value))
