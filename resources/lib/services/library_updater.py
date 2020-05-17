# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Automatic updates of items exported to the Kodi library

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from datetime import datetime, timedelta

import AddonSignals
import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.library as kodi_library
from resources.lib.kodi.library_autoupdate import auto_update_library

try:  # Kodi >= 19
    from xbmcvfs import makeLegalFilename  # pylint: disable=ungrouped-imports
except ImportError:  # Kodi 18
    from xbmc import makeLegalFilename  # pylint: disable=ungrouped-imports


class LibraryUpdateService(xbmc.Monitor):
    """
    Checks if a library update is scheduled and triggers it
    """

    def __init__(self):
        try:
            self.enabled = g.ADDON.getSettingInt('lib_auto_upd_mode') == 2
        except Exception:  # pylint: disable=broad-except
            # If settings.xml was not created yet, as at first service run
            # g.ADDON.getSettingInt('lib_auto_upd_mode') will thrown a TypeError
            # If any other error appears, we don't want the service to crash,
            # let's return None in all case
            self.enabled = False

        self.startidle = 0
        self.next_schedule = _compute_next_schedule()

        # Update library variables
        xbmc.Monitor.__init__(self)
        self.scan_in_progress = False
        self.scan_awaiting = False
        AddonSignals.registerSlot(
            g.ADDON.getAddonInfo('id'), common.Signals.LIBRARY_UPDATE_REQUESTED,
            self.update_kodi_library)

    def on_service_tick(self):
        """Check if update is due and trigger it"""
        if not self.enabled:
            return
        if (self.next_schedule is not None
                and self.next_schedule <= datetime.now()
                and self.is_idle()):
            common.debug('Triggering auto update library')

            common.run_threaded(True, auto_update_library, g.ADDON.getSettingBool('lib_sync_mylist'), True)

            g.SHARED_DB.set_value('library_auto_update_last_start', datetime.now())
            self.next_schedule = _compute_next_schedule()

    def is_idle(self):
        """
        Check if Kodi has been idle for 5 minutes
        """
        if not g.ADDON.getSettingBool('lib_auto_upd_wait_idle'):
            return True

        lastidle = xbmc.getGlobalIdleTime()
        if xbmc.Player().isPlaying():
            self.startidle = lastidle
        if lastidle < self.startidle:
            self.startidle = 0
        idletime = lastidle - self.startidle
        return idletime >= 300

    def onSettingsChanged(self):
        """
        As settings changed, we will compute next schedule again
        to ensure it's still correct
        """
        # Wait for slow system (like Raspberry Pi) to write the settings
        xbmc.sleep(500)
        # Check if the status is changed
        self.enabled = g.ADDON.getSettingInt('lib_auto_upd_mode') == 2
        # Then compute the next schedule
        if self.enabled:
            self.next_schedule = _compute_next_schedule()

    def onScanStarted(self, library):
        """Monitor library scan to avoid multiple calls"""
        # Kodi cancels the update if called with JSON RPC twice
        # so we monitor events to ensure we're not cancelling a previous scan
        if library == 'video':
            self.scan_in_progress = True

    def onScanFinished(self, library):
        """Monitor library scan to avoid multiple calls"""
        # Kodi cancels the update if called with JSON RPC twice
        # so we monitor events to ensure we're not cancelling a previous scan
        if library == 'video':
            self.scan_in_progress = False
            if self.scan_awaiting:
                common.debug('Kodi library update requested from library auto-update (from awaiting)')
                self.update_kodi_library()

    def update_kodi_library(self, data=None):  # pylint: disable=unused-argument
        # Update only the elements in the addon export folder for faster processing with a large library (on Kodi 18.x)
        # If a scan is already in progress, the scan is delayed until onScanFinished event
        if not self.scan_in_progress:
            common.debug('Kodi library update requested from library auto-update')
            self.scan_awaiting = False
            common.scan_library(
                makeLegalFilename(
                    xbmc.translatePath(
                        kodi_library.library_path())))
        else:
            self.scan_awaiting = True


def _compute_next_schedule():
    try:
        if g.ADDON.getSettingBool('use_mysql'):
            client_uuid = g.LOCAL_DB.get_value('client_uuid')
            uuid = g.SHARED_DB.get_value('auto_update_device_uuid')
            if client_uuid != uuid:
                common.debug('The auto update has been disabled because another device '
                             'has been set as the main update manager')
                return None

        time = g.ADDON.getSetting('lib_auto_upd_start') or '00:00'
        last_run = g.SHARED_DB.get_value('library_auto_update_last_start',
                                         datetime.utcfromtimestamp(0))
        update_frequency = g.ADDON.getSettingInt('lib_auto_upd_freq')

        last_run = last_run.replace(hour=int(time[0:2]), minute=int(time[3:5]))
        next_run = last_run + timedelta(days=[1, 2, 5, 7][update_frequency])
        if next_run >= datetime.now():
            common.info('Next library auto update is scheduled for {}', next_run)
        return next_run
    except Exception:  # pylint: disable=broad-except
        # If settings.xml was not created yet, as at first service run
        # g.ADDON.getSettingBool('use_mysql') will thrown a TypeError
        # If any other error appears, we don't want the service to crash,
        # let's return None in all case
        # import traceback
        # common.debug(g.py2_decode(traceback.format_exc(), 'latin-1'))
        common.warn('Managed error at _compute_next_schedule')
        return None
