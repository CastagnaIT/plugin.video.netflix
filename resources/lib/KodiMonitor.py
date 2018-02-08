# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: KodiHelper
# Created on: 13.01.2017

import xbmc
import xbmcgui
import json


class KodiMonitor(xbmc.Monitor):

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
                    'properties': ['percentage']
                }

                response = self.json_rpc(method, params)

                if 'result' in response:
                    self.progress = response['result']['percentage']
                    self.kodi_helper.log(
                        msg='Current playback progress is {}%'.format(
                            self.progress)
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
        xbmc.sleep(7500)
        player_id = self.get_active_video_player()

        if self.is_netflix_play() and player_id is not None:
            self.video_info = self.get_video_info(player_id, item)
            self.progress = 0
        else:
            self.kodi_helper.log(
                msg='Playback is not from Netflix or it suddenly stopped'
            )

    def on_playback_stopped(self, ended):
        if self.video_info is not None and self.is_netflix_play():
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

        return self.json_rpc(method, params)

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
                'showtitle',
                'season',
                'episode'
            ]
        }

        resp = self.json_rpc(method, params)

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

        video_info = self.get_video_info_fallback(fallback_data)

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

    def get_video_info_fallback(self, data):
        self.kodi_helper.log(
            msg='Using fallback lookup method for video info (BAD)',
            level=xbmc.LOGWARNING
        )
        return None

    def is_netflix_play(self):
        return xbmcgui.Window(self.kodi_helper.TAGGED_WINDOW_ID).getProperty(
            self.kodi_helper.PROP_NETFLIX_PLAY
        ) is not None

    def json_rpc(self, method, params=None):
        req = {
            'jsonrpc': '2.0',
            'method': method,
            'id': 1,
            'params': params or {}
        }

        jsonrequest = json.dumps(req)
        self.kodi_helper.log(msg='Sending request: {}'.format(jsonrequest))

        jsonresponse = unicode(
            xbmc.executeJSONRPC(jsonrequest),
            'utf-8',
            errors='ignore'
        )
        self.kodi_helper.log(msg='Received response: {}'.format(jsonresponse))

        return json.loads(jsonresponse)
