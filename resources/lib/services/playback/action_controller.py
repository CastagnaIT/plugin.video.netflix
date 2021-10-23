# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Playback tracking and coordination of several actions during playback

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import threading
import time
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.directorybuilder.dir_builder import DirectoryBuilder
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations
    from resources.lib.services.nfsession.msl.msl_handler import MSLHandler


class ActionController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the add-on
    """
    def __init__(self, nfsession: 'NFSessionOperations', msl_handler: 'MSLHandler',
                 directory_builder: 'DirectoryBuilder'):
        xbmc.Monitor.__init__(self)
        self.nfsession = nfsession
        self.msl_handler = msl_handler
        self.directory_builder = directory_builder
        self._playback_tick = None
        self._init_data = None
        self.init_count = 0
        self.is_tracking_enabled = False
        self.active_player_id = None
        self.action_managers = None
        self._last_player_state = {}
        self._is_pause_called = False
        common.register_slot(self.initialize_playback, common.Signals.PLAYBACK_INITIATED, is_signal=True)

    def initialize_playback(self, **kwargs):
        """
        Callback for AddonSignal when this add-on has initiated a playback
        """
        self._init_data = kwargs
        self._init_data['videoid_parent'] = kwargs['videoid'].derive_parent(common.VideoId.SHOW)
        self._init_data['metadata'] = self.nfsession.get_metadata(kwargs['videoid'])
        self.active_player_id = None
        self.is_tracking_enabled = True

    def _initialize_am(self):
        self._last_player_state = {}
        self._is_pause_called = False
        if not self._init_data:
            return
        self.action_managers = [
            AMPlayback(),
            AMSectionSkipper(),
            AMStreamContinuity(),
            AMVideoEvents(self.nfsession, self.msl_handler, self.directory_builder),
            AMUpNextNotifier(self.nfsession)
        ]
        self.init_count += 1
        self._notify_all(ActionManager.call_initialize, self._init_data)
        self._init_data = None

    def onNotification(self, sender, method, data):  # pylint: disable=unused-argument,too-many-branches
        """
        Callback for Kodi notifications that handles and dispatches playback events
        """
        # WARNING: Do not get playerid from 'data',
        # Because when Up Next add-on play a video while we are inside Netflix add-on and
        # not externally like Kodi library, the playerid become -1 this id does not exist
        if not self.is_tracking_enabled or not method.startswith('Player.'):
            return
        try:
            if method == 'Player.OnPlay':
                if self.init_count > 0:
                    # In this case the user has chosen to play another video while another one is in playing,
                    # then we send the missing Stop event for the current video
                    self._on_playback_stopped()
                self._initialize_am()
            elif method == 'Player.OnAVStart':
                self._on_playback_started()
                if self._playback_tick is None or not self._playback_tick.is_alive():
                    self._playback_tick = PlaybackTick(self.on_playback_tick)
                    self._playback_tick.daemon = True
                    self._playback_tick.start()
            elif method == 'Player.OnSeek':
                self._on_playback_seek(json.loads(data)['player']['time'])
            elif method == 'Player.OnPause':
                self._is_pause_called = True
                self._on_playback_pause()
            elif method == 'Player.OnResume':
                # Kodi call this event instead the "Player.OnStop" event when you try to play a video
                # while another one is in playing (also if the current video is in pause) (not happen on RPI devices)
                # Can be one of following cases:
                # - When you use ctx menu "Play From Here", this happen when click to next button
                # - When you use UpNext add-on
                # - When you play a non-Netflix video when a Netflix video is in playback in background
                # - When you play a video over another in playback (back in menus)
                if not self._is_pause_called:
                    return
                if self.init_count == 0:
                    # This should never happen, we have to avoid this event when you try to play a video
                    # while another non-netflix video is in playing
                    return
                self._is_pause_called = False
                self._on_playback_resume()
            elif method == 'Player.OnStop':
                self.is_tracking_enabled = False
                if self.active_player_id is None:
                    # if playback does not start due to an error in streams initialization
                    # OnAVStart notification will not be called, then active_player_id will be None
                    LOG.debug('ActionController: Player.OnStop event has been ignored')
                    LOG.warn('ActionController: Action managers disabled due to a playback initialization error')
                    self.action_managers = None
                    self.init_count -= 1
                    return
                self._on_playback_stopped()
        except Exception:  # pylint: disable=broad-except
            import traceback
            LOG.error(traceback.format_exc())
            self.is_tracking_enabled = False
            if self._playback_tick and self._playback_tick.is_alive():
                self._playback_tick.stop_join()
                self._playback_tick = None
            self.init_count = 0

    def on_playback_tick(self):
        """
        Notify to action managers that an second of playback has elapsed
        """
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_tick, player_state)

    def _on_playback_started(self):
        player_id = _get_player_id()
        self._notify_all(ActionManager.call_on_playback_started, self._get_player_state(player_id))
        if LOG.is_enabled and G.ADDON.getSettingBool('show_codec_info'):
            common.json_rpc('Input.ExecuteAction', {'action': 'codecinfo'})
        self.active_player_id = player_id

    def _on_playback_seek(self, time_override):
        if self.active_player_id is not None:
            player_state = self._get_player_state(time_override=time_override)
            if player_state:
                self._notify_all(ActionManager.call_on_playback_seek,
                                 player_state)

    def _on_playback_pause(self):
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_pause,
                                 player_state)

    def _on_playback_resume(self):
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_resume,
                                 player_state)

    def _on_playback_stopped(self):
        if self._playback_tick and self._playback_tick.is_alive():
            self._playback_tick.stop_join()
            self._playback_tick = None
        self.active_player_id = None
        # Immediately send the request to release the license
        common.run_threaded(True, self.msl_handler.release_license)
        self._notify_all(ActionManager.call_on_playback_stopped,
                         self._last_player_state)
        self.action_managers = None
        self.init_count -= 1

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
        msg = f'{manager.name} disabled due to exception: {exc}'
        import traceback
        LOG.error(traceback.format_exc())
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


class PlaybackTick(threading.Thread):
    """Thread to send a notification every second of playback"""
    def __init__(self, on_playback_tick):
        self._on_playback_tick = on_playback_tick
        self._stop_event = threading.Event()
        self.is_playback_paused = False
        super().__init__()

    def run(self):
        while not self._stop_event.is_set():
            self._on_playback_tick()
            if self._stop_event.wait(1):
                break  # Stop requested by stop_join

    def stop_join(self):
        self._stop_event.set()
        self.join()
