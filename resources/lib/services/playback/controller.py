# -*- coding: utf-8 -*-
"""Playback tracking and coordination of several actions during playback"""
from __future__ import absolute_import, division, unicode_literals

import json

import xbmc
import AddonSignals

from resources.lib.globals import g
import resources.lib.common as common

from .action_manager import PlaybackActionManager
from .resume_manager import ResumeManager
from .section_skipping import SectionSkipper
from .stream_continuity import StreamContinuityManager
from .upnext import UpNextNotifier

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


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
            g.ADDON.getAddonInfo('id'), common.Signals.PLAYBACK_INITIATED,
            self.initialize_playback)

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
                self._on_playback_started(
                    json.loads(unicode(data, 'utf-8')))
            elif method == 'Player.OnStop':
                self._on_playback_stopped()
        except Exception:
            import traceback
            common.error(traceback.format_exc())

    def on_playback_tick(self):
        """
        Notify action managers of playback tick
        """
        if self.tracking and self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(PlaybackActionManager.on_tick,
                                 player_state)

    def _on_playback_started(self, data):
        self.active_player_id = max(data['player']['playerid'], 1)
        self._notify_all(PlaybackActionManager.on_playback_started,
                         self._get_player_state())

    def _on_playback_stopped(self):
        self.tracking = False
        self.active_player_id = None
        self._notify_all(PlaybackActionManager.on_playback_stopped)
        self.action_managers = None

    def _notify_all(self, notification, data=None):
        # pylint: disable=broad-except
        common.debug('Notifying all managers of {} (data={})'
                     .format(notification.__name__, data))
        for manager in self.action_managers:
            _notify_managers(manager, notification, data)

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


def _notify_managers(manager, notification, data):
    notify_method = getattr(manager, notification.__name__)
    try:
        if data is not None:
            notify_method(data)
        else:
            notify_method()
    except Exception as exc:
        common.error('{} disabled due to exception: {}'
                     .format(manager.name, exc))
        manager.enabled = False
        raise
