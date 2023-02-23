# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Automatic updates of items exported to the Kodi library

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from datetime import datetime, timedelta

import xbmc

from resources.lib.globals import G
import resources.lib.common as common
from resources.lib.kodi.library_utils import get_library_path
from resources.lib.utils.logging import LOG


class LibraryUpdateService(xbmc.Monitor):
    """
    Checks if a library update is scheduled and triggers it
    """
    def __init__(self):
        super().__init__()
        try:
            self.enabled = (G.ADDON.getSettingBool('lib_enabled')
                            and G.ADDON.getSettingInt('lib_auto_upd_mode') in [0, 2])
        except Exception:  # pylint: disable=broad-except
            # If settings.xml was not created yet, as at first service run
            # G.ADDON.getSettingInt('lib_auto_upd_mode') will thrown a TypeError
            self.enabled = False
        self.startidle = 0
        self.next_schedule = _compute_next_schedule()
        # Request library update variables
        self.scan_in_progress = False
        self.scan_awaiting = False
        self.clean_in_progress = False
        self.clean_awaiting = False
        common.register_slot(self.request_kodi_library_update, common.Signals.REQUEST_KODI_LIBRARY_UPDATE,
                             is_signal=True)

    def on_service_tick(self):
        """Check if update is due and trigger it"""
        if not self.enabled or self.next_schedule is None:
            return
        if self.next_schedule <= datetime.now() and self.is_idle():
            # Check if the schedule value is changed
            # (when a manual update/full sync is done, we avoid to perform again the update)
            self.next_schedule = _compute_next_schedule()
            if self.next_schedule >= datetime.now():
                return
            LOG.debug('Triggering auto update library')
            # Send signal to nfsession to run the library auto update
            common.send_signal('library_auto_update')
            # Compute the next schedule
            self.next_schedule = _compute_next_schedule(datetime.now())

    def is_idle(self):
        """
        Check if Kodi has been idle for 5 minutes
        """
        try:
            if not G.ADDON.getSettingBool('lib_auto_upd_wait_idle'):
                return True
        except TypeError:
            # Could happen when the service tick is executed at the same time when the settings are written
            return False
        lastidle = xbmc.getGlobalIdleTime()
        if xbmc.Player().isPlaying():
            self.startidle = lastidle
        if lastidle < self.startidle:
            self.startidle = 0
        idletime = lastidle - self.startidle
        return idletime >= 300

    def onSettingsChanged(self):
        """
        As settings changed, we will compute next schedule again to ensure it's still correct
        """
        # Wait for slow system (like Raspberry Pi) to write the settings
        xbmc.sleep(500)
        # Check if the status is changed
        self.enabled = (G.ADDON.getSettingBool('lib_enabled')
                        and G.ADDON.getSettingInt('lib_auto_upd_mode') in [0, 2])
        # Then compute the next schedule
        if self.enabled:
            self.next_schedule = _compute_next_schedule()

    def onScanStarted(self, library):
        """Monitor library scan to avoid multiple calls"""
        if library == 'video':
            self.scan_in_progress = True

    def onScanFinished(self, library):
        """Monitor library scan to avoid multiple calls"""
        if library == 'video':
            self.scan_in_progress = False
            self.check_awaiting_operations()

    def onCleanStarted(self, library):
        """Monitor library clean to avoid multiple calls"""
        if library == 'video':
            self.clean_in_progress = True

    def onCleanFinished(self, library):
        """Monitor library clean to avoid multiple calls"""
        if library == 'video':
            self.clean_in_progress = False
            self.check_awaiting_operations()

    def request_kodi_library_update(self, clean=False, scan=False):
        """Make a request for scan/clean the Kodi library database"""
        # Kodi library scan/clean has some issues (Kodi 18/19), for example:
        # - If more than one scan calls will be performed, the last call cancel the previous scan
        # - If a clean is in progress, a new scan/clean call will be ignored
        # To manage these problems we monitor the events to check if a scan/clean is currently in progress
        # (from this or others add-ons) and delay the call until the current scan/clean will be finished.
        if clean:
            self.start_clean_kodi_library()
        if scan:
            self.start_update_kodi_library()

    def check_awaiting_operations(self):
        if self.clean_awaiting:
            LOG.debug('Kodi library clean requested (from awaiting)')
            self.start_clean_kodi_library()
        if self.scan_awaiting:
            LOG.debug('Kodi library scan requested (from awaiting)')
            self.start_update_kodi_library()

    def start_update_kodi_library(self):
        if not self.scan_in_progress and not self.clean_in_progress:
            LOG.debug('Start Kodi library scan')
            self.scan_in_progress = True  # Set as in progress (avoid wait "started" callback it comes late)
            self.scan_awaiting = False
            common.scan_library(get_library_path())
        else:
            self.scan_awaiting = True

    def start_clean_kodi_library(self):
        if not self.scan_in_progress and not self.clean_in_progress:
            LOG.debug('Start Kodi library clean')
            self.clean_in_progress = True  # Set as in progress (avoid wait "started" callback it comes late)
            self.clean_awaiting = False
            common.clean_library(False, get_library_path())
        else:
            self.clean_awaiting = True


def _compute_next_schedule(date_last_start=None):
    try:
        if G.ADDON.getSettingBool('use_mysql'):
            client_uuid = G.LOCAL_DB.get_value('client_uuid')
            uuid = G.SHARED_DB.get_value('auto_update_device_uuid')
            if client_uuid != uuid:
                LOG.debug('The auto update has been disabled because another device '
                          'has been set as the main update manager')
                return None

        last_run = date_last_start or G.SHARED_DB.get_value('library_auto_update_last_start',
                                                            datetime.utcfromtimestamp(0))
        if G.ADDON.getSettingInt('lib_auto_upd_mode') == 0:  # Update at Kodi startup
            time = '00:00'
            update_frequency = 0
        else:
            time = G.ADDON.getSetting('lib_auto_upd_start') or '00:00'
            update_frequency = G.ADDON.getSettingInt('lib_auto_upd_freq')

        last_run = last_run.replace(hour=int(time[0:2]), minute=int(time[3:5]))
        next_run = last_run + timedelta(days=[1, 2, 5, 7][update_frequency])
        if next_run >= datetime.now():
            LOG.info('Next library auto update is scheduled for {}', next_run)
        return next_run
    except Exception:  # pylint: disable=broad-except
        # If settings.xml was not created yet, as at first service run
        # G.ADDON.getSettingBool('use_mysql') will thrown a TypeError
        # If any other error appears, we don't want the service to crash,
        # let's return None in all case
        # import traceback
        # LOG.debug(traceback.format_exc())
        LOG.warn('Managed error at _compute_next_schedule')
        return None
