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
        req_sort_order_type_oldvalue = g.REQ_SORT_ORDER_TYPE

        g.init_globals(sys.argv)

        if g.REQ_SORT_ORDER_TYPE != req_sort_order_type_oldvalue:
            # We remove the cache to allow get the new results in the chosen order
            common.run_plugin('plugin://plugin.video.netflix/action/purge_cache/?on_disk=True&no_notification=True')
