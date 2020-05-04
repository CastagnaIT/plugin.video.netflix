# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Smeulf (original implementation module)
    Operations for changing the playback status

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time

import xbmc

import resources.lib.common as common

from .action_manager import ActionManager


class AMPlayback(ActionManager):
    """Operations for changing the playback status"""

    SETTING_ID = 'ResumeManager_enabled'

    def __init__(self):
        super(AMPlayback, self).__init__()
        self.resume_position = None
        self.enabled = True
        self.start_time = None
        self.is_player_in_pause = False

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def initialize(self, data):
        # Due to a bug on Kodi the resume on SRTM files not works correctly, so we force the skip to the resume point
        self.resume_position = data.get('resume_position')

    def on_playback_started(self, player_state):
        if self.resume_position:
            common.info('AMPlayback has forced resume point to {}', self.resume_position)
            xbmc.Player().seekTime(int(self.resume_position))

    def on_tick(self, player_state):
        # Stops playback when paused for more than one hour.
        # Some users leave the playback paused also for more than 12 hours,
        # this complicates things to resume playback, because the manifest data expires and with it also all
        # the streams urls are no longer guaranteed, so we force the stop of the playback.
        if self.is_player_in_pause and (time.time() - self.start_time) > 3600:
            common.info('The playback has been stopped because it has been exceeded 1 hour of pause')
            common.stop_playback()

    def on_playback_pause(self, player_state):
        self.start_time = time.time()
        self.is_player_in_pause = True

    def on_playback_resume(self, player_state):
        self.is_player_in_pause = False
