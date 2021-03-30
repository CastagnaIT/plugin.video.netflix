# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Common base for all playback action managers

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


class ActionManager:
    """
    Base class for managers that handle executing of specific actions during playback
    """

    SETTING_ID = None  # ID of the settings.xml property

    def __init__(self):
        self._enabled = None
        self.videoid = None
        self.videoid_parent = None
        """If the 'videoid' variable is an episode, you get the parent videoid as tvshow or else return same videoid"""

    @property
    def name(self):
        """Name of this manager"""
        return self.__class__.__name__

    @property
    def enabled(self):
        """
        Indicates whether this instance is enabled or not.
        Loads the value from Kodi settings if it has not been set.
        """
        if self._enabled is None:
            LOG.debug('Loading enabled setting from store')
            self._enabled = G.ADDON.getSettingBool(self.SETTING_ID)

        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        self._enabled = enabled

    def call_initialize(self, data):
        """
        Initialize the manager with data when the addon initiates a playback.
        """
        self.videoid = data['videoid']
        self.videoid_parent = data['videoid_parent']
        self._call_if_enabled(self.initialize, data=data)
        LOG.debug('Initialized {}: {}', self.name, self)

    def call_on_playback_started(self, player_state):
        """
        Notify that the playback has actually started and supply initial
        player state
        """
        self._call_if_enabled(self.on_playback_started, player_state=player_state)

    def call_on_tick(self, player_state):
        """
        Notify that a playback tick has passed and supply current player state
        """
        self._call_if_enabled(self.on_tick, player_state=player_state)

    def call_on_playback_seek(self, player_state):
        """
        Notify that a playback has seek
        """
        self._call_if_enabled(self.on_playback_seek, player_state=player_state)

    def call_on_playback_pause(self, player_state):
        """
        Notify that the playback is actually in pause
        """
        self._call_if_enabled(self.on_playback_pause, player_state=player_state)

    def call_on_playback_resume(self, player_state):
        """
        Notify that the playback has been resumed
        """
        self._call_if_enabled(self.on_playback_resume, player_state=player_state)

    def call_on_playback_stopped(self, player_state):
        """
        Notify that a playback has stopped
        """
        self._call_if_enabled(self.on_playback_stopped, player_state=player_state)
        self.enabled = None

    def _call_if_enabled(self, target_func, **kwargs):
        if self.enabled:
            target_func(**kwargs)

    def initialize(self, data):
        """
        Initialize the manager for a new playback.
        If preconditions are not met, this should raise an exception so the
        manager will be disabled through the current playback.
        """
        raise NotImplementedError

    def on_playback_started(self, player_state):
        """
        This method is called when video playback starts
        NOTE: If possible never use sleep delay inside this method
              otherwise it delay the execution of subsequent action managers
        """

    def on_tick(self, player_state):
        """
        This method is called every second from the service,
        but only after the 'on_playback_started' method will be called.
        NOTE: If possible never use sleep delay inside this method
              otherwise it delay the execution of subsequent action managers
        """
        raise NotImplementedError

    def on_playback_seek(self, player_state):
        pass

    def on_playback_pause(self, player_state):
        pass

    def on_playback_resume(self, player_state):
        pass

    def on_playback_stopped(self, player_state):
        pass
