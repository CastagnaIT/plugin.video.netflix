# -*- coding: utf-8 -*-
"""Automatic updates of items exported to the Kodi library"""
from __future__ import absolute_import, division, unicode_literals

import AddonSignals
from xbmc import Monitor

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.library as kodi_library


class LibraryUpdateService(Monitor):
    """
    Checks if a library update is scheduled and triggers it
    """

    def __init__(self):
        try:
            self.enabled = g.ADDON.getSettingInt('lib_auto_upd_mode') == 1
        except Exception:  # pylint: disable=broad-except
            # If settings.xml was not created yet, as at first service run
            # g.ADDON.getSettingInt('lib_auto_upd_mode') will thrown a TypeError
            # If any other error appears, we don't want the service to crash,
            # let's return None in all case
            self.enabled = False

        self.startidle = 0
        self.next_schedule = _compute_next_schedule()

        # Update library variables
        Monitor.__init__(self)
        self.scan_in_progress = False
        self.scan_awaiting = False
        AddonSignals.registerSlot(
            g.ADDON.getAddonInfo('id'), common.Signals.LIBRARY_UPDATE_REQUESTED,
            self.update_kodi_library)

    def on_tick(self):
        """Check if update is due and trigger it"""
        if not self.enabled:
            return
        from datetime import datetime
        if (self.next_schedule is not None
                and self.is_idle()
                and self.next_schedule <= datetime.now()):
            from xbmc import executebuiltin
            common.debug('Triggering auto update library')
            executebuiltin('XBMC.RunPlugin(plugin://{}/library/service_auto_upd_run_now/)'.format(g.ADDON_ID))
            g.SHARED_DB.set_value('library_auto_update_last_start', datetime.now())
            self.next_schedule = _compute_next_schedule()

    def is_idle(self):
        """
        Check if Kodi has been idle for 5 minutes
        """
        if not g.ADDON.getSettingBool('lib_auto_upd_wait_idle'):
            return True

        from xbmc import getGlobalIdleTime, Player
        lastidle = getGlobalIdleTime()
        if Player().isPlaying():
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
        from xbmc import sleep
        # Wait for slow system (like Raspberry Pi) to write the settings
        sleep(500)
        # Check if the status is changed
        self.enabled = g.ADDON.getSettingInt('lib_auto_upd_mode') == 1
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
                self.update_kodi_library()

    def update_kodi_library(self, data=None):  # pylint: disable=unused-argument
        # Update only the elements in the addon export folder
        # for faster processing with a large library.
        # If a scan is already in progress, the scan is delayed until onScanFinished event
        common.debug('Library update requested for library updater service')
        if not self.scan_in_progress:
            from xbmc import makeLegalFilename, translatePath
            self.scan_awaiting = False
            common.scan_library(makeLegalFilename(translatePath(kodi_library.library_path())))
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

        from datetime import datetime, timedelta
        time = g.ADDON.getSetting('lib_auto_upd_start') or '00:00'
        last_run = g.SHARED_DB.get_value('library_auto_update_last_start',
                                         datetime.utcfromtimestamp(0))
        update_frequency = g.ADDON.getSettingInt('lib_auto_upd_freq')

        last_run = last_run.replace(hour=int(time[0:2]), minute=int(time[3:5]))
        next_run = last_run + timedelta(days=[1, 2, 5, 7][update_frequency])
        common.info('Next library auto update is scheduled for {}', next_run)
        return next_run
    except Exception:  # pylint: disable=broad-except
        # If settings.xml was not created yet, as at first service run
        # g.ADDON.getSettingBool('use_mysql') will thrown a TypeError
        # If any other error appears, we don't want the service to crash,
        # let's return None in all case
        # import traceback
        # common.debug(traceback.format_exc())
        common.warn('Managed error at _compute_next_schedule')
        return None
