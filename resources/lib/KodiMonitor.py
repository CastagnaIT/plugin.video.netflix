# -*- coding: utf-8 -*-
# Author: caphm
# Module: KodiMonitor
# Created on: 08.02.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Playback tracking & update of associated item properties in Kodi library"""

import AddonSignals
from xbmc import Monitor, LOGERROR

from resources.lib.NetflixCommon import Signals
from resources.lib.section_skipping import (
    SectionSkipper, OFFSET_WATCHED_TO_END)
from resources.lib.utils import (
    json_rpc, get_active_video_player, update_library_item_details)


class KodiMonitor(Monitor):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """
    def __init__(self, nx_common):
        super(KodiMonitor, self).__init__()
        self.log = nx_common.log
        self.section_skipper = SectionSkipper(nx_common)
        self.tracking = False
        self.dbinfo = None
        self.progress = 0
        self.elapsed = 0
        self.active_player_id = None

        AddonSignals.registerSlot(
            nx_common.addon.getAddonInfo('id'), Signals.PLAYBACK_INITIATED,
            self.setup_playback_tracking)

    def setup_playback_tracking(self, data):
        """
        Callback for addon signal when this addon initiates a playback
        """
        self.tracking = True
        self.dbinfo = data.get('dbinfo')
        self.progress = 0
        self.elapsed = 0
        self.section_skipper.initialize(data.get('timeline_markers'))

    def onNotification(self, sender, method, data):
        # pylint: disable=unused-argument, invalid-name
        """
        Callback for Kodi notifications that handles and dispatches playback
        started and playback stopped events.
        """
        if self.tracking:
            if method == 'Player.OnAVStart':
                self._on_playback_started()
            elif method == 'Player.OnStop':
                self._on_playback_stopped()

    def on_playback_tick(self):
        """
        Update the internal progress tracking of a playback and check if
        sections need to be skipped
        """
        if self.tracking:
            self._update_progress()
            self.section_skipper.on_tick(self.elapsed)

    def _update_progress(self):
        try:
            player_props = json_rpc('Player.GetProperties', {
                'playerid': self.active_player_id,
                'properties': ['percentage', 'time']
            })
        except IOError:
            return

        self.progress = player_props['percentage']
        self.elapsed = (player_props['time']['hours'] * 3600 +
                        player_props['time']['minutes'] * 60 +
                        player_props['time']['seconds'])

        if self.dbinfo:
            self._save_bookmark()

    def _save_bookmark(self):
        update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'resume': {'position': self.elapsed}})

    def _on_playback_started(self):
        self.active_player_id = get_active_video_player()

        if self.active_player_id is None:
            self.log('Cannot obtain active player, not tracking playback',
                     level=LOGERROR)
            self._on_playback_stopped()

    def _on_playback_stopped(self):
        if self.tracking and self.dbinfo and self._watched_to_end():
            self._mark_as_watched()

        self.tracking = False
        self.dbinfo = None
        self.progress = 0
        self.elapsed = 0
        self.active_player_id = None

    def _watched_to_end(self):
        return (
            (OFFSET_WATCHED_TO_END in self.timeline_markers and
             self.elapsed >= self.timeline_markers[OFFSET_WATCHED_TO_END]) or
            (OFFSET_WATCHED_TO_END not in self.timeline_markers and
             self.progress >= 90))

    def _mark_as_watched(self):
        update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'playcount': self.dbinfo.get('playcount', 0) + 1,
             'resume': {'position': 0}})
