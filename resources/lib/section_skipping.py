# -*- coding: utf-8 -*-
# Author: caphm
# Module: section_skipping
# Created on: 31.07.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Skipping of video sections (recap, intro)"""
import xbmc
import xbmcgui

from resources.lib.kodi.skip import Skip


AUTOCLOSE_COMMAND = 'AlarmClock(closedialog,Dialog.Close(all,true),' \
                    '{:02d}:{:02d},silent)'
SKIPPABLE_SECTIONS = {'credit': 30076, 'recap': 30077}
OFFSET_CREDITS = 'creditsOffset'
OFFSET_WATCHED_TO_END = 'watchedToEndOffset'


class SectionSkipper(object):
    """
    Encapsulates skipping logic. on_tick() method must periodically
    be called to execute actions.
    """
    def __init__(self, nx_common):
        self.addon = nx_common.get_addon()
        self.log = nx_common.log
        self.enabled = False
        self.auto_skip = False
        self.pause_on_skip = False
        self._markers = {}

    def initialize(self, markers):
        """
        Init markers and load settings
        """
        self._markers = markers or {}
        self.enabled = self.addon.getSetting('skip_credits') == 'true'
        self.auto_skip = self.addon.getSetting('auto_skip_credits') == 'true'
        self.pause_on_skip = self.addon.getSetting('pause_on_skip') == 'true'

    def on_tick(self, elapsed):
        """
        Check if playback has reached a skippable section and skip if this is
        the case
        """
        if self.enabled:
            for section in SKIPPABLE_SECTIONS:
                self._check_section(section, elapsed)

    def _check_section(self, section, elapsed):
        section_markers = self._markers.get(section)
        if (section_markers and
                elapsed >= section_markers['start'] and
                elapsed < section_markers['end']):
            self._skip_section(section)
            del self._markers[section]

    def _skip_section(self, section):
        label = self.addon.getLocalizedString(SKIPPABLE_SECTIONS[section])
        if self.auto_skip:
            self._auto_skip(section, label)
        else:
            self._ask_to_skip(section, label)

    def _auto_skip(self, section, label):
        player = xbmc.Player()
        xbmcgui.Dialog().notification(
            'Netflix', '{}...'.format(label), xbmcgui.NOTIFICATION_INFO, 5000)
        if self.pause_on_skip:
            player.pause()
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.seekTime(self._markers[section]['end'])
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.pause()  # unpause playback at seek position
        else:
            player.seekTime(self._markers[section]['end'])

    def _ask_to_skip(self, section, label):
        dlg = Skip("plugin-video-netflix-Skip.xml",
                   self.addon.getAddonInfo('path'),
                   "default", "1080i",
                   skip_to=self._markers[section]['end'],
                   label=label)
        # close skip intro dialog after time
        dialog_duration = (self._markers[section]['end'] -
                           self._markers[section]['start'])
        seconds = dialog_duration % 60
        minutes = (dialog_duration - seconds) / 60
        xbmc.executebuiltin(AUTOCLOSE_COMMAND.format(minutes, seconds))
        dlg.doModal()
