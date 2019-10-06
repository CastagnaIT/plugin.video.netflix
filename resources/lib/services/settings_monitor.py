# -*- coding: utf-8 -*-
"""Checks when settings are changed"""
from __future__ import absolute_import, division, unicode_literals

import sys

import xbmc

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.database.db_utils import (TABLE_SETTINGS_MONITOR)
from resources.lib.globals import g

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class SettingsMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        if not g.settings_monitor_is_suspended():
            self._on_change()

    def _on_change(self):
        common.debug('SettingsMonitor: settings have been changed, started checks')
        reboot_addon = False
        clean_cache = False

        use_mysql = g.ADDON.getSettingBool('use_mysql')
        use_mysql_old = g.LOCAL_DB.get_value('use_mysql', False, TABLE_SETTINGS_MONITOR)
        use_mysql_turned_on = use_mysql and not use_mysql_old

        common.debug('SettingsMonitor: Reinitialization of global settings')
        g.init_globals(sys.argv, reboot_addon)

        # Check the MySQL connection status after reinitialization of global settings
        use_mysql_after = g.ADDON.getSettingBool('use_mysql')
        if use_mysql_turned_on and use_mysql_after:
            g.LOCAL_DB.set_value('use_mysql', True, TABLE_SETTINGS_MONITOR)
            ui.show_notification(g.ADDON.getLocalizedString(30202))
        if not use_mysql_after and use_mysql_old:
            g.LOCAL_DB.set_value('use_mysql', False, TABLE_SETTINGS_MONITOR)

        # Check if the custom esn is changed
        custom_esn = g.ADDON.getSetting('esn')
        custom_esn_old = g.LOCAL_DB.get_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
        if custom_esn != custom_esn_old:
            g.LOCAL_DB.set_value('custom_esn', custom_esn, TABLE_SETTINGS_MONITOR)
            common.send_signal(signal=common.Signals.ESN_CHANGED, data=g.get_esn())

        # Check menu settings changes
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
                reboot_addon = True

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
                    # We remove the cache to allow get the new results in the chosen order
                    clean_cache = True

        # Check changes on content profiles
        # This is necessary because it is possible that some manifests
        # could be cached using the previous settings (see msl_handler - load_manifest)
        menu_keys = ['enable_dolby_sound', 'enable_vp9_profiles', 'enable_hevc_profiles',
                     'enable_hdr_profiles', 'enable_dolbyvision_profiles', 'enable_force_hdcp',
                     'disable_webvtt_subtitle']
        collect_int = ''
        for menu_key in menu_keys:
            collect_int += unicode(int(g.ADDON.getSettingBool(menu_key)))
        collect_int_old = g.LOCAL_DB.get_value('content_profiles_int', '', TABLE_SETTINGS_MONITOR)
        if collect_int != collect_int_old:
            g.LOCAL_DB.set_value('content_profiles_int', collect_int, TABLE_SETTINGS_MONITOR)
            clean_cache = True

        if clean_cache:
            common.run_plugin('plugin://plugin.video.netflix/action/purge_cache/'
                              '?on_disk=True&no_notification=True')

        if reboot_addon:
            common.debug('SettingsMonitor: addon will be rebooted')
            url = 'plugin://plugin.video.netflix/directory/root'
            xbmc.executebuiltin('XBMC.Container.Update(path,replace)')  # Clean path history
            xbmc.executebuiltin('Container.Update({})'.format(url))  # Open root page
