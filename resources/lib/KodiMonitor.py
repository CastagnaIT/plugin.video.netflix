# -*- coding: utf-8 -*-
# Author: caphm
# Module: KodiMonitor
# Created on: 08.02.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=line-too-long

"""Playback tracking & update of associated item properties in Kodi library"""

try:
    import cPickle as pickle
except ImportError:
    import pickle

from json import loads

import xbmc
import xbmcgui

from resources.lib.library_matching import guess_movie, guess_episode
from resources.lib.utils import json_rpc, noop
from resources.lib.kodi.skip import Skip

from resources.lib.KodiHelper import TAGGED_WINDOW_ID, \
    PROP_NETFLIX_PLAY, PROP_PLAYBACK_INIT, PROP_PLAYBACK_TRACKING, \
    PROP_TIMELINE_MARKERS


def _retry(func, max_tries):
    for _ in range(1, max_tries):
        xbmc.sleep(3000)
        retval = func()
        if retval is not None:
            return retval
    return None


def _get_active_video_player():
    return next((player['playerid']
                 for player in json_rpc('Player.GetActivePlayers')
                 if player['type'] == 'video'),
                None)


def _is_playback_status(status):
    return xbmcgui.Window(TAGGED_WINDOW_ID).getProperty(
        PROP_NETFLIX_PLAY) == status


def _seek(player_id, milliseconds):
    return json_rpc('Player.Seek', {
        'playerid': player_id,
        'value': {
            'hours': (milliseconds / (1000 * 60 * 60)) % 24,
            'minutes': (milliseconds / (1000 * 60)) % 60,
            'seconds': (milliseconds / 1000) % 60,
            'milliseconds': (milliseconds) % 1000
        }
    })


def is_initialized_playback():
    """
    Indicates if a playback was initiated by the netflix addon by
    checking the appropriate window property set by KodiHelper.
    """
    return _is_playback_status(PROP_PLAYBACK_INIT)


def is_netflix_playback():
    """
    Indicates if an ongoing playback is from netflix addon
    """
    return _is_playback_status(PROP_PLAYBACK_TRACKING)


