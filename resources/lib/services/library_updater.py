# -*- coding: utf-8 -*-
"""Automatic updates of items exported to the Kodi library"""
from __future__ import unicode_literals

from datetime import datetime, timedelta

import AddonSignals
import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.library as library


class LibraryUpdateService(xbmc.Monitor):
    """
    Checks if a library update is scheduled and triggers it
    """
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.scan_in_progress = False
        self.scan_awaiting = False
        self.startidle = 0
        self.last_schedule_check = datetime.now()

        AddonSignals.registerSlot(
            g.ADDON.getAddonInfo('id'), common.Signals.LIBRARY_UPDATE_REQUESTED,
            self.update_kodi_library)

    def on_tick(self):
        """Check if update is due and trigger it"""
        if self.library_update_scheduled() and self.is_idle():
            library.update_library()

    def is_idle(self):
        """
        Check if Kodi has been idle for 5 minutes
        """
        if not g.ADDON.getSettingBool('wait_idle'):
            return True

        lastidle = xbmc.getGlobalIdleTime()
        if xbmc.Player().isPlaying():
            self.startidle = lastidle
        if lastidle < self.startidle:
            self.startidle = 0
        idletime = lastidle - self.startidle
        return idletime >= 300

    def library_update_scheduled(self):
        """
        Checks if the scheduled time for a library update has been reached
        """
        try:
            now = datetime.now()
            update_frequency = g.ADDON.getSettingInt('auto_update')
            interval = g.ADDON.getSettingInt('schedule_check_interval')
            next_schedule_check = (self.last_schedule_check +
                                   timedelta(minutes=interval))

            if not update_frequency or now <= next_schedule_check:
                return False

            self.last_schedule_check = now
            time = g.ADDON.getSetting('update_time') or '00:00'
            lastrun_date = (g.ADDON.getSetting('last_update') or
                            '1970-01-01')
            lastrun = common.strp('{} {}'.format(lastrun_date, time[0:5]),
                                  '%Y-%m-%d %H:%M')
            nextrun = lastrun + timedelta(days=[0, 1, 2, 5, 7][update_frequency])
            common.log(
                'It\'s currently {}, next run is scheduled for {}'
                .format(now, nextrun))

            return now >= nextrun
        except TypeError:
            # When there is concurrency between getSettingX and setSettingX at the same time,
            # the get settings fails to read
            return False


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


    def update_kodi_library(self, data = None):
        # Update only the elements in the addon export folder
        # for faster processing with a large library.
        # If a scan is already in progress, the scan is delayed until onScanFinished event
        common.debug('Library update requested for library updater service')
        if not self.scan_in_progress:
            self.scan_awaiting = False
            common.scan_library(
                    xbmc.makeLegalFilename(
                        xbmc.translatePath(
                            library.library_path())))
        else:
            self.scan_awaiting = True
