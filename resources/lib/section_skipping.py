# -*- coding: utf-8 -*-
# Author: caphm
# Module: section_skipping
# Created on: 31.07.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Skipping of video sections (recap, intro)"""
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmc
import xbmcgui

from resources.lib.KodiHelper import TAGGED_WINDOW_ID, PROP_TIMELINE_MARKERS
from resources.lib.kodi.skip import Skip


AUTOCLOSE_COMMAND = 'AlarmClock(closedialog,Dialog.Close(all,true),' \
                    '{:02d}:{:02d},silent)'
SKIPPABLE_SECTIONS = ['recap', 'credit']
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

    def on_playback_started(self):
        """
        Initialize settings and timeline markers for a new playback
        """
        self._load_settings()
        self._load_markers()

    def _load_settings(self):
        self.enabled = self.addon.getSetting('skip_credits') == 'true'
        self.auto_skip = self.addon.getSetting('auto_skip_credits') == 'true'
        self.pause_on_skip = self.addon.getSetting('pause_on_skip') == 'true'

    def _load_markers(self):
        try:
            self._markers = pickle.loads(xbmcgui.Window(
                TAGGED_WINDOW_ID).getProperty(PROP_TIMELINE_MARKERS))
        # pylint: disable=bare-except
        except:
            self.log('No timeline markers found')
            self._markers = {'creditMarkers': {}}

        self.log('Found timeline markers: {}'.format(self._markers))

    def on_tick(self, elapsed):
        """
        Check if playback has reached a skippable section and skip if this is
        the case
        """
        if self.enabled:
            for section in SKIPPABLE_SECTIONS:
                self._check_section(elapsed, section)

    def _check_section(self, elapsed, section):
        section_markers = self._markers['creditMarkers'].get(section)
        if (section_markers is not None and
                elapsed >= section_markers['start'] and
                elapsed < section_markers['end']):
            self._skip_section(section)
            del self._markers['creditMarkers'][section]

    def _skip_section(self, section):
        label = self.addon.getLocalizedString(
            30076 if section == 'credit' else 30077)
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
            player.seekTime(self._markers['creditMarkers'][section]['end'])
            xbmc.sleep(1000)  # give kodi the chance to execute
            player.pause()  # unpause playback at seek position
        else:
            player.seekTime(self._markers['creditMarkers'][section]['end'])

    def _ask_to_skip(self, section, label):
        dlg = Skip("plugin-video-netflix-Skip.xml",
                   self.addon.getAddonInfo('path'),
                   "default", "1080i",
                   section=section,
                   skip_to=self._markers['creditMarkers'][section]['end'],
                   label=label)
        # close skip intro dialog after time
        dialog_duration = (self._markers['creditMarkers'][section]['end'] -
                           self._markers['creditMarkers'][section]['start'])
        seconds = dialog_duration % 60
        minutes = (dialog_duration - seconds) / 60
        xbmc.executebuiltin(AUTOCLOSE_COMMAND.format(minutes, seconds))
        dlg.doModal()
