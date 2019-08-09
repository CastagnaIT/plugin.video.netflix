# -*- coding: utf-8 -*-
"""Checks when settings are changed"""

from __future__ import unicode_literals

import xbmc
import sys

from resources.lib.database.db_utils import (TABLE_SETTINGS_MONITOR, TABLE_SESSION)
from resources.lib.globals import g
import resources.lib.common as common


class SettingsMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        if not g.settings_monitor_is_suspended():
            self._on_change()

    def _on_change(self):
        common.debug('SettingsMonitor: Settings changed, reinitialize global settings')

        g.init_globals(sys.argv)

        custom_esn = g.ADDON.getSetting('esn')
        stored_esn = g.LOCAL_DB.get_value('esn', table=TABLE_SESSION)
        if custom_esn:
            # Use a custom esn
            if custom_esn != stored_esn:
                g.LOCAL_DB.set_value('esn', custom_esn, table=TABLE_SESSION)
                common.send_signal(signal=common.Signals.ESN_CHANGED, data=custom_esn)
        else:
            esn_generated = g.LOCAL_DB.get_value('esn_generated', table=TABLE_SESSION)
            if stored_esn != esn_generated:
                # Custom esn erased, use the generated one
                esn_generated = g.LOCAL_DB.get_value('esn_generated', table=TABLE_SESSION)
                g.LOCAL_DB.set_value('esn', esn_generated, table=TABLE_SESSION)
                common.send_signal(signal=common.Signals.ESN_CHANGED, data=esn_generated)

        show_menu_changed = False
        sort_order_type_changed = False

        for menu_id, menu_data in g.MAIN_MENU_ITEMS.iteritems():
            # Check settings changes in show menu
            show_menu_new_setting = bool(g.ADDON.getSettingBool('_'.join(('show_menu', menu_id))))
            show_menu_old_setting = g.LOCAL_DB.get_value('menu_{}_show'.format(menu_id),
                                                         True,
                                                         TABLE_SETTINGS_MONITOR)
            if show_menu_new_setting != show_menu_old_setting:
                g.LOCAL_DB.set_value('menu_{}_show'.format(menu_id),
                                     show_menu_new_setting,
                                     TABLE_SETTINGS_MONITOR)
                show_menu_changed = True

            # Check settings changes in sort order of menu
            if menu_data.get('request_context_name'):
                menu_sortorder_new_setting = int(
                    g.ADDON.getSettingInt('_'.join(('menu_sortorder', menu_data['path'][1]))))
                menu_sortorder_old_setting = g.LOCAL_DB.get_value('menu_{}_sortorder'.format(menu_id),
                                                                  0,
                                                                  TABLE_SETTINGS_MONITOR)
                if menu_sortorder_new_setting != menu_sortorder_old_setting:
                    g.LOCAL_DB.set_value('menu_{}_sortorder'.format(menu_id),
                                         menu_sortorder_new_setting,
                                         TABLE_SETTINGS_MONITOR)
                    sort_order_type_changed = True

        if sort_order_type_changed:
            # We remove the cache to allow get the new results in the chosen order
            common.run_plugin('plugin://plugin.video.netflix/action/purge_cache/?on_disk=True&no_notification=True')

        if show_menu_changed:
            url = 'plugin://plugin.video.netflix/directory/root'
            xbmc.executebuiltin('Container.Update({},replace)'.format(url))
