# -*- coding: utf-8 -*-
# Author: caphm
# Package: bookmarking
# Created on: 02.08.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""Save bookmarks for library items and mark them as watched"""

from resources.lib.playback import PlaybackActionManager, json_rpc

OFFSET_WATCHED_TO_END = 'watchedToEndOffset'


def update_library_item_details(dbtype, dbid, details):
    """
    Update properties of an item in the Kodi library
    """
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)


class BookmarkManager(PlaybackActionManager):
    """
    Saves bookmarks on each playback tick if the played item exists in the
    Kodi library and marks it as watched after playback.
    """
    def __init__(self, nx_common):
        super(BookmarkManager, self).__init__(nx_common)
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
        self.log('Saving bookmark for {} at {}s'.format(self.dbinfo,
                                                        self.elapsed))
        update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'resume': {'position': self.elapsed}})

    def _watched_to_end(self):
        return (
            (OFFSET_WATCHED_TO_END in self.markers and
             self.elapsed >= self.markers[OFFSET_WATCHED_TO_END]) or
            (OFFSET_WATCHED_TO_END not in self.markers and
             self.progress >= 90))

    def _mark_as_watched(self):
        self.log('Marking {} as watched'.format(self.dbinfo))
        update_library_item_details(
            self.dbinfo['dbtype'], self.dbinfo['dbid'],
            {'playcount': self.dbinfo.get('playcount', 0) + 1,
             'resume': {'position': 0}})
