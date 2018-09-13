# -*- coding: utf-8 -*-
# Author: caphm
# Package: playback
# Created on: 08.02.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Playback tracking and coordination of several actions during playback"""

import json

import xbmc
import AddonSignals

from resources.lib.NetflixCommon import Signals
from resources.lib.utils import LoggingComponent


def json_rpc(method, params=None):
    """
    Executes a JSON-RPC in Kodi

    :param method: The JSON-RPC method to call
    :type method: string
    :param params: The parameters of the method call (optional)
    :type params: dict
    :returns: dict -- Method call result
    """
    request_data = {'jsonrpc': '2.0', 'method': method, 'id': 1,
                    'params': params or {}}
    request = json.dumps(request_data)
    response = json.loads(unicode(xbmc.executeJSONRPC(request), 'utf-8',
                                  errors='ignore'))
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


class PlaybackController(xbmc.Monitor, LoggingComponent):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """
    def __init__(self, nx_common):
        xbmc.Monitor.__init__(self)
        LoggingComponent.__init__(self, nx_common)
        self.tracking = False
        self.active_player_id = None
        self.action_managers = []

        AddonSignals.registerSlot(
            nx_common.addon.getAddonInfo('id'), Signals.PLAYBACK_INITIATED,
            self.initialize_playback)

    def initialize_playback(self, data):
        """
        Callback for addon signal when this addon has initiated a playback
        """
        self.tracking = True
        try:
            self._notify_all(PlaybackActionManager.initialize, data)
        except RuntimeError as exc:
            self.log('RuntimeError: {}'.format(exc), xbmc.LOGERROR)

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
                self.log('RuntimeError: {}'.format(exc), xbmc.LOGERROR)

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
        self.log('Notifying all managers of {} (data={})'
                 .format(notification.__name__, data))
        for manager in self.action_managers:
            notify_method = getattr(manager, notification.__name__)
            if data is not None:
                notify_method(data)
            else:
                notify_method()

    def _get_player_state(self):
        try:
            player_state = json_rpc('Player.GetProperties', {
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


class PlaybackActionManager(LoggingComponent):
    """
    Base class for managers that handle executing of specific actions
    during playback
    """
    def __init__(self, nx_common):
        LoggingComponent.__init__(self, nx_common)
        self.addon = nx_common.get_addon()
        self._enabled = None

    @property
    def enabled(self):
        """
        Indicates whether this instance is enabled or not.
        Loads the value from Kodi settings if it has not been set.
        """
        if self._enabled is None:
            self.log('Loading enabled setting from store')
            self._enabled = self.addon.getSettingBool(
                '{}_enabled'.format(self.__class__.__name__))

        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        self._enabled = enabled

    def initialize(self, data):
        """
        Initialize the manager with data when the addon initiates a playback.
        """
        # pylint: disable=bare-except
        try:
            self._call_if_enabled(self._initialize, data=data)
        except:
            self.enabled = False
        self.log('Initialiized ({})'.format(self))

    def on_playback_started(self, player_state):
        """
        Notify that the playback has actually started and supply initial
        player state
        """
        self._call_if_enabled(self._on_playback_started,
                              player_state=player_state)

    def on_tick(self, player_state):
        """
        Notify that a playback tick has passed and supply current player state
        """
        self._call_if_enabled(self._on_tick, player_state=player_state)

    def on_playback_stopped(self):
        """
        Notify that a playback has stopped
        """
        self._call_if_enabled(self._on_playback_stopped)
        self.enabled = None

    def _call_if_enabled(self, target_func, **kwargs):
        if self.enabled:
            target_func(**kwargs)

    def _initialize(self, data):
        """
        Initialize the manager for a new playback.
        If preconditions are not met, this should raise an exception so the
        manager will be disabled throught the current playback.
        """
        raise NotImplementedError

    def _on_playback_started(self, player_state):
        pass

    def _on_tick(self, player_state):
        raise NotImplementedError

    def _on_playback_stopped(self):
        pass
