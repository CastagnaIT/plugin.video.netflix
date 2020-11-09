# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Playback tracking and coordination of several actions during playback

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json
import time

import xbmc

import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager
from .am_playback import AMPlayback
from .am_section_skipping import AMSectionSkipper
from .am_stream_continuity import AMStreamContinuity
from .am_upnext_notifier import AMUpNextNotifier
from .am_video_events import AMVideoEvents


class ActionController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the add-on
    """
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self._init_data = None
        self.tracking = False
        self.active_player_id = None
        self.action_managers = None
        self._last_player_state = {}
        self._is_pause_called = False
        common.register_slot(self.initialize_playback, common.Signals.PLAYBACK_INITIATED)

    def initialize_playback(self, data):
        """
        Callback for AddonSignal when this add-on has initiated a playback
        """
        # We convert the videoid only once for all action managers
        videoid = common.VideoId.from_dict(data['videoid'])
        data['videoid'] = videoid
        data['videoid_parent'] = videoid.derive_parent(common.VideoId.SHOW)
        if data['videoid_next_episode']:
            data['videoid_next_episode'] = common.VideoId.from_dict(data['videoid_next_episode'])
        self._init_data = data
        self.active_player_id = None
        # WARNING KODI EVENTS SIDE EFFECTS!
        # If action_managers is not None, means that 'Player.OnStop' event did not happen,
        # this means that you have tried to play a video while another one is currently in playing
        if self.action_managers is None:
            self._initialize_am()

    def _initialize_am(self):
        if not self._init_data:
            return
        self._last_player_state = {}
        self.action_managers = [
            AMPlayback(),
            AMSectionSkipper(),
            AMStreamContinuity(),
            AMVideoEvents(),
            AMUpNextNotifier()
        ]
        self._notify_all(ActionManager.call_initialize, self._init_data)
        self._init_data = None
        self._is_pause_called = False
        self.tracking = True

    def onNotification(self, sender, method, data):  # pylint: disable=unused-argument
        """
        Callback for Kodi notifications that handles and dispatches playback events
        """
        # WARNING: Do not get playerid from 'data',
        # Because when Up Next add-on play a video while we are inside Netflix add-on and
        # not externally like Kodi library, the playerid become -1 this id does not exist
        if not self.tracking or 'Player.' not in method:
            return
        try:
            if method == 'Player.OnAVStart':
                self._on_playback_started()
            elif method == 'Player.OnSeek':
                self._on_playback_seek(json.loads(data)['player']['time'])
            elif method == 'Player.OnPause':
                self._is_pause_called = True
                self._on_playback_pause()
            elif method == 'Player.OnResume':
                # Kodi can call this event instead the "OnStop" event when you try to play a video
                # when another one is in playing, can be one of following cases:
                # - When you use ctx menu "Play From Here", this happen when click to next button
                # - When you use UpNext add-on
                # - When you play a non-Netflix video when a Netflix video is in playback in background
                if not self._is_pause_called:
                    self._on_playback_stopped()
                    self._initialize_am()
                    return
                self._is_pause_called = False
                self._on_playback_resume()
            elif method == 'Player.OnStop':
                if self.active_player_id is None:
                    # if playback does not start due to an error in streams initialization
                    # OnAVStart notification will not be called, then active_player_id will be None
                    LOG.debug('ActionController: Player.OnStop event has been ignored')
                    LOG.warn('ActionController: Action managers disabled due to a playback initialization error')
                    self.tracking = False
                    self.action_managers = None
                    return
                self._on_playback_stopped()
        except Exception:  # pylint: disable=broad-except
            import traceback
            LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))

    def on_service_tick(self):
        """
        Notify to action managers that an interval of time has elapsed
        """
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_tick, player_state)

    def _on_playback_started(self):
        player_id = _get_player_id()
        self._notify_all(ActionManager.call_on_playback_started, self._get_player_state(player_id))
        if LOG.level == LOG.LEVEL_VERBOSE and G.ADDON.getSettingBool('show_codec_info'):
            common.json_rpc('Input.ExecuteAction', {'action': 'codecinfo'})
        self.active_player_id = player_id

    def _on_playback_seek(self, time_override):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state(time_override=time_override)
            if player_state:
                self._notify_all(ActionManager.call_on_playback_seek,
                                 player_state)

    def _on_playback_pause(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_pause,
                                 player_state)

    def _on_playback_resume(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_resume,
                                 player_state)

    def _on_playback_stopped(self):
        self.tracking = False
        self.active_player_id = None
        # Immediately send the request to release the license
        common.send_signal(signal=common.Signals.RELEASE_LICENSE, non_blocking=True)
        self._notify_all(ActionManager.call_on_playback_stopped,
                         self._last_player_state)
        self.action_managers = None

    def _notify_all(self, notification, data=None):
        LOG.debug('Notifying all action managers of {} (data={})', notification.__name__, data)
        for manager in self.action_managers:
            _notify_managers(manager, notification, data)

    def _get_player_state(self, player_id=None, time_override=None):
        try:
            player_state = common.json_rpc('Player.GetProperties', {
                'playerid': self.active_player_id if player_id is None else player_id,
                'properties': [
                    'audiostreams',
                    'currentaudiostream',
                    'currentvideostream',
                    'subtitles',
                    'currentsubtitle',
                    'subtitleenabled',
                    'percentage',
                    'time']
            })
        except IOError as exc:
            LOG.warn('_get_player_state: {}', exc)
            return {}

        # convert time dict to elapsed seconds
        player_state['elapsed_seconds'] = (player_state['time']['hours'] * 3600 +
                                           player_state['time']['minutes'] * 60 +
                                           player_state['time']['seconds'])

        if time_override:
            player_state['time'] = time_override
            elapsed_seconds = (time_override['hours'] * 3600 +
                               time_override['minutes'] * 60 +
                               time_override['seconds'])
            player_state['percentage'] = player_state['percentage'] / player_state['elapsed_seconds'] * elapsed_seconds
            player_state['elapsed_seconds'] = elapsed_seconds

        # Sometimes may happen that when you stop playback the player status is partial,
        # this is because the Kodi player stop immediately but the stop notification (from the Monitor)
        # arrives late, meanwhile in this interval of time a service tick may occur.
        if ((player_state['audiostreams'] and player_state['elapsed_seconds']) or
                (player_state['audiostreams'] and not player_state['elapsed_seconds'] and not self._last_player_state)):
            # save player state
            self._last_player_state = player_state
        else:
            # use saved player state
            player_state = self._last_player_state

        return player_state


def _notify_managers(manager, notification, data):
    notify_method = getattr(manager, notification.__name__)
    try:
        if data is not None:
            notify_method(data)
        else:
            notify_method()
    except Exception as exc:  # pylint: disable=broad-except
        manager.enabled = False
        msg = '{} disabled due to exception: {}'.format(manager.name, exc)
        import traceback
        LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
        ui.show_notification(title=common.get_local_string(30105), msg=msg)


def _get_player_id():
    try:
        retry = 10
        while retry:
            result = common.json_rpc('Player.GetActivePlayers')
            if result:
                return result[0]['playerid']
            time.sleep(0.1)
            retry -= 1
        LOG.warn('Player ID not obtained, fallback to ID 1')
    except IOError:
        LOG.error('Player ID not obtained, fallback to ID 1')
    return 1
