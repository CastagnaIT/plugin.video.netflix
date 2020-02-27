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

import AddonSignals
import xbmc

import resources.lib.common as common
from resources.lib.globals import g
from .action_manager import PlaybackActionManager
from .progress_manager import ProgressManager
from .resume_manager import ResumeManager
from .section_skipping import SectionSkipper
from .stream_continuity import StreamContinuityManager
from .upnext import UpNextNotifier


class PlaybackController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """
    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.tracking = False
        self.active_player_id = None
        self.action_managers = None

        AddonSignals.registerSlot(
            g.ADDON.getAddonInfo('id'), common.Signals.PLAYBACK_INITIATED, self.initialize_playback)

    def initialize_playback(self, data):
        # pylint: disable=broad-except
        """
        Callback for addon signal when this addon has initiated a playback
        """
        self.tracking = True
        self.active_player_id = None
        self.action_managers = [
            ResumeManager(),
            SectionSkipper(),
            StreamContinuityManager(),
            ProgressManager(),
            UpNextNotifier()
        ]
        self._notify_all(PlaybackActionManager.initialize, data)

    def onNotification(self, sender, method, data):
        # pylint: disable=unused-argument, invalid-name, broad-except
        """
        Callback for Kodi notifications that handles and dispatches playback
        started and playback stopped events.
        """
        if not self.tracking:
            return
        try:
            if method == 'Player.OnAVStart':
                # WARNING: Do not get playerid from 'data',
                # Because when UpNext addon play a video while we are inside Netflix addon and
                # not externally like Kodi library, the playerid become -1 this id does not exist
                self._on_playback_started()
            elif method == 'Player.OnSeek':
                self._on_playback_seek()
            elif method == 'Player.OnPause':
                self._on_playback_pause()
            elif method == 'Player.OnResume':
                self._on_playback_resume()
            elif method == 'Player.OnStop':
                self._on_playback_stopped()
        except Exception:
            import traceback
            common.error(traceback.format_exc())

    def on_service_tick(self):
        """
        Notify action managers of playback tick
        """
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_tick, player_state)

    def _on_playback_started(self):
        player_id = _get_player_id()
        self._notify_all(PlaybackActionManager.on_playback_started, self._get_player_state(player_id))
        if common.is_debug_verbose() and g.ADDON.getSettingBool('show_codec_info'):
            common.json_rpc('Input.ExecuteAction', {'action': 'codecinfo'})
        self.active_player_id = player_id

    def _on_playback_seek(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_playback_seek,
                                 player_state)

    def _on_playback_pause(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_playback_pause,
                                 player_state)

    def _on_playback_resume(self):
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_playback_resume,
                                 player_state)

    def _on_playback_stopped(self):
        self.tracking = False
        self.active_player_id = None
        # Immediately send the request to release the license
        common.send_signal(signal=common.Signals.RELEASE_LICENSE, non_blocking=True)
        self._notify_all(PlaybackActionManager.on_playback_stopped)
        self.action_managers = None

    def _notify_all(self, notification, data=None):
        # pylint: disable=broad-except
        common.debug('Notifying all managers of {} (data={})', notification.__name__, data)
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

        # Sometime may happen that when you stop playback, a player status without data is read,
        # so all dict values are returned with a default empty value,
        # then return an empty status instead of fake data
        if not player_state['audiostreams']:
            return {}

        # convert time dict to elapsed seconds
        player_state['elapsed_seconds'] = (
            player_state['time']['hours'] * 3600 +
            player_state['time']['minutes'] * 60 +
            player_state['time']['seconds'])

        return player_state


def _notify_managers(manager, notification, data):
    notify_method = getattr(manager, notification.__name__)
    try:
        if data is not None:
            notify_method(data)
        else:
            notify_method()
    except Exception as exc:
        common.error('{} disabled due to exception: {}', manager.name, exc)
        manager.enabled = False
        raise


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
