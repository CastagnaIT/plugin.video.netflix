# -*- coding: utf-8 -*-
# Author: caphm
# Module: stream_continuity
# Created on: 02.08.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""
Remember and restore audio stream / subtitle settings between individual
episodes of a tv show
"""
import xbmc

import resources.lib.ui as ui
from resources.lib.playback import PlaybackActionManager

STREAMS = {
    'audio': {
        'attribute_current': 'currentaudiostream',
        'setter': xbmc.Player.setAudioStream
    },
    'subtitle': {
        'attribute_current': 'currentsubtitle',
        'setter': xbmc.Player.setSubtitleStream
    }
}


class StreamContinuityManager(PlaybackActionManager):
    """
    Detects changes in audio / subtitle streams during playback, saves them
    for the currently playing show and restores them on subsequent episodes.
    """
    def __init__(self, nx_common):
        super(StreamContinuityManager, self).__init__(nx_common)
        self.storage = nx_common.get_storage(__name__)
        self.current_show = None
        self.current_streams = {}
        self.player = xbmc.Player()
        self.did_restore = False

    def __str__(self):
        return ('enabled={}, current_show={}'
                .format(self.enabled, self.current_show))

    def _initialize(self, data):
        self.did_restore = False
        self.current_show = data['dbinfo']['tvshowid']

    def _on_playback_started(self, player_state):
        for stype, stream in STREAMS.iteritems():
            current_player_stream = player_state[stream['attribute_current']]
            if current_player_stream:
                self.current_streams.update({
                    stype: current_player_stream['index']
                })
            self._restore_stream(stype, stream['setter'])
        self.did_restore = True

    def _on_tick(self, player_state):
        if not self.did_restore:
            self.log('Did not restore streams yet, ignoring tick')
            return

        for stype in self.current_streams:
            stream = STREAMS[stype]
            current_player_stream = player_state[stream['attribute_current']]
            if (self.current_streams[stype] !=
                    current_player_stream['index']):
                self.log('{} stream has changed from {} to {}'
                         .format(stype,
                                 self.current_streams[stype],
                                 current_player_stream))
                self._ask_to_save(
                    stype, current_player_stream['index'])
                self.current_streams[stype] = current_player_stream['index']

    def _restore_stream(self, stype, stream_setter):
        self.log('Trying to restore {}...'.format(stype))
        stored_streams = self.storage.get(self.current_show, {})
        if (stype in stored_streams and
                (stored_streams[stype] != self.current_streams[stype] or
                 stype not in self.current_streams)):
            self.current_streams[stype] = stored_streams[stype]
            getattr(self.player, stream_setter.__name__)(
                self.current_streams[stype])
            self.log('Restored {}'.format(stype))

    def _ask_to_save(self, stype, index):
        self.log('Asking to save {} stream #{}'.format(stype, index))
        stream_settings = self.storage.get(self.current_show, {})
        stream_settings[stype] = index
        ui.show_modal_dialog(ui.xmldialogs.SaveStreamSettings,
                             "plugin-video-netflix-SaveStreamSettings.xml",
                             self.addon.getAddonInfo('path'),
                             minutes=0,
                             seconds=5,
                             stream_settings=stream_settings,
                             tvshowid=self.current_show,
                             storage=self.storage)
