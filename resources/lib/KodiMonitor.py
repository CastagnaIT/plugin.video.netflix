# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: KodiHelper
# Created on: 13.01.2017

import xbmc
import xbmcgui
import json


class KodiMonitor(xbmc.Monitor):

    PROP_PLAYBACK_TRACKING = 'tracking'

    def __init__(self, kodi_helper):
        super(KodiMonitor, self).__init__()
        self.kodi_helper = kodi_helper
        self.video_info = None
        self.progress = 0

    def update_playback_progress(self):
        if self.video_info is not None:
            player_id = self.get_active_video_player()

            if player_id is not None:
                method = 'Player.GetProperties'
                params = {
                    'playerid': player_id,
                    'properties': ['percentage', 'time']
                }

                response = self.json_rpc(method, params)

                if 'result' in response:
                    self.progress = response['result']['percentage']
                    self.kodi_helper.log(
                        msg='Current playback progress is {}%'.format(
                            self.progress)
                    )
                    time = response['result']['time']
                    playtime_seconds = time['hours'] * 3600 + \
                        time['minutes'] * 60 + time['seconds']
                    if self.save_resume_bookmark(
                        playtime_seconds,
                        self.video_info['dbtype'],
                        self.video_info['dbid']
                    ):
                        self.kodi_helper.log(
                            msg='Saved bookmark at {} seconds'.format(
                                playtime_seconds)
                        )
                    else:
                        self.kodi_helper.log(
                            msg='Could not save bookmark',
                            level=xbmc.LOGWARNING
                        )
                else:
                    self.kodi_helper.log(
                        msg='Could not update playback progress'
                    )

    def onNotification(self, sender, method, data):
        data = json.loads(unicode(data, 'utf-8', errors='ignore'))

        if method == 'Player.OnPlay':
            self.on_playback_started(data.get('item', None))
        elif method == 'Player.OnStop':
            self.on_playback_stopped(data['end'])

    def on_playback_started(self, item):
        self.kodi_helper.log(
            msg='Playback started, waiting for player - item: {}'.format(item)
        )

        # wait for player to start playing video
        xbmc.sleep(3000)
        player_id = self.get_active_video_player()
        retries = 0

        while player_id is None and retries < 3:
            # wait and retry up to three times if player is very slow
            xbmc.sleep(3000)
            player_id = self.get_active_video_player()
            retries += 1

        if self.is_initialized_playback() and player_id is not None:
            self.video_info = self.get_video_info(player_id, item)
            self.progress = 0
            xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
                self.kodi_helper.PROP_NETFLIX_PLAY,
                self.PROP_PLAYBACK_TRACKING
            )
        else:
            # Clean up remnants from unproperly stopped previous playbacks
            xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
                self.kodi_helper.PROP_NETFLIX_PLAY, 'notnetflix')
            self.kodi_helper.log(
                msg='Playback is not from Netflix or it suddenly stopped'
            )

    def on_playback_stopped(self, ended):
        if self.video_info is not None and self.is_tracking_playback():
            self.kodi_helper.log(msg='Netflix playback stopped')

            if self.progress >= 90:
                self.increment_playcount(
                    self.video_info['dbtype'],
                    self.video_info['dbid'],
                    self.video_info['playcount']
                )
            else:
                self.kodi_helper.log(
                    msg='Progress insufficient, not marking as watched'
                )
        else:
            self.kodi_helper.log(msg='Playback was not from Netflix')

        xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).setProperty(
            self.kodi_helper.PROP_NETFLIX_PLAY, 'stopped')
        self.video_info = None
        self.progress = 0

    def increment_playcount(self, dbtype, dbid, playcount=0):
        new_playcount = playcount + 1

        self.kodi_helper.log(
            msg='Incrementing playcount of {} with dbid {} to {}'.format(
                dbtype, dbid, new_playcount),
            level=xbmc.LOGNOTICE
        )

        method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
        params = {
            '{}id'.format(dbtype): dbid,
            'playcount': new_playcount
        }

        return self.is_ok(self.json_rpc(method, params))

    def save_resume_bookmark(self, time, dbtype, dbid):
        method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
        params = {
            '{}id'.format(dbtype): dbid,
            'resume': {'position': time}
        }

        return self.is_ok(self.json_rpc(method, params))

    def get_active_video_player(self):
        method = 'Player.GetActivePlayers'
        resp = self.json_rpc(method)

        if 'result' in resp:
            for player in resp['result']:
                if player['type'] == 'video':
                    return player['playerid']

        return None

    def get_video_info(self, player_id, fallback_data):
        method = 'Player.GetItem'
        params = {
            'playerid': player_id,
            'properties': [
                'playcount',
                'title',
                'year',
                'tvshowid',
                'showtitle',
                'season',
                'episode'
            ]
        }

        resp = self.json_rpc(method, params)
        item = None

        if 'result' in resp and 'item' in resp['result']:
            item = resp['result']['item']

            self.kodi_helper.log(
                msg=u'Got info from player: {}'.format(item)
            )

            dbid = item.get('id', None)
            dbtype = item.get('type', None)

            if dbtype is not None and dbid is not None:
                playcount = item['playcount']
                video_info = {
                    'dbtype': dbtype,
                    'dbid': dbid,
                    'playcount': playcount
                }
                self.kodi_helper.log(
                    msg='Found video info from player: {}'.format(video_info)
                )

                if video_info['dbtype'] in ['episode', 'movie']:
                    return video_info
                else:
                    self.kodi_helper.log(msg='Not playing an episode or movie')
                    return None

        video_info = self.get_video_info_fallback(item, fallback_data)

        if video_info is not None:
            self.kodi_helper.log(
                msg='Found video info by fallback: {}'.format(video_info)
            )
        else:
            self.kodi_helper.log(
                msg='Could not get video info',
                level=xbmc.LOGERROR
            )

        return video_info

    def get_video_info_fallback(self, item, fallback_data):
        """
        Finds video info using a more inaccurate matching approach. Tries to
        use as much info returned by the player in `item` to do the lookup.
        If that fails, the most generic fallback is used by just matching
        against titles / show names and season episode numbers."""

        if (item is not None or
                (fallback_data is not None and 'title' in fallback_data)):
            self.kodi_helper.log(
                msg='Using inaccurate fallback lookup method for video info',
                level=xbmc.LOGWARNING
            )

            # Kinda weird way to prevent duplicate code, feel free to improve:
            # If there's a dbtype given, we want to use the associated lookup
            # function first, to save time. If it returns None, we still want
            # the other one to be called.
            dbtype = item.get('type', 'episode')
            if dbtype not in ['episode', 'movie']:
                # Coerce into known value
                dbtype = 'episode'
            other_dbtype = ['episode', 'movie']
            other_dbtype.remove(dbtype)
            other_dbtype = other_dbtype[0]
            self.kodi_helper.log(
                msg='Lookup priority: 1) {} 2) {}'.format(dbtype, other_dbtype)
            )
            lookup_functions = {
                'episode': self.find_episode_info,
                'movie': self.find_movie_info
            }

            return (
                lookup_functions[dbtype](item, fallback_data) or
                lookup_functions[other_dbtype](item, fallback_data)
            )
        else:
            return None

    def find_episode_info(self, item, fallback_data):
        method = 'VideoLibrary.GetEpisodes'
        params = {
            'properties': [
                'playcount',
                'tvshowid',
                'showtitle',
                'season',
                'episode'
            ]
        }

        showtitle = None
        tvshowid = None
        season = None
        episode = None
        title = None

        if item is not None:
            if 'tvshowid' in item and item['tvshowid'] > 0:
                tvshowid = item['tvshowid']
            if 'showtitle' in item and item['showtitle']:
                showtitle = item['showtitle']
            if 'season' in item and item['season'] > 0:
                season = item['season']
            if 'episode' in item and item['episode'] > 0:
                episode = item['episode']
            if 'label' in item and item['label']:
                title = item['label']
            elif fallback_data is not None:
                title = fallback_data.get('title', '')

        resp = self.json_rpc(method, params)

        if 'result' in resp and 'episodes' in resp['result']:
            for episode in resp['result']['episodes']:
                episode_meta = 'S%02dE%02d' % (
                    episode['season'],
                    episode['episode']
                )

                if ((tvshowid == episode['tvshowid'] or
                        showtitle == episode['showtitle']) and
                    season == episode['season'] and
                    episode == episode['episode'] or
                    (episode_meta in title and
                        episode['showtitle'] in title)):
                    return {
                        'dbtype': 'episode',
                        'dbid': episode['episodeid'],
                        'playcount': episode['playcount']
                    }
        else:
            return None

    def find_movie_info(self, item, fallback_data):
        method = 'VideoLibrary.GetMovies'
        params = {
            'properties': ['playcount', 'year', 'title']
        }

        title = ''

        if item is not None:
            title = item.get(
                'title',
                fallback_data.get(
                    'title',
                    ''
                ) if fallback_data is not None else ''
            )

            if 'year' in item:
                params['filter'] = {'year': item['year']}

        resp = self.json_rpc(method, params)

        if 'result' in resp and 'movies' in resp['result']:
            for movie in resp['result']['movies']:
                movie_meta = '%s (%d)' % (movie['label'], movie['year'])
                self.kodi_helper.log(u'Matching {}'.format(movie_meta))
                if movie_meta == title or movie['label'] in title:
                    return {
                        'dbtype': 'movie',
                        'dbid': movie['movieid'],
                        'playcount': movie['playcount']
                    }
        else:
            return None

    def is_initialized_playback(self):
        return self.is_playback_status(self.kodi_helper.PROP_PLAYBACK_INIT)

    def is_tracking_playback(self):
        return self.is_playback_status(self.PROP_PLAYBACK_TRACKING)

    def is_playback_status(self, status):
        return xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).getProperty(
            self.kodi_helper.PROP_NETFLIX_PLAY
        ) == status

    def json_rpc(self, method, params=None):
        req = {
            'jsonrpc': '2.0',
            'method': method,
            'id': 1,
            'params': params or {}
        }

        jsonrequest = json.dumps(req)
        self.kodi_helper.log(msg=u'Sending request: {}'.format(jsonrequest))

        jsonresponse = unicode(
            xbmc.executeJSONRPC(jsonrequest),
            'utf-8',
            errors='ignore'
        )
        self.kodi_helper.log(msg=u'Received response: {}'.format(jsonresponse))

        return json.loads(jsonresponse)

    def is_ok(self, jsonrpc_response):
        return (
            'result' in jsonrpc_response and
            jsonrpc_response['result'] == 'OK'
        )
