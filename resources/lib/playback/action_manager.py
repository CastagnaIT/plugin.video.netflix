# -*- coding: utf-8 -*-
"""Common base for all playback action managers"""
from __future__ import unicode_literals

import resources.lib.common as common

class PlaybackActionManager(object):
    """
    Base class for managers that handle executing of specific actions
    during playback
    """
    def __init__(self):
        self._enabled = None

    @property
    def enabled(self):
        """
        Indicates whether this instance is enabled or not.
        Loads the value from Kodi settings if it has not been set.
        """
        if self._enabled is None:
            common.log('Loading enabled setting from store')
            self._enabled = common.ADDON.getSettingBool(
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
        common.log('Initialiized ({})'.format(self))

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
