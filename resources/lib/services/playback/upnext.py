# -*- coding: utf-8 -*-

"""Relay playback info to UP NEXT addon"""
from __future__ import unicode_literals

import resources.lib.common as common

from .action_manager import PlaybackActionManager


class UpNextNotifier(PlaybackActionManager):
    """
    Triggers the AddonSignal for Up Next addon integration.
    Needed because the signal must be sent after playback started.
    """
    def __init__(self):
        super(UpNextNotifier, self).__init__()
        self.upnext_info = None

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def _initialize(self, data):
        self.upnext_info = data['upnext_info']
        self.enabled = True if self.upnext_info else False

    def _on_playback_started(self, player_state):
        # pylint: disable=unused-argument
        common.debug('Sending initialization signal to Up Next')
        common.send_signal('upnext_data', self.upnext_info)

    def _on_tick(self, player_state):
        pass
