# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Playback tracking and coordination of several actions during playback

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time

import xbmc

import resources.lib.common as common
from resources.lib.globals import g
from resources.lib.kodi import ui
from .action_manager import ActionManager
from .am_video_events import AMVideoEvents
from .am_playback import AMPlayback
from .am_section_skipping import AMSectionSkipper
from .am_stream_continuity import AMStreamContinuity
from .am_upnext_notifier import AMUpNextNotifier


class ActionController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the add-on
    """
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self._init_data = None
        self.tracking = False
        self.events_workaround = False
        self.active_player_id = None
        self.action_managers = None
        self._last_player_state = {}
        common.register_slot(self.initialize_playback, common.Signals.PLAYBACK_INITIATED)

    def initialize_playback(self, data):
        """
        Callback for AddonSignal when this add-on has initiated a playback
        """
        self._init_data = data
        self.active_player_id = None
        # WARNING KODI EVENTS SIDE EFFECTS - TO CONSIDER FOR ACTION MANAGER'S BEHAVIOURS!
        # If action_managers is not None, means that 'Player.OnStop' event did not happen
        if self.action_managers is not None:
            # When you try to play a video while another one is currently in playing, Kodi have some side effects:
            # - The event "Player.OnStop" not exists. This can happen for example when using context menu
            #    "Play From Here" or with UpNext add-on, so to fix this we generate manually the stop event
            #    when Kodi send 'Player.OnPlay' event.
            # - The event "Player.OnResume" is sent without apparent good reason.
            #    When you use ctx menu "Play From Here", this happen when click to next button (can not be avoided).
            #    When you use UpNext add-on, happen a bit after, then can be avoided (by events_workaround).
            self.events_workaround = True
        else:
            self._initialize_am()

    def _initialize_am(self):
        self._last_player_state = {}
        self.action_managers = [
            AMPlayback(),
            AMSectionSkipper(),
            AMStreamContinuity(),
            AMVideoEvents(),
            AMUpNextNotifier()
        ]
        self._notify_all(ActionManager.call_initialize, self._init_data)
        self.tracking = True

    def onNotification(self, sender, method, data):  # pylint: disable=unused-argument
        """
        Callback for Kodi notifications that handles and dispatches playback events
        """
        if not self.tracking or 'Player.' not in method:
            return
        try:
            if method == 'Player.OnPlay':
                if self.events_workaround:
                    self._on_playback_stopped()
                    self._initialize_am()
            elif method == 'Player.OnAVStart':
                # WARNING: Do not get playerid from 'data',
                # Because when Up Next add-on play a video while we are inside Netflix add-on and
                # not externally like Kodi library, the playerid become -1 this id does not exist
                self._on_playback_started()
            elif method == 'Player.OnSeek':
                self._on_playback_seek()
            elif method == 'Player.OnPause':
                self._on_playback_pause()
            elif method == 'Player.OnResume':
                if self.events_workaround:
                    common.debug('ActionController: Player.OnResume event has been ignored')
                    return
                self._on_playback_resume()
            elif method == 'Player.OnStop':
                # When an error occurs before the video can be played,
                # Kodi send a Stop event and here the active_player_id is None, then ignore this event
                if self.active_player_id is None:
                    common.debug('ActionController: Player.OnStop event has been ignored')
                    common.warn('ActionController: Possible problem with video playback, action managers disabled.')
                    self.tracking = False
                    self.action_managers = None
                    self.events_workaround = False
                    return
                # It should not happen, but we avoid a possible double Stop event when using the workaround
                if not self.events_workaround:
                    self._on_playback_stopped()
        except Exception:  # pylint: disable=broad-except
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))

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
        if common.is_debug_verbose() and g.ADDON.getSettingBool('show_codec_info'):
            common.json_rpc('Input.ExecuteAction', {'action': 'codecinfo'})
        self.active_player_id = player_id

    def _on_playback_seek(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
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
        self.events_workaround = False

    def _notify_all(self, notification, data=None):
        common.debug('Notifying all action managers of {} (data={})', notification.__name__, data)
        for manager in self.action_managers:
            _notify_managers(manager, notification, data)

    def _get_player_state(self, player_id=None):
        try:
            player_state = common.json_rpc('Player.GetProperties', {
                'playerid': self.active_player_id or player_id,
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
        except IOError:
            return {}

        # convert time dict to elapsed seconds
        player_state['elapsed_seconds'] = (
            player_state['time']['hours'] * 3600 +
            player_state['time']['minutes'] * 60 +
            player_state['time']['seconds'])

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
        common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
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
        common.warn('Player ID not obtained, fallback to ID 1')
    except IOError:
        common.error('Player ID not obtained, fallback to ID 1')
    return 1
