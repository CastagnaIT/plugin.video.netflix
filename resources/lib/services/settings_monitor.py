# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo (original implementation module)
    Checks when settings are changed

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
import sys
from future.utils import iteritems

import xbmc

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common.cache_utils import CACHE_COMMON, CACHE_MYLIST, CACHE_SEARCH, CACHE_MANIFESTS
from resources.lib.database.db_utils import TABLE_SETTINGS_MONITOR, TABLE_SESSION
from resources.lib.globals import G
from resources.lib.utils.esn import generate_android_esn, ForceWidevine
from resources.lib.utils.logging import LOG

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class SettingsMonitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self)

    def onSettingsChanged(self):
        status = G.settings_monitor_suspend_status()
        if status == 'First':
            LOG.warn('SettingsMonitor: triggered but in suspend status (at first change)')
            G.settings_monitor_suspend(False)
            return
        if status == 'True':
            LOG.warn('SettingsMonitor: triggered but in suspend status (permanent)')
            return
        self._on_change()

    def _on_change(self):
        LOG.debug('SettingsMonitor: settings have been changed, started checks')
        reboot_addon = False
        clean_cache = False

        use_mysql = G.ADDON.getSettingBool('use_mysql')
        use_mysql_old = G.LOCAL_DB.get_value('use_mysql', False, TABLE_SETTINGS_MONITOR)
        use_mysql_turned_on = use_mysql and not use_mysql_old

        LOG.debug('SettingsMonitor: Reloading global settings')
        G.init_globals(sys.argv, reinitialize_database=use_mysql != use_mysql_old, reload_settings=True)

        # Check the MySQL connection status after reinitialization of service global settings
        use_mysql_after = G.ADDON.getSettingBool('use_mysql')
        if use_mysql_turned_on and use_mysql_after:
            G.LOCAL_DB.set_value('use_mysql', True, TABLE_SETTINGS_MONITOR)
            ui.show_notification(G.ADDON.getLocalizedString(30202))
        if not use_mysql_after and use_mysql_old:
            G.LOCAL_DB.set_value('use_mysql', False, TABLE_SETTINGS_MONITOR)

        _check_esn()

        # Check menu settings changes
        for menu_id, menu_data in iteritems(G.MAIN_MENU_ITEMS):
            # Check settings changes in show/hide menu
            if menu_data.get('has_show_setting', True):
                show_menu_new_setting = bool(G.ADDON.getSettingBool('_'.join(('show_menu', menu_id))))
                show_menu_old_setting = G.LOCAL_DB.get_value('menu_{}_show'.format(menu_id),
                                                             True,
                                                             TABLE_SETTINGS_MONITOR)
                if show_menu_new_setting != show_menu_old_setting:
                    G.LOCAL_DB.set_value('menu_{}_show'.format(menu_id),
                                         show_menu_new_setting,
                                         TABLE_SETTINGS_MONITOR)
                    reboot_addon = True

            # Check settings changes in sort order of menu
            if menu_data.get('has_sort_setting'):
                menu_sortorder_new_setting = int(G.ADDON.getSettingInt('menu_sortorder_' + menu_data['path'][1]))
                menu_sortorder_old_setting = G.LOCAL_DB.get_value('menu_{}_sortorder'.format(menu_id),
                                                                  0,
                                                                  TABLE_SETTINGS_MONITOR)
                if menu_sortorder_new_setting != menu_sortorder_old_setting:
                    G.LOCAL_DB.set_value('menu_{}_sortorder'.format(menu_id),
                                         menu_sortorder_new_setting,
                                         TABLE_SETTINGS_MONITOR)
                    clean_cache = True

        # Checks for settings changes that require cache invalidation
        if not clean_cache:
            page_results = G.ADDON.getSettingInt('page_results')
            page_results_old = G.LOCAL_DB.get_value('page_results', 90, TABLE_SETTINGS_MONITOR)
            if page_results != page_results_old:
                G.LOCAL_DB.set_value('page_results', page_results, TABLE_SETTINGS_MONITOR)
                clean_cache = True

        _check_msl_profiles()
        _check_watched_status_sync()

        if clean_cache:
            # We remove the cache to allow get the new results with the new settings
            G.CACHE.clear([CACHE_COMMON, CACHE_MYLIST, CACHE_SEARCH])

        # Avoid perform these operations when the add-on is installed from scratch and there are no credentials
        if reboot_addon and not common.check_credentials():
            reboot_addon = False

        if reboot_addon:
            LOG.debug('SettingsMonitor: addon will be rebooted')
            # Open root page
            common.container_update(common.build_url(['root'], mode=G.MODE_DIRECTORY))


def _check_esn():
    """Check if the custom esn is changed"""
    custom_esn = G.ADDON.getSetting('esn')
    custom_esn_old = G.LOCAL_DB.get_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
    if custom_esn != custom_esn_old:
        G.LOCAL_DB.set_value('custom_esn', custom_esn, TABLE_SETTINGS_MONITOR)
        common.send_signal(signal=common.Signals.ESN_CHANGED)

    if not custom_esn:
        # Check if "Force identification as L3 Widevine device" is changed (ANDROID ONLY)
        force_widevine = G.ADDON.getSettingString('force_widevine')
        force_widevine_old = G.LOCAL_DB.get_value('force_widevine', ForceWidevine.DISABLED, TABLE_SETTINGS_MONITOR)
        if force_widevine != force_widevine_old:
            G.LOCAL_DB.set_value('force_widevine', force_widevine, TABLE_SETTINGS_MONITOR)
            # If user has changed setting is needed clear previous ESN and perform a new handshake with the new one
            G.LOCAL_DB.set_value('esn', generate_android_esn() or '', TABLE_SESSION)
            common.send_signal(signal=common.Signals.ESN_CHANGED)


def _check_msl_profiles():
    """Check for changes on content profiles settings"""
    # This is necessary because it is possible that some manifests
    # could be cached using the previous settings (see load_manifest on msl_handler.py)
    menu_keys = ['enable_dolby_sound', 'enable_vp9_profiles', 'enable_hevc_profiles',
                 'enable_hdr_profiles', 'enable_dolbyvision_profiles', 'enable_force_hdcp',
                 'disable_webvtt_subtitle']
    collect_int = ''
    for menu_key in menu_keys:
        collect_int += unicode(int(G.ADDON.getSettingBool(menu_key)))
    collect_int_old = G.LOCAL_DB.get_value('content_profiles_int', '', TABLE_SETTINGS_MONITOR)
    if collect_int != collect_int_old:
        G.LOCAL_DB.set_value('content_profiles_int', collect_int, TABLE_SETTINGS_MONITOR)
        G.CACHE.clear([CACHE_MANIFESTS])


def _check_watched_status_sync():
    """Check if NF watched status sync setting is changed"""
    progress_manager_enabled = G.ADDON.getSettingBool('ProgressManager_enabled')
    progress_manager_enabled_old = G.LOCAL_DB.get_value('progress_manager_enabled', False, TABLE_SETTINGS_MONITOR)
    if progress_manager_enabled != progress_manager_enabled_old:
        G.LOCAL_DB.set_value('progress_manager_enabled', progress_manager_enabled, TABLE_SETTINGS_MONITOR)
        common.send_signal(signal=common.Signals.SWITCH_EVENTS_HANDLER, data=progress_manager_enabled)
