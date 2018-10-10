# -*- coding: utf-8 -*-

"""Save bookmarks for library items and mark them as watched"""
from __future__ import unicode_literals

import resources.lib.common as common

from .action_manager import PlaybackActionManager
from .markers import OFFSET_WATCHED_TO_END


class BookmarkManager(PlaybackActionManager):
    """
    Saves bookmarks on each playback tick if the played item exists in the
    Kodi library and marks it as watched after playback.
    """
    def __init__(self):
        super(BookmarkManager, self).__init__()
        self.dbinfo = None
        self.markers = None
        self.progress = 0
        self.elapsed = 0

    def __str__(self):
        return ('enabled={}, dbinfo={}, markers={}'
                .format(self.enabled, self.dbinfo, self.markers))

    def _initialize(self, data):
        self.dbinfo = data['dbinfo']
        self.markers = data.get('timeline_markers', {})
        self.progress = 0
        self.elapsed = 0

    def _on_playback_stopped(self):
        if self._watched_to_end():
            self._mark_as_watched()

    def _on_tick(self, player_state):
        self.progress = player_state['percentage']
        self.elapsed = player_state['elapsed_seconds']
        if self.elapsed % 5 == 0:
            self._save_bookmark()

    def _save_bookmark(self):
        common.log('Saving bookmark for {} at {}s'.format(self.dbinfo,
                                                          self.elapsed))
        common.update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'resume': {'position': self.elapsed}})

    def _watched_to_end(self):
        return (
            (OFFSET_WATCHED_TO_END in self.markers and
             self.elapsed >= self.markers[OFFSET_WATCHED_TO_END]) or
            (OFFSET_WATCHED_TO_END not in self.markers and
             self.progress >= 90))

    def _mark_as_watched(self):
        common.log('Marking {} as watched'.format(self.dbinfo))
        common.update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'playcount': self.dbinfo.get('playcount', 0) + 1,
             'resume': {'position': 0}})
