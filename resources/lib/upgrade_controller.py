# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Check if the addon has been updated and make necessary changes

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.common import is_device_4k_capable
from resources.lib.common.misc_utils import CmpVersion
from resources.lib.database.db_update import run_local_db_updates, run_shared_db_updates
from resources.lib.globals import G, remove_ver_suffix
from resources.lib.utils.logging import LOG


def check_addon_upgrade():
    """
    Check addon upgrade and perform necessary update operations

    :return True if this is the first run of the add-on after an installation from scratch
    """
    # Upgrades that require user interaction or to be performed outside of the service
    addon_previous_ver = G.LOCAL_DB.get_value('addon_previous_version', None)
    addon_current_ver = G.VERSION
    if addon_previous_ver is None or CmpVersion(addon_current_ver) > addon_previous_ver:
        _perform_addon_changes(addon_previous_ver, addon_current_ver)
        G.LOCAL_DB.set_value('addon_previous_version', addon_current_ver)
    return addon_previous_ver is None


def check_service_upgrade():
    """Check service upgrade and perform necessary update operations"""
    # Upgrades to be performed before starting the service
    # Upgrade the local database
    current_local_db_version = G.LOCAL_DB.get_value('local_db_version', None)
    upgrade_to_local_db_version = '0.2'
    if current_local_db_version != upgrade_to_local_db_version:
        _perform_local_db_changes(current_local_db_version, upgrade_to_local_db_version)
        G.LOCAL_DB.set_value('local_db_version', upgrade_to_local_db_version)

    # Upgrade the shared databases
    current_shared_db_version = G.LOCAL_DB.get_value('shared_db_version', None)
    upgrade_to_shared_db_version = '0.2'
    if current_shared_db_version != upgrade_to_shared_db_version:
        _perform_shared_db_changes(current_shared_db_version, upgrade_to_shared_db_version)
        G.LOCAL_DB.set_value('shared_db_version', upgrade_to_shared_db_version)

    # Perform service changes
    service_previous_ver = G.LOCAL_DB.get_value('service_previous_version', None)
    service_current_ver = G.VERSION
    if service_previous_ver is None or CmpVersion(service_current_ver) > service_previous_ver:
        _perform_service_changes(service_previous_ver, service_current_ver)
        G.LOCAL_DB.set_value('service_previous_version', service_current_ver)


def _perform_addon_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    LOG.debug('Initialize add-on upgrade operations, from version {} to {}', previous_ver, current_ver)
    if not previous_ver:
        return
    if CmpVersion(previous_ver) < '1.16.2':
        from xbmcaddon import Addon
        isa_version = remove_ver_suffix(Addon('inputstream.adaptive').getAddonInfo('version'))
        if CmpVersion(isa_version) < '2.6.18':
            from resources.lib.kodi import ui
            ui.show_ok_dialog('Netflix add-on upgrade',
                              'The currently installed [B]InputStream Adaptive add-on[/B] version not support Netflix HD videos.'
                              '[CR]To get HD video contents, please update it to the last version.')


def _perform_service_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    LOG.debug('Initialize add-on service upgrade operations, from version {} to {}', previous_ver, current_ver)
    # Clear cache (prevents problems when netflix change data structures)
    G.CACHE.clear()
    if not previous_ver:
        return
    # Delete all stream continuity data - if user has upgraded from Kodi 18 to Kodi 19
    if CmpVersion(previous_ver) < '1.13':
        # There is no way to determine if the user has migrated from Kodi 18 to Kodi 19,
        #   then we assume that add-on versions prior to 1.13 was on Kodi 18
        # The am_stream_continuity.py on Kodi 18 works differently and the existing data can not be used on Kodi 19
        G.SHARED_DB.clear_stream_continuity()
        # Disable enable_hevc_profiles if has been wrongly enabled by the user and it is unsupported by the systems
        with G.SETTINGS_MONITOR.ignore_events(1):
            is_4k_capable = is_device_4k_capable()
            G.ADDON.setSettingBool('enable_hevc_profiles', is_4k_capable)
    if CmpVersion(previous_ver) < '1.9.0':
        # In the version 1.9.0 has been changed the COOKIE_ filename with a static filename
        from resources.lib.upgrade_actions import rename_cookie_file
        rename_cookie_file()
    if CmpVersion(previous_ver) < '1.12.0':
        # In the version 1.13.0:
        # - 'force_widevine' on setting.xml has been moved
        #   as 'widevine_force_seclev' in TABLE_SESSION with different values:
        # force_widevine = G.ADDON.getSettingString('force_widevine')
        # # Old values: Disabled|Widevine L3|Widevine L3 (ID-4445)
        # # New values: Disabled|L3|L3 (ID 4445)
        # if force_widevine == 'Widevine L3':
        #     G.LOCAL_DB.set_value('widevine_force_seclev', 'L3', table=TABLE_SESSION)
        # elif force_widevine == 'Widevine L3 (ID-4445)':
        #     G.LOCAL_DB.set_value('widevine_force_seclev', 'L3 (ID 4445)', table=TABLE_SESSION)
        # # - 'esn' on setting.xml is not more used but if was set the value need to be copied on 'esn' on TABLE_SESSION:
        # esn = G.ADDON.getSettingString('esn')
        # if esn:
        #     from resources.lib.utils.esn import set_esn
        #     set_esn(esn)
        # - 'suspend_settings_monitor' is not more used
        G.LOCAL_DB.delete_key('suspend_settings_monitor')
        # In the version 1.14.0 the new settings.xml format has been introduced
        # the migration of the settings (commented above) from this version is no more possible
        from resources.lib.kodi import ui
        ui.show_ok_dialog('Netflix add-on upgrade',
                          'This add-on upgrade has reset your ESN code, if you had set an ESN code manually '
                          'you must re-enter it again in the Expert settings, otherwise simply ignore this message.')
    if CmpVersion(previous_ver) < '1.16.0':
        # In the version 1.16.0 the watched status sync setting has been enabled by default,
        # therefore to be able to keep the user's setting even when it has never been changed,
        # we have done a new setting (ProgressManager_enabled >> to >> sync_watched_status)
        with G.SETTINGS_MONITOR.ignore_events(1):
            G.ADDON.setSettingBool('sync_watched_status', G.ADDON.getSettingBool('ProgressManager_enabled'))


def _perform_local_db_changes(current_version, upgrade_to_version):
    """Perform database actions for a db version change"""
    if current_version is not None:
        LOG.debug('Initialize local database updates, from version {} to {}',
                  current_version, upgrade_to_version)
        run_local_db_updates(current_version, upgrade_to_version)


def _perform_shared_db_changes(current_version, upgrade_to_version):
    """Perform database actions for a db version change"""
    if current_version is not None:
        LOG.debug('Initialize shared databases updates, from version {} to {}',
                  current_version, upgrade_to_version)
        run_shared_db_updates(current_version, upgrade_to_version)
