# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Relay playback info to Up Next add-on

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.common as common
from resources.lib.globals import g
from .action_manager import ActionManager


class AMUpNextNotifier(ActionManager):
    """
    Prepare the data and trigger the AddonSignal for Up Next add-on integration.
    The signal must be sent after playback started.
    """

    SETTING_ID = 'UpNextNotifier_enabled'

    def __init__(self):
        super(AMUpNextNotifier, self).__init__()
        self.upnext_info = None

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def initialize(self, data):
        if not data['videoid_next_episode'] or not data['info_data']:
            return
        videoid = common.VideoId.from_dict(data['videoid'])
        videoid_next_episode = common.VideoId.from_dict(data['videoid_next_episode'])
        self.upnext_info = get_upnext_info(videoid, videoid_next_episode, data['info_data'], data['metadata'],
                                           data['is_played_from_addon'])

    def on_playback_started(self, player_state):  # pylint: disable=unused-argument
        common.debug('Sending initialization signal to Up Next Add-on')
        common.send_signal(common.Signals.UPNEXT_ADDON_INIT, self.upnext_info, non_blocking=True)

    def on_tick(self, player_state):
        pass


def get_upnext_info(videoid, videoid_next_episode, info_data, metadata, is_played_from_addon):
    """Get the data to send to Up Next add-on"""
    upnext_info = {
        'current_episode': _upnext_info(videoid, *info_data[videoid.value]),
        'next_episode': _upnext_info(videoid_next_episode, *info_data[videoid_next_episode.value])
    }

    if is_played_from_addon:
        url = common.build_url(videoid=videoid_next_episode,
                               mode=g.MODE_PLAY,
                               params={'profile_guid': g.LOCAL_DB.get_active_profile_guid()})
    else:
        # Played from Kodi library get the strm file path
        file_path = g.SHARED_DB.get_episode_filepath(
            videoid_next_episode.tvshowid,
            videoid_next_episode.seasonid,
            videoid_next_episode.episodeid)
        url = g.py2_decode(xbmc.translatePath(file_path))
    upnext_info['play_info'] = {'play_path': url}

    if 'creditsOffset' in metadata[0]:
        upnext_info['notification_offset'] = metadata[0]['creditsOffset']
    return upnext_info


def _upnext_info(videoid, infos, art):
    """Create a data dict for Up Next signal"""
    # Double check to 'rating' key, sometime can be an empty string, not accepted by Up Next add-on
    rating = infos.get('rating', None)
    return {
        'episodeid': videoid.episodeid,
        'tvshowid': videoid.tvshowid,
        'title': infos['title'],
        'art': {
            'tvshow.poster': art.get('poster', ''),
            'thumb': art.get('thumb', ''),
            'tvshow.fanart': art.get('fanart', ''),
            'tvshow.landscape': art.get('landscape', ''),
            'tvshow.clearart': art.get('clearart', ''),
            'tvshow.clearlogo': art.get('clearlogo', '')
        },
        'plot': infos['plot'],
        'showtitle': infos['tvshowtitle'],
        'playcount': infos.get('playcount', 0),
        'runtime': infos['duration'],
        'season': infos['season'],
        'episode': infos['episode'],
        'rating': rating if rating else None,
        'firstaired': infos.get('year', infos.get('firstaired', ''))
    }
