# -*- coding: utf-8 -*-
"""Playback tracking and coordination of several actions during playback"""

from __future__ import unicode_literals

import json

import xbmc
import AddonSignals

import resources.lib.common as common

from .action_manager import PlaybackActionManager


class PlaybackController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """
    def __init__(self, action_managers=None):
        xbmc.Monitor.__init__(self)
        self.tracking = False
        self.active_player_id = None
        self.action_managers = action_managers or []

        AddonSignals.registerSlot(
            common.ADDON.getAddonInfo('id'), common.Signals.PLAYBACK_INITIATED,
            self.initialize_playback)

    def initialize_playback(self, data):
        """
        Callback for addon signal when this addon has initiated a playback
        """
        self.tracking = True
        try:
            self._notify_all(PlaybackActionManager.initialize, data)
        except RuntimeError as exc:
            common.log('RuntimeError: {}'.format(exc), common.LOGERROR)

    def onNotification(self, sender, method, data):
        # pylint: disable=unused-argument, invalid-name
        """
        Callback for Kodi notifications that handles and dispatches playback
        started and playback stopped events.
        """
        if self.tracking:
            try:
                if method == 'Player.OnAVStart':
                    self._on_playback_started(
                        json.loads(unicode(data, 'utf-8', errors='ignore')))
                elif method == 'Player.OnStop':
                    self._on_playback_stopped()
            except RuntimeError as exc:
                common.log('RuntimeError: {}'.format(exc), common.LOGERROR)

    def on_playback_tick(self):
        """
        Notify action managers of playback tick
        """
        if self.tracking:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_tick,
                                 player_state)

    def _on_playback_started(self, data):
        self.active_player_id = data['player']['playerid']
        self._notify_all(PlaybackActionManager.on_playback_started,
                         self._get_player_state())

    def _on_playback_stopped(self):
        self.tracking = False
        self.active_player_id = None
        self._notify_all(PlaybackActionManager.on_playback_stopped)

    def _notify_all(self, notification, data=None):
        common.log('Notifying all managers of {} (data={})'
                   .format(notification.__name__, data))
        for manager in self.action_managers:
            notify_method = getattr(manager, notification.__name__)
            if data is not None:
                notify_method(data)
            else:
                notify_method()

    def _get_player_state(self):
        try:
            player_state = common.json_rpc('Player.GetProperties', {
                'playerid': self.active_player_id,
                'properties': [
                    'audiostreams',
                    'currentaudiostream',
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

        return player_state
