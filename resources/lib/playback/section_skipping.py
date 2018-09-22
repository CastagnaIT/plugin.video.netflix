# -*- coding: utf-8 -*-
# Author: caphm
# Module: section_skipping
# Created on: 31.07.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Skipping of video sections (recap, intro)"""
import xbmc
import xbmcgui

from resources.lib.ui import xmldialogs, show_modal_dialog
from resources.lib.playback import PlaybackActionManager

SKIPPABLE_SECTIONS = {'credit': 30076, 'recap': 30077}
OFFSET_CREDITS = 'creditsOffset'


class SectionSkipper(PlaybackActionManager):
    """
    Checks if a skippable section has been reached and takes appropriate action
    """
    def __init__(self, nx_common):
        super(SectionSkipper, self).__init__(nx_common)
        self.markers = {}
        self.auto_skip = False
        self.pause_on_skip = False

    def __str__(self):
        return ('enabled={}, markers={}, auto_skip={}, pause_on_skip={}'
                .format(self.enabled, self.markers, self.auto_skip,
                        self.pause_on_skip))

    def _initialize(self, data):
        self.markers = data['timeline_markers']
        self.auto_skip = self.addon.getSetting('auto_skip_credits') == 'true'
        self.pause_on_skip = self.addon.getSetting('pause_on_skip') == 'true'

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
        self.log('Entered section {}'.format(section))
        label = self.addon.getLocalizedString(SKIPPABLE_SECTIONS[section])
        if self.auto_skip:
            self._auto_skip(section, label)
        else:
            self._ask_to_skip(section, label)

    def _auto_skip(self, section, label):
        self.log('Auto-skipping {}'.format(section))
        player = xbmc.Player()
        xbmcgui.Dialog().notification(
            'Netflix', '{}...'.format(label.encode('utf-8')),
            xbmcgui.NOTIFICATION_INFO, 5000)
        if self.pause_on_skip:
            player.pause()
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.seekTime(self.markers[section]['end'])
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.pause()  # unpause playback at seek position
        else:
            player.seekTime(self.markers[section]['end'])

    def _ask_to_skip(self, section, label):
        self.log('Asking to skip {}'.format(section))
        dialog_duration = (self.markers[section]['end'] -
                           self.markers[section]['start'])
        seconds = dialog_duration % 60
        minutes = (dialog_duration - seconds) / 60
        show_modal_dialog(xmldialogs.Skip,
                          "plugin-video-netflix-Skip.xml",
                          self.addon.getAddonInfo('path'),
                          minutes=minutes,
                          seconds=seconds,
                          skip_to=self.markers[section]['end'],
                          label=label)
