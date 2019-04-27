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
        if not g.SETTINGS_MONITOR_IGNORE:
            self._on_change()

    def _on_change(self):
        common.debug('SettingsMonitor: Settings changed, reinitialize global settings')
        req_sort_order_type_oldvalue = g.REQ_SORT_ORDER_TYPE

        g.init_globals(sys.argv)

        if g.REQ_SORT_ORDER_TYPE != req_sort_order_type_oldvalue:
            # We remove the cache to allow get the new results in the chosen order
            common.run_plugin('plugin://plugin.video.netflix/action/purge_cache/?on_disk=True&no_notification=True')

        ps_changed = False
        for menu_id, data in g.MAIN_MENU_ITEMS.iteritems():
            new_setting = bool(g.ADDON.getSettingBool('_'.join(('show_menu', menu_id))))
            old_setting = g.PERSISTENT_STORAGE['show_menus'].get(menu_id, True)

            if new_setting != old_setting:
                g.PERSISTENT_STORAGE['show_menus'][menu_id] = new_setting
                ps_changed = True
        if ps_changed:
            g.PERSISTENT_STORAGE.commit()
            url = 'plugin://plugin.video.netflix/directory/root'
            xbmc.executebuiltin('Container.Update({},replace)'.format(url))
