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

        g.init_globals(sys.argv)

        ps_changed = False
        show_menu_changed = False
        sort_order_type_changed = False

        for menu_id, menu_data in g.MAIN_MENU_ITEMS.iteritems():
            # Check settings changes in show menu
            show_menu_new_setting = bool(g.ADDON.getSettingBool('_'.join(('show_menu', menu_id))))
            show_menu_old_setting = g.PERSISTENT_STORAGE['show_menus'].get(menu_id, True)
            if show_menu_new_setting != show_menu_old_setting:
                g.PERSISTENT_STORAGE['show_menus'][menu_id] = show_menu_new_setting
                show_menu_changed = True
                ps_changed = True
            # Check settings changes in sort order of menu
            if menu_data.get('request_context_name'):
                menu_sortorder_new_setting = int(
                    g.ADDON.getSettingInt('_'.join(('menu_sortorder', menu_data['path'][1]))))
                menu_sortorder_old_setting = g.PERSISTENT_STORAGE['menu_sortorder'].get(menu_id, 0)
                if menu_sortorder_new_setting != menu_sortorder_old_setting:
                    g.PERSISTENT_STORAGE['menu_sortorder'][menu_id] = menu_sortorder_new_setting
                    sort_order_type_changed = True
                    ps_changed = True

        if ps_changed:
            g.PERSISTENT_STORAGE.commit()

        if sort_order_type_changed:
            # We remove the cache to allow get the new results in the chosen order
            common.run_plugin('plugin://plugin.video.netflix/action/purge_cache/?on_disk=True&no_notification=True')

        if show_menu_changed:
            url = 'plugin://plugin.video.netflix/directory/root'
            xbmc.executebuiltin('Container.Update({},replace)'.format(url))
