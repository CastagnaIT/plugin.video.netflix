# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Check if the addon has been updated and make necessary changes

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from resources.lib.common.misc_utils import is_less_version, is_minimum_version
from resources.lib.database.db_update import run_local_db_updates, run_shared_db_updates
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


def check_addon_upgrade():
    """
    Check addon upgrade and perform necessary update operations

    :return tuple boolean 1: True if this is the first run of the add-on after an installation from scratch
                  boolean 2: True to cancel a playback after upgrade
                             (if user was trying to playback from kodi library so without open the add-on interface)
    """
    # Upgrades that require user interaction or to be performed outside of the service
    cancel_playback = False
    addon_previous_ver = G.LOCAL_DB.get_value('addon_previous_version', None)
    addon_current_ver = G.VERSION
    if addon_previous_ver is None or is_less_version(addon_previous_ver, addon_current_ver):
        cancel_playback = _perform_addon_changes(addon_previous_ver, addon_current_ver)
    return addon_previous_ver is None, cancel_playback


def check_service_upgrade():
    """Check service upgrade and perform necessary update operations"""
    # Upgrades to be performed before starting the service
    # Upgrade the local database
    current_local_db_version = G.LOCAL_DB.get_value('local_db_version', None)
    upgrade_to_local_db_version = '0.2'
    if current_local_db_version != upgrade_to_local_db_version:
        _perform_local_db_changes(current_local_db_version, upgrade_to_local_db_version)

    # Upgrade the shared databases
    current_shared_db_version = G.LOCAL_DB.get_value('shared_db_version', None)
    upgrade_to_shared_db_version = '0.2'
    if current_local_db_version != upgrade_to_local_db_version:
        _perform_shared_db_changes(current_shared_db_version, upgrade_to_shared_db_version)

    # Perform service changes
    service_previous_ver = G.LOCAL_DB.get_value('service_previous_version', None)
    service_current_ver = G.VERSION
    if service_previous_ver is None or is_less_version(service_previous_ver, service_current_ver):
        _perform_service_changes(service_previous_ver, service_current_ver)


def _perform_addon_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    cancel_playback = False
    LOG.debug('Initialize addon upgrade operations, from version {} to {})', previous_ver, current_ver)
    if previous_ver and is_less_version(previous_ver, '0.15.9'):
        import resources.lib.kodi.ui as ui
        msg = ('This update resets the settings to auto-update library.\r\n'
               'Therefore only in case you are using auto-update must be reconfigured.')
        ui.show_ok_dialog('Netflix upgrade', msg)
    if previous_ver and is_less_version(previous_ver, '1.7.0'):
        from resources.lib.upgrade_actions import migrate_library
        migrate_library()
        cancel_playback = True
    # Always leave this to last - After the operations set current version
    G.LOCAL_DB.set_value('addon_previous_version', current_ver)
    return cancel_playback


def _perform_service_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    LOG.debug('Initialize service upgrade operations, from version {} to {})', previous_ver, current_ver)
    # Clear cache (prevents problems when netflix change data structures)
    G.CACHE.clear()
    if previous_ver and is_less_version(previous_ver, '1.2.0'):
        # In the version 1.2.0 has been implemented a new cache management
        from resources.lib.upgrade_actions import delete_cache_folder
        delete_cache_folder()
        # In the version 1.2.0 has been implemented in auto-update mode setting the option to disable the feature
        try:
            lib_auto_upd_mode = G.ADDON.getSettingInt('lib_auto_upd_mode')
            G.ADDON.setSettingInt('lib_auto_upd_mode', lib_auto_upd_mode + 1)
        except TypeError:
            # In case of a previous rollback this could fails
            G.ADDON.setSettingInt('lib_auto_upd_mode', 1)
    if previous_ver and is_less_version(previous_ver, '1.9.0'):
        # In the version 1.9.0 has been changed the COOKIE_ filename with a static filename
        from resources.lib.upgrade_actions import rename_cookie_file
        rename_cookie_file()
    # Always leave this to last - After the operations set current version
    G.LOCAL_DB.set_value('service_previous_version', current_ver)


def _perform_local_db_changes(current_version, upgrade_to_version):
    """Perform database actions for a db version change"""
    if current_version is not None:
        LOG.debug('Initialization of local database updates from version {} to {})',
                  current_version, upgrade_to_version)
        run_local_db_updates(current_version, upgrade_to_version)
    G.LOCAL_DB.set_value('local_db_version', upgrade_to_version)


def _perform_shared_db_changes(current_version, upgrade_to_version):
    """Perform database actions for a db version change"""
    # This is a temporary bug fix, to be removed on future addon versions,
    # this because a previous oversight never saved the current version
    # Init fix
    service_previous_ver = G.LOCAL_DB.get_value('service_previous_version', None)
    if service_previous_ver is not None and\
            current_version is None and\
            not is_minimum_version(service_previous_ver, '0.17.0'):
        current_version = '0.1'
    # End fix

    if current_version is not None:
        LOG.debug('Initialization of shared databases updates from version {} to {})',
                  current_version, upgrade_to_version)
        run_shared_db_updates(current_version, upgrade_to_version)
    G.LOCAL_DB.set_value('shared_db_version', upgrade_to_version)
