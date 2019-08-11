# -*- coding: utf-8 -*-
"""Check if the addon has been updated and make necessary changes"""
from __future__ import unicode_literals

import resources.lib.common as common

import resources.lib.upgrade_actions as upgrade_actions
from resources.lib.globals import g
from resources.lib.database.db_update import run_local_db_updates, run_shared_db_updates


def check_addon_upgrade():
    """Check addon upgrade and perform necessary update operations"""
    # Upgrades that require user interaction or to be performed outside of the service
    addon_previous_ver = g.LOCAL_DB.get_value('addon_previous_version', None)
    addon_current_ver = g.VERSION
    if addon_current_ver != addon_previous_ver:
        _perform_addon_changes(addon_previous_ver, addon_current_ver)


def check_service_upgrade():
    """Check service upgrade and perform necessary update operations"""
    # Upgrades to be performed before starting the service
    # Database upgrade
    local_db_version = g.LOCAL_DB.get_value('local_db_version', '0.1')
    shared_db_version = g.LOCAL_DB.get_value('shared_db_version', '0.1')
    _perform_local_db_changes(local_db_version)
    _perform_shared_db_changes(shared_db_version)
    # Perform service changes
    service_previous_ver = g.LOCAL_DB.get_value('service_previous_version', None)
    service_current_ver = g.VERSION
    if service_current_ver != service_previous_ver:
        _perform_service_changes(service_previous_ver, service_current_ver)


def _perform_addon_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    common.debug('Initialize addon upgrade operations, from version {} to {})'
                 .format(previous_ver, current_ver))
    # Always leave this to last - After the operations set current version
    g.LOCAL_DB.set_value('addon_previous_version', current_ver)


def _perform_service_changes(previous_ver, current_ver):
    """Perform actions for an version bump"""
    common.debug('Initialize service upgrade operations, from version {} to {})'
                 .format(previous_ver, current_ver))
    if previous_ver is None:
        upgrade_actions.migrate_library_to_db()
    # Always leave this to last - After the operations set current version
    g.LOCAL_DB.set_value('service_previous_version', current_ver)


def _perform_local_db_changes(db_version):
    """Perform database actions for a db version change"""
    db_new_version = '0.1'
    if db_version != db_new_version:
        common.debug('Initialization of local database updates from version {} to {})'
                     .format(db_version, db_new_version))
        run_local_db_updates(db_version, db_new_version)
        g.LOCAL_DB.set_value('local_db_version', db_new_version)


def _perform_shared_db_changes(db_version):
    """Perform database actions for a db version change"""
    db_new_version = '0.1'
    if db_version != db_new_version:
        common.debug('Initialization of shared database updates from version {} to {})'
                     .format(db_version, db_new_version))
        run_shared_db_updates(db_version, db_new_version)
        g.LOCAL_DB.set_value('shared_db_version', db_new_version)
