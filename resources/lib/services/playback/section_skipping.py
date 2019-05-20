# -*- coding: utf-8 -*-

"""Skipping of video sections (recap, intro)"""
from __future__ import unicode_literals

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.kodi.ui as ui
from .action_manager import PlaybackActionManager
from .markers import SKIPPABLE_SECTIONS


class SectionSkipper(PlaybackActionManager):
    """
    Checks if a skippable section has been reached and takes appropriate action
    """
    def __init__(self):
        super(SectionSkipper, self).__init__()
        self.markers = {}
        self.auto_skip = False
        self.pause_on_skip = False

    def __str__(self):
        return ('enabled={}, markers={}, auto_skip={}, pause_on_skip={}'
                .format(self.enabled, self.markers, self.auto_skip,
                        self.pause_on_skip))

    def _initialize(self, data):
        self.markers = data['timeline_markers']
        self.auto_skip = g.ADDON.getSettingBool('auto_skip_credits')
        self.pause_on_skip = g.ADDON.getSettingBool('pause_on_skip')

    def _on_tick(self, player_state):
        for section in SKIPPABLE_SECTIONS:
            self._check_section(section, player_state['elapsed_seconds'])

    def _check_section(self, section, elapsed):
        if (self.markers.get(section) and
                elapsed >= self.markers[section]['start'] and
                elapsed <= self.markers[section]['end']):
            self._skip_section(section)
            del self.markers[section]

    def _skip_section(self, section):
        common.debug('Entered section {}'.format(section))
        if self.auto_skip:
            self._auto_skip(section)
        else:
            self._ask_to_skip(section)

    def _auto_skip(self, section):
        common.info('Auto-skipping {}'.format(section))
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
        common.debug('Asking to skip {}'.format(section))
        dialog_duration = (self.markers[section]['end'] -
                           self.markers[section]['start'])
        seconds = dialog_duration % 60
        minutes = (dialog_duration - seconds) / 60
        ui.show_modal_dialog(ui.xmldialogs.Skip,
                             "plugin-video-netflix-Skip.xml",
                             g.ADDON.getAddonInfo('path'),
                             minutes=minutes,
                             seconds=seconds,
                             skip_to=self.markers[section]['end'],
                             label=common.get_local_string(
                                 SKIPPABLE_SECTIONS[section]))

    def _on_playback_stopped(self):
        # Close any dialog remaining open
        xbmc.executebuiltin('Dialog.Close(all,true)')
