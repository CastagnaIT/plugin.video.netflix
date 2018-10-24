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
        self.infos = None
        self.markers = None
        self.progress = 0
        self.elapsed = 0

    def __str__(self):
        return ('enabled={}, dbinfo={}, markers={}'
                .format(self.enabled, self.infos, self.markers))

    def _initialize(self, data):
        if 'DBID' in data:
            self.infos = data['infos']
            self.markers = data.get('timeline_markers', {})
            self.progress = 0
            self.elapsed = 0
        else:
            self.enabled = False

    def _on_playback_stopped(self):
        if self._watched_to_end():
            self._mark_as_watched()
        self.infos = None
        self.markers = None

    def _on_tick(self, player_state):
        self.progress = player_state['percentage']
        self.elapsed = player_state['elapsed_seconds']
        if self.progress > 5 and self.elapsed % 5 == 0:
            self._save_bookmark()

    def _save_bookmark(self):
        common.debug('Saving bookmark for {} at {}s'.format(self.infos,
                                                            self.elapsed))
        common.update_library_item_details(
            self.infos['DBTYPE'], self.infos['DBID'],
            {'resume': {'position': self.elapsed}})

    def _watched_to_end(self):
        if OFFSET_WATCHED_TO_END in self.markers:
            return self.elapsed >= self.markers[OFFSET_WATCHED_TO_END]
        return self.progress >= 90

    def _mark_as_watched(self):
        common.info('Marking {} as watched'.format(self.infos))
        common.update_library_item_details(
            self.infos['DBTYPE'], self.infos['DBID'],
            {'playcount': self.infos.get('playcount', 0) + 1,
             'resume': {'position': 0}})
