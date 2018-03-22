# -*- coding: utf-8 -*-
# Author: caphm
# Module: KodiMonitor
# Created on: 08.02.2018
# License: MIT https://goo.gl/5bMj3H

"""Playback tracking & update of associated item properties in Kodi library"""

import json
import xbmc
import xbmcgui

from resources.lib.utils import noop, log


def _get_safe_with_fallback(item, fallback, **kwargs):
    itemkey = kwargs.get('itemkey', 'title')
    fallbackkey = kwargs.get('fallbackkey', 'title')
    default = kwargs.get('default', '')
    try:
        return item.get(itemkey) or fallback.get(fallbackkey)
    except AttributeError:
        return default


def _retry(func, max_tries):
    for _ in range(1, max_tries):
        xbmc.sleep(3000)
        retval = func()
        if retval is not None:
            return retval
    return None


def _json_rpc(method, params=None):
    request_data = {'jsonrpc': '2.0', 'method': method, 'id': 1,
                    'params': params or {}}
    request = json.dumps(request_data)
    response = json.loads(unicode(xbmc.executeJSONRPC(request), 'utf-8',
                                  errors='ignore'))
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


def _get_active_video_player():
    return next((player['playerid']
                 for player in _json_rpc('Player.GetActivePlayers')
                 if player['type'] == 'video'),
                None)


def _match_episode(item, episode, fallback_data):
    title = _get_safe_with_fallback(item, fallback_data, itemkey='label')
    try:
        matches_show = (item.get('tvshowid') == episode['tvshowid'] or
                        item.get('showtitle') == episode['showtitle'])
        matches_season = item.get('season') == episode['season']
        matches_episode = item.get('episode') == episode['episode']
        matches_explicitly = (matches_show and matches_season and
                              matches_episode)
    except AttributeError:
        matches_explicitly = False

    episode_meta = 'S%02dE%02d' % (episode['season'],
                                   episode['episode'])
    matches_meta = (episode['showtitle'] in title and
                    episode_meta in title)
    return matches_explicitly or matches_meta


def _guess_episode(item, fallback_data):
    resp = _json_rpc('VideoLibrary.GetEpisodes',
                     {'properties': ['playcount', 'tvshowid',
                                     'showtitle', 'season',
                                     'episode']})
    return next(({'dbtype': 'episode', 'dbid': episode['episodeid'],
                  'playcount': episode['playcount']}
                 for episode in resp.get('episodes', [])
                 if _match_episode(item, episode, fallback_data)),
                None)


def _match_movie(item, movie, fallback_data):
    title = _get_safe_with_fallback(item, fallback_data)
    movie_meta = '%s (%d)' % (movie['label'], movie['year'])
    return movie_meta == title or movie['label'] in title


def _guess_movie(item, fallback_data):
    params = {'properties': ['playcount', 'year', 'title']}
    try:
        params['filter'] = {'year': item['year']}
    except (TypeError, KeyError):
        pass
    resp = _json_rpc('VideoLibrary.GetMovies', params)
    return next(({'dbtype': 'movie', 'dbid': movie['movieid'],
                  'playcount': movie['playcount']}
                 for movie in resp.get('movies', [])
                 if _match_movie(item, movie, fallback_data)),
                None)


class KodiMonitor(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the addon and
    saves bookmarks and watched state for the associated items into the Kodi
    library.
    """

    PROP_PLAYBACK_TRACKING = 'tracking'

    def __init__(self, kodi_helper, log_fn=noop):
        super(KodiMonitor, self).__init__()
        self.kodi_helper = kodi_helper
        self.video_info = None
        self.progress = 0
        self.log = log_fn

    def is_initialized_playback(self):
        """
        Indicates if a playback was initiated by the netflix addon by
        checking the appropriate window property set by KodiHelper.
        """
        return self._is_playback_status(self.kodi_helper.PROP_PLAYBACK_INIT)

    def is_tracking_playback(self):
        """
        Indicates if an ongoing playback is actively tracked by an
        instance of this class.
        """
        return (self.video_info is not None and
                self._is_playback_status(self.PROP_PLAYBACK_TRACKING))

    def update_playback_progress(self):
        """
        Updates the internal progress status of a tracked playback
        and saves bookmarks to Kodi library.
        """
        if not self.is_tracking_playback():
            return

        player_id = _get_active_video_player()
        try:
            progress = _json_rpc('Player.GetProperties', {
                'playerid': player_id,
                'properties': ['percentage', 'time']
            })
        except IOError:
            return
        playtime_seconds = (progress['time']['hours'] * 3600 +
                            progress['time']['minutes'] * 60 +
                            progress['time']['seconds'])
        self._update_item_details({'resume': {'position': playtime_seconds}})
        self.progress = progress['percentage']

    def onNotification(self, sender, method, data):
        """
        Callback for Kodi notifications that handles and dispatches playback
        started and playback stopped events.
        """
        # pylint: disable=unused-argument, invalid-name
        data = json.loads(unicode(data, 'utf-8', errors='ignore'))
        if method == 'Player.OnPlay':
            self._on_playback_started(data.get('item', None))
        elif method == 'Player.OnStop':
            self._on_playback_stopped()

    @log
    def _on_playback_started(self, item):
        player_id = _retry(_get_active_video_player, 5)

        if player_id is not None and self.is_initialized_playback():
            self.video_info = self._get_video_info(player_id, item)
            self.progress = 0
            xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
                self.kodi_helper.PROP_NETFLIX_PLAY,
                self.PROP_PLAYBACK_TRACKING)
            self.log('Tracking playback of {}'.format(self.video_info))
        else:
            # Clean up remnants from improperly stopped previous playbacks.
            # Clearing the window property does not work as expected, thus
            # we overwrite it with an arbitrary value
            xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
                self.kodi_helper.PROP_NETFLIX_PLAY, 'notnetflix')
            self.log('Not tracking playback: {}'
                     .format('Playback not initiated by netflix plugin'
                             if self.is_initialized_playback() else
                             'Unable to obtain active video player'))

    @log
    def _on_playback_stopped(self):
        if self.is_tracking_playback():
            if self.progress >= 90:
                new_playcount = self.video_info.get('playcount', 0) + 1
                self._update_item_details({'playcount': new_playcount,
                                           'resume': {'position': 0}})
                action = 'marking {} as watched.'.format(self.video_info)
            else:
                action = ('not marking {} as watched, progress too little'
                          .format(self.video_info))
            self.log('Tracked playback stopped: {}'.format(action))

        xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
            self.kodi_helper.PROP_NETFLIX_PLAY, 'stopped')
        self.video_info = None
        self.progress = 0

    @log
    def _get_video_info(self, player_id, fallback_data):
        info = _json_rpc('Player.GetItem',
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
            video_info = (self._guess_episode(info, fallback_data) or
                          self._guess_movie(info, fallback_data))
            if video_info is None:
                self.log('Unable to obtain video info (fallback_data={})'
                         .format(fallback_data),
                         xbmc.LOGERROR)
            else:
                self.log('Obtained video info by guessing ({})'
                         .format(video_info),
                         xbmc.LOGWARNING)
            return video_info

    @log
    def _update_item_details(self, properties):
        method = ('VideoLibrary.Set{}Details'
                  .format(self.video_info['dbtype'].capitalize()))
        params = {'{}id'.format(self.video_info['dbtype']):
                  self.video_info['dbid']}
        params.update(properties)
        _json_rpc(method, params)

    def _is_playback_status(self, status):
        return xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).getProperty(
            self.kodi_helper.PROP_NETFLIX_PLAY) == status
