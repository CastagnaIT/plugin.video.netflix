# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Manages events to send to the netflix service for the progress of the played video

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from xbmcgui import Window

import resources.lib.common as common
from resources.lib.services.msl.msl_utils import EVENT_START, EVENT_ENGAGE, EVENT_STOP, EVENT_KEEP_ALIVE
from .action_manager import PlaybackActionManager


class ProgressManager(PlaybackActionManager):
    """Detect the progress of the played video and send the data to the netflix service"""

    def __init__(self):  # pylint: disable=super-on-old-class
        super(ProgressManager, self).__init__()
        self.event_data = {}
        self.is_event_start_sent = False
        self.last_tick_count = 0
        self.tick_elapsed = 0
        self.last_player_state = {}
        self.is_player_in_pause = False
        self.lock_events = False
        self.window_cls = Window(10000)  # Kodi home window

    def _initialize(self, data):
        if not data['event_data']:
            common.warn('ProgressManager: disabled due to no event data')
            self.enabled = False
            return
        self.event_data = data['event_data']

    def _on_tick(self, player_state):
        if self.lock_events:
            return
        if self.is_player_in_pause and (self.tick_elapsed - self.last_tick_count) >= 1800:
            # When the player is paused for more than 30 minutes we interrupt the sending of events (1800secs=30m)
            _send_event(EVENT_ENGAGE, self.event_data, self.last_player_state)
            _send_event(EVENT_STOP, self.event_data, self.last_player_state)
            self.is_event_start_sent = False
            self.lock_events = True
        else:
            if not self.is_event_start_sent:
                # We do not use _on_playback_started() to send EVENT_START, because StreamContinuityManager
                # and ResumeManager may cause inconsistencies with the content of player_state data

                # When the playback starts for the first time, for correctness should send elapsed_seconds value to 0
                if self.tick_elapsed < 5 and self.event_data['resume_position'] is None:
                    player_state['elapsed_seconds'] = 0
                _send_event(EVENT_START, self.event_data, player_state)
                self.is_event_start_sent = True
                self.tick_elapsed = 0
            else:
                # Generate events to send to Netflix service every 1 minute (60secs=1m)
                if (self.tick_elapsed - self.last_tick_count) >= 60:
                    _send_event(EVENT_KEEP_ALIVE, self.event_data, player_state)
                    self.last_tick_count = self.tick_elapsed
                # On Kodi we can save every second instead every minute, but only after the first minute
                if self.last_tick_count:
                    self._save_resume_time(player_state['elapsed_seconds'])
        self.last_player_state = player_state
        self.tick_elapsed += 1  # One tick almost always represents one second

    def on_playback_pause(self, player_state):
        if not self.is_event_start_sent:
            return
        self.tick_elapsed = 0
        self.is_player_in_pause = True
        _send_event(EVENT_ENGAGE, self.event_data, player_state)

    def on_playback_resume(self, player_state):
        self.is_player_in_pause = False
        self.lock_events = False

    def on_playback_seek(self, player_state):
        if not self.is_event_start_sent or self.lock_events:
            # This might happen when ResumeManager skip is performed
            return
        self.tick_elapsed = 0
        _send_event(EVENT_ENGAGE, self.event_data, player_state)
        self._save_resume_time(player_state['elapsed_seconds'])

    def _on_playback_stopped(self):
        if not self.is_event_start_sent or self.lock_events:
            return
        self.tick_elapsed = 0
        _send_event(EVENT_ENGAGE, self.event_data, self.last_player_state)
        _send_event(EVENT_STOP, self.event_data, self.last_player_state)

    def _save_resume_time(self, resume_time):
        """Save resume time in order to modify the frontend cache"""
        # Why this, the video lists are requests to the web service only once and then will be cached in order to
        # quickly get the data and speed up a lot the GUI response.
        # Watched status of a (video) list item is based on resume time, and the resume time is saved in the cache data.
        # To avoid slowing down the GUI by invalidating the cache to get new data from website service, one solution is
        # modify the cache data.
        # Altering here the cache on the fly is not possible because it is currently not shared between service-frontend
        # therefore we save the value in a Kodi property and we will modify the cache from addon frontend.
        # The choice to save the value in a Kodi property is to not continuously lock with mutex the database.
        # The callback _on_playback_stopped can not be used, because the loading of frontend happen before.
        self.window_cls.setProperty('nf_playback_resume_time', str(resume_time))


def _send_event(event_type, event_data, player_state):
    if not player_state:
        common.warn('ProgressManager: the event [{}] cannot be sent, missing player_state data', event_type)
        return
    common.send_signal(common.Signals.QUEUE_VIDEO_EVENT, {
        'event_type': event_type,
        'event_data': event_data,
        'player_state': player_state
    }, non_blocking=True)
