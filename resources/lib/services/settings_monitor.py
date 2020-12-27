# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo (original implementation module)
    Checks when settings are changed

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from contextlib import contextmanager

import xbmc

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common.cache_utils import CACHE_COMMON, CACHE_MYLIST, CACHE_SEARCH, CACHE_MANIFESTS
from resources.lib.database.db_utils import TABLE_SETTINGS_MONITOR
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


class SettingsMonitor(xbmc.Monitor):
    """Checks when settings are changed (all code is executed in the service instance only)"""
    def __init__(self):
        super().__init__()
        self.ignore_n_events = 0

    @contextmanager
    def ignore_events(self, ignore_n_events):
        """Context to set how many onSettingsChanged events to be ignored"""
        self.ignore_n_events += ignore_n_events
        try:
            yield
        except Exception:  # pylint: disable=broad-except
            self.ignore_n_events = 0
            raise

    def onSettingsChanged(self):
        # This method will be called when user change add-on settings or every time ADDON.setSetting...() is called
        if self.ignore_n_events > 0:
            self.ignore_n_events -= 1
            LOG.debug('SettingsMonitor: onSettingsChanged event ignored (remaining {})'.format(self.ignore_n_events))
            return
        try:
            self._on_change()
        except Exception as exc:  # pylint: disable=broad-except
            # If settings.xml is read/write at same time G.ADDON.getSetting...() could thrown a TypeError
            LOG.error('SettingsMonitor: Checks failed due to an error ({})', exc)
            import traceback
            LOG.error(traceback.format_exc())

    def _on_change(self):
        # Reinitialize the log settings
        LOG.initialize(G.ADDON_ID, G.PLUGIN_HANDLE,
                       G.ADDON.getSettingString('debug_log_level'),
                       G.ADDON.getSettingBool('enable_timing'))
        LOG.debug('SettingsMonitor: settings have been changed, started checks')
        reboot_addon = False
        clean_buckets = []

        use_mysql = G.ADDON.getSettingBool('use_mysql')
        use_mysql_old = G.LOCAL_DB.get_value('use_mysql', False, TABLE_SETTINGS_MONITOR)
        use_mysql_turned_on = use_mysql and not use_mysql_old

        # Update global settings
        G.IPC_OVER_HTTP = G.ADDON.getSettingBool('enable_ipc_over_http')
        if use_mysql != use_mysql_old:
            G.init_database()
            clean_buckets.append(CACHE_COMMON)  # Need to be cleaned to reload the Exported menu content
        G.CACHE_MANAGEMENT.load_ttl_values()

        # Verify the MySQL connection status after execute init_database()
        use_mysql_after = G.ADDON.getSettingBool('use_mysql')
        if use_mysql_turned_on and use_mysql_after:
            G.LOCAL_DB.set_value('use_mysql', True, TABLE_SETTINGS_MONITOR)
            ui.show_notification(G.ADDON.getLocalizedString(30202))
        if not use_mysql_after and use_mysql_old:
            G.LOCAL_DB.set_value('use_mysql', False, TABLE_SETTINGS_MONITOR)

        # Check menu settings changes
        for menu_id, menu_data in G.MAIN_MENU_ITEMS.items():
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
                    clean_buckets += [CACHE_COMMON, CACHE_MYLIST, CACHE_SEARCH]

        # Checks for settings changes that require cache invalidation
        page_results = G.ADDON.getSettingInt('page_results')
        page_results_old = G.LOCAL_DB.get_value('page_results', 90, TABLE_SETTINGS_MONITOR)
        if page_results != page_results_old:
            G.LOCAL_DB.set_value('page_results', page_results, TABLE_SETTINGS_MONITOR)
            clean_buckets += [CACHE_COMMON, CACHE_MYLIST, CACHE_SEARCH]

        _check_msl_profiles(clean_buckets)
        _check_watched_status_sync()

        # Clean cache buckets if needed (to get new results and so on...)
        if clean_buckets:
            G.CACHE.clear([dict(t) for t in {tuple(d.items()) for d in clean_buckets}])  # Remove duplicates
        # Avoid perform these operations when the add-on is installed from scratch and there are no credentials
        if reboot_addon and not common.check_credentials():
            reboot_addon = False
        if reboot_addon:
            LOG.debug('SettingsMonitor: addon will be rebooted')
            # Open root page
            common.container_update(common.build_url(['root'], mode=G.MODE_DIRECTORY))


def _check_msl_profiles(clean_buckets):
    """Check for changes on content profiles settings"""
    # This is necessary because it is possible that some manifests
    # could be cached using the previous settings (see load_manifest on msl_handler.py)
    menu_keys = ['enable_dolby_sound', 'enable_vp9_profiles', 'enable_hevc_profiles',
                 'enable_hdr_profiles', 'enable_dolbyvision_profiles', 'enable_force_hdcp',
                 'disable_webvtt_subtitle']
    collect_int = ''
    for menu_key in menu_keys:
        collect_int += str(int(G.ADDON.getSettingBool(menu_key)))
    collect_int_old = G.LOCAL_DB.get_value('content_profiles_int', '', TABLE_SETTINGS_MONITOR)
    if collect_int != collect_int_old:
        G.LOCAL_DB.set_value('content_profiles_int', collect_int, TABLE_SETTINGS_MONITOR)
        clean_buckets.append(CACHE_MANIFESTS)


def _check_watched_status_sync():
    """Check if NF watched status sync setting is changed"""
    progress_manager_enabled = G.ADDON.getSettingBool('ProgressManager_enabled')
    progress_manager_enabled_old = G.LOCAL_DB.get_value('progress_manager_enabled', False, TABLE_SETTINGS_MONITOR)
    if progress_manager_enabled != progress_manager_enabled_old:
        G.LOCAL_DB.set_value('progress_manager_enabled', progress_manager_enabled, TABLE_SETTINGS_MONITOR)
        common.send_signal(signal=common.Signals.SWITCH_EVENTS_HANDLER, data=progress_manager_enabled)
