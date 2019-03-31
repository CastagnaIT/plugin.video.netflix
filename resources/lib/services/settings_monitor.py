# -*- coding: utf-8 -*-
"""Checks when settings are changed"""

from __future__ import unicode_literals

import xbmc
import sys

from resources.lib.globals import g
import resources.lib.common as common

class SettingsMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        self._on_change()

    def _on_change(self):
        common.debug('SettingsMonitor: Settings changed, reinitialize global settings')
        g.init_globals(sys.argv)
