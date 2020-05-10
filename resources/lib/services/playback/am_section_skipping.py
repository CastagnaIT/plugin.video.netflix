# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Skipping of video sections (recap, intro)

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.globals import g
from .action_manager import ActionManager
from .markers import SKIPPABLE_SECTIONS, get_timeline_markers


class AMSectionSkipper(ActionManager):
    """
    Checks if a skippable section has been reached and takes appropriate action
    """

    SETTING_ID = 'SectionSkipper_enabled'

    def __init__(self):
        super(AMSectionSkipper, self).__init__()
        self.markers = {}
        self.auto_skip = False
        self.pause_on_skip = False

    def __str__(self):
        return ('enabled={}, markers={}, auto_skip={}, pause_on_skip={}'
                .format(self.enabled, self.markers, self.auto_skip,
                        self.pause_on_skip))

    def initialize(self, data):
        self.markers = get_timeline_markers(data['metadata'][0])
        self.auto_skip = g.ADDON.getSettingBool('auto_skip_credits')
        self.pause_on_skip = g.ADDON.getSettingBool('pause_on_skip')

    def on_tick(self, player_state):
        for section in SKIPPABLE_SECTIONS:
            self._check_section(section, player_state['elapsed_seconds'])

    def _check_section(self, section, elapsed):
        if self.markers.get(section) and self.markers[section]['start'] <= elapsed <= self.markers[section]['end']:
            self._skip_section(section)
            del self.markers[section]

    def _skip_section(self, section):
        common.debug('Entered section {}', section)
        if self.auto_skip:
            self._auto_skip(section)
        else:
            self._ask_to_skip(section)

    def _auto_skip(self, section):
        common.info('Auto-skipping {}', section)
        player = xbmc.Player()
        ui.show_notification(
            common.get_local_string(SKIPPABLE_SECTIONS[section]))
        if self.pause_on_skip:
            player.pause()
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.seekTime(self.markers[section]['end'])
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.pause()  # unpause playback at seek position
        else:
            player.seekTime(self.markers[section]['end'])

    def _ask_to_skip(self, section):
        common.debug('Asking to skip {}', section)
        dialog_duration = (self.markers[section]['end'] -
                           self.markers[section]['start'])
        ui.show_modal_dialog(True,
                             ui.xmldialogs.Skip,
                             "plugin-video-netflix-Skip.xml",
                             g.ADDON.getAddonInfo('path'),
                             seconds=dialog_duration,
                             skip_to=self.markers[section]['end'],
                             label=common.get_local_string(SKIPPABLE_SECTIONS[section]))

    def on_playback_stopped(self, player_state):
        # Close any dialog remaining open
        xbmc.executebuiltin('Dialog.Close(all,true)')