class KodiMonitor(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """

    def __init__(self, nx_common, log_fn=noop):
        super(KodiMonitor, self).__init__()
        self.nx_common = nx_common
        self.video_info = None
        self.progress = 0
        self.elapsed = 0
        self.log = log_fn
        self.timeline_markers = {}

    # @log
    def on_playback_tick(self):
        """
        Updates the internal progress status of a tracked playback
        and saves bookmarks to Kodi library.
        """
        if not is_netflix_playback():
            return

        player_id = _get_active_video_player()
        try:
            progress = json_rpc('Player.GetProperties', {
                'playerid': player_id,
                'properties': ['percentage', 'time']
            })
        except IOError:
            return
        self.elapsed = (progress['time']['hours'] * 3600 +
                        progress['time']['minutes'] * 60 +
                        progress['time']['seconds'])
        self.progress = progress['percentage']

        if self.nx_common.get_addon().getSetting('skip_credits') == 'true':
            for section in ['recap', 'credit']:
                section_markers = self.timeline_markers['credit_markers'].get(
                    section)
                if (section_markers and
                        self.elapsed >= section_markers['start'] and
                        self.elapsed < section_markers['end']):
                    self._skip(section)
                    del self.timeline_markers['credit_markers'][section]

        if self.video_info:
            self._update_item_details({'resume': {'position': self.elapsed}})

    def onNotification(self, sender, method, data):
        """
        Callback for Kodi notifications that handles and dispatches playback
        started and playback stopped events.
        """
        # pylint: disable=unused-argument, invalid-name
        data = loads(unicode(data, 'utf-8', errors='ignore'))
        if method == 'Player.OnPlay':
            self._on_playback_started(data.get('item', None))
        elif method == 'Player.OnStop':
            self._on_playback_stopped()

    # @log
    def _on_playback_started(self, item):
        player_id = _retry(_get_active_video_player, 5)

        if player_id is not None and is_initialized_playback():
            self.video_info = self._get_video_info(player_id, item)
            self.progress = 0
            self.elapsed = 0
            self._grab_timeline_markers()
            xbmcgui.Window(TAGGED_WINDOW_ID).setProperty(
                PROP_NETFLIX_PLAY,
                PROP_PLAYBACK_TRACKING)
            self.log('Tracking playback of {}'.format(self.video_info))
        else:
            # Clean up remnants from improperly stopped previous playbacks.
            # Clearing the window property does not work as expected, thus
            # we overwrite it with an arbitrary value
            xbmcgui.Window(TAGGED_WINDOW_ID).setProperty(
                PROP_NETFLIX_PLAY, 'notnetflix')
            self.log('Not tracking playback: {}'
                     .format('Playback not initiated by netflix plugin'
                             if is_initialized_playback() else
                             'Unable to obtain active video player'))

    # @log
    def _on_playback_stopped(self):
        if is_netflix_playback() and self.video_info:
            if (('watched_to_end_offset' in self.timeline_markers and
                 (self.elapsed >=
                  self.timeline_markers['watched_to_end_offset'])) or
                    ('watched_to_end_offset' not in self.timeline_markers and
                     self.progress >= 90)):
                new_playcount = self.video_info.get('playcount', 0) + 1
                self._update_item_details({'playcount': new_playcount,
                                           'resume': {'position': 0}})
                action = 'marking {} as watched.'.format(self.video_info)
            else:
                action = ('not marking {} as watched, progress too little'
                          .format(self.video_info))
            self.log('Tracked playback stopped: {}'.format(action))

        xbmcgui.Window(TAGGED_WINDOW_ID).setProperty(
            PROP_NETFLIX_PLAY, 'stopped')
        xbmcgui.Window(TAGGED_WINDOW_ID).setProperty(
            PROP_TIMELINE_MARKERS, '')
        self.video_info = None
        self.progress = 0
        self.elapsed = 0
        self.timeline_markers = {}

    def _skip(self, section):
        addon = self.nx_common.get_addon()
        label_code = 30076 if section == 'credit' else 30077
        label = addon.getLocalizedString(label_code)
        if addon.getSetting('auto_skip_credits') == 'true':
            player = xbmc.Player()
            dlg = xbmcgui.Dialog()
            dlg.notification('Netflix', '{}...'.format(label),
                             xbmcgui.NOTIFICATION_INFO, 5000)
            if addon.getSetting('skip_enabled_no_pause') == 'true':
                player.seekTime(
                    self.timeline_markers['credit_markers'][section]['end'])
            else:
                player.pause()
                xbmc.sleep(1)  # give kodi the chance to execute
                player.seekTime(
                    self.timeline_markers['credit_markers'][section]['end'])
                xbmc.sleep(1)  # give kodi the chance to execute
                player.pause()  # unpause playback at seek position
        else:
            dlg = Skip("plugin-video-netflix-Skip.xml",
                       self.nx_common.get_addon().getAddonInfo('path'),
                       "default", "1080i", section=section,
                       skip_to=self.timeline_markers['credit_markers']
                       [section]['end'],
                       label=label)
            # close skip intro dialog after time
            dialog_duration = (
                self.timeline_markers['credit_markers'][section]['end'] -
                self.timeline_markers['credit_markers'][section]['start'])
            seconds = dialog_duration % 60
            minutes = (dialog_duration - seconds) / 60
            xbmc.executebuiltin(
                'AlarmClock(closedialog,Dialog.Close(all,true),{:02d}:{:02d},silent)'
                .format(minutes, seconds))
            dlg.doModal()

    # @log
    def _get_video_info(self, player_id, fallback_data):
        info = json_rpc('Player.GetItem',
                        {
                            'playerid': player_id,
                            'properties': ['playcount', 'title', 'year',
                                           'tvshowid', 'showtitle',
                                           'season', 'episode']
                        }).get('item', {})
        try:
            return {'dbtype': info['type'], 'dbid': info['id'],
                    'playcount': info.get('playcount', 0)}
        except KeyError:
            self.log('Guessing video info (fallback={})'.format(fallback_data),
                     xbmc.LOGWARNING)
            return (guess_episode(info, fallback_data) or
                    guess_movie(info, fallback_data))

    # @log
    def _update_item_details(self, properties):
        method = ('VideoLibrary.Set{}Details'
                  .format(self.video_info['dbtype'].capitalize()))
        params = {'{}id'.format(self.video_info['dbtype']):
                  self.video_info['dbid']}
        params.update(properties)
        return json_rpc(method, params)

    def _grab_timeline_markers(self):
        self.timeline_markers = {'credit_markers': {}}
        try:
            timeline_markers = pickle.loads(xbmcgui.Window(
                TAGGED_WINDOW_ID).getProperty(PROP_TIMELINE_MARKERS))
        except:
            self.nx_common.log('No timeline markers found')
            return

        if timeline_markers['end_credits_offset'] is not None:
            self.timeline_markers['end_credits_offset'] = (
                timeline_markers['end_credits_offset'])

        if timeline_markers['watched_to_end_offset'] is not None:
            self.timeline_markers['watched_to_end_offset'] = (
                timeline_markers['watched_to_end_offset'])

        if timeline_markers['credit_markers']['credit']['start'] is not None:
            self.timeline_markers['credit_markers']['credit'] = {
                'start': int(timeline_markers['credit_markers']['credit']['start']/ 1000),
                'end': int(timeline_markers['credit_markers']['credit']['end'] / 1000)
            }

        if timeline_markers['credit_markers']['recap']['start'] is not None:
            self.timeline_markers['credit_markers']['recap'] = {
                'start': int(timeline_markers['credit_markers']['recap']['start'] / 1000),
                'end': int(timeline_markers['credit_markers']['recap']['end'] / 1000)
            }

        self.nx_common.log('Found timeline markers: {}'.format(self.timeline_markers))
