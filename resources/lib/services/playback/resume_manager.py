# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Smeulf (original implementation module)
    Force resume when item played from the library

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.common as common

from .action_manager import PlaybackActionManager


class ResumeManager(PlaybackActionManager):
    """
    Checks if a resume action must be done
    """

    def __init__(self):  # pylint: disable=super-on-old-class
        super(ResumeManager, self).__init__()
        self.resume_position = None
        self.enabled = True

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def _initialize(self, data):
        self.resume_position = data.get('resume_position')

    def _on_playback_started(self, player_state):
        if self.resume_position:
            common.info('ResumeManager forced resume point to {}', self.resume_position)
            xbmc.Player().seekTime(int(self.resume_position))

    def _on_tick(self, player_state):
        pass
