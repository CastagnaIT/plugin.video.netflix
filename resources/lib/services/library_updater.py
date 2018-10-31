# -*- coding: utf-8 -*-
"""Automatic updates of items exported to the Kodi library"""
from __future__ import unicode_literals

from datetime import datetime, timedelta

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.library as library


class LibraryUpdateService(object):
    """
    Checks if a library update is scheduled and triggers it
    """
    def __init__(self):
        self.startidle = 0
        self.last_schedule_check = datetime.now()

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
        now = datetime.now()
        interval = int(g.ADDON.getSetting('schedule_check_interval'))
        update_frequency = int('0' + g.ADDON.getSetting('auto_update'))
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
