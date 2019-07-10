# -*- coding: utf-8 -*-
"""Automatic updates of items exported to the Kodi library"""
from __future__ import unicode_literals

from datetime import date, datetime, timedelta

import AddonSignals
import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.library as kodi_library


class LibraryUpdateService(xbmc.Monitor):
    """
    Checks if a library update is scheduled and triggers it
    """

    def __init__(self):

        # Export new episodes variables
        self.startidle = 0
        # self.last_schedule_check = datetime.now()
        self.next_schedule = _compute_next_schedule()

        # Update library variables
        xbmc.Monitor.__init__(self)
        self.scan_in_progress = False
        self.scan_awaiting = False
        AddonSignals.registerSlot(
            g.ADDON.getAddonInfo('id'), common.Signals.LIBRARY_UPDATE_REQUESTED,
            self.update_kodi_library)

    def on_tick(self):
        """Check if update is due and trigger it"""
        if (self.next_schedule is not None
                and self.is_idle()
                and self.next_schedule <= datetime.now()):
            common.debug('Triggering export new episodes')
            xbmc.executebuiltin('XBMC.RunPlugin(plugin://{}/library/exportallnewepisodes/)'
                                .format(g.ADDON_ID))
            g.PERSISTENT_STORAGE['library_auto_update_last_start'] = \
                date.today().strftime('%Y-%m-%d')
            self.next_schedule = _compute_next_schedule()

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

    def onSettingsChanged(self):
        """
        As settings changed, we will compute next schedule again
        to ensure it's still correct
        """
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

    def update_kodi_library(self, data=None):
        # Update only the elements in the addon export folder
        # for faster processing with a large library.
        # If a scan is already in progress, the scan is delayed until onScanFinished event
        common.debug('Library update requested for library updater service')
        if not self.scan_in_progress:
            self.scan_awaiting = False
            common.scan_library(
                xbmc.makeLegalFilename(
                    xbmc.translatePath(
                        kodi_library.library_path())))
        else:
            self.scan_awaiting = True


def _compute_next_schedule():
    update_frequency = g.ADDON.getSettingInt('auto_update')

    if not update_frequency:
        common.debug('Library auto update scheduled is disabled')
        return None

    time = g.ADDON.getSetting('update_time') or '00:00'
    last_run = g.PERSISTENT_STORAGE.get(
        'library_auto_update_last_start',
        '1970-01-01')
    last_run = common.strp('{} {}'.format(last_run, time[0:5]),
                           '%Y-%m-%d %H:%M')
    next_run = last_run + timedelta(days=[0, 1, 2, 5, 7][update_frequency])
    common.debug('Next library auto update is scheduled for {}'.format(next_run))
    return next_run
