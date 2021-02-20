# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Relay playback info to Up Next add-on

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmc
import xbmcvfs

import resources.lib.common as common
from resources.lib.common.exceptions import DBRecordNotExistError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager


class AMUpNextNotifier(ActionManager):
    """
    Prepare the data and trigger the AddonSignal for Up Next add-on integration.
    The signal must be sent after playback started.
    """

    SETTING_ID = 'UpNextNotifier_enabled'

    def __init__(self):
        super().__init__()
        self.upnext_info = None

    def __str__(self):
        return 'enabled={}'.format(self.enabled)

    def initialize(self, data):
        if (not self.videoid_next_episode or
                not data['info_data'] or
                not xbmc.getCondVisibility('System.AddonIsEnabled(service.upnext)')):
            return
        try:
            self.upnext_info = self._get_upnext_info(data['info_data'], data['metadata'], data['is_played_from_strm'])
        except DBRecordNotExistError:
            # The videoid record of the STRM episode is missing in add-on database when:
            # - The metadata have a new episode, but the STRM is not exported yet
            # - User try to play STRM files copied from another/previous add-on installation (without import them)
            # - User try to play STRM files from a shared path (like SMB) of another device (without use shared db)
            LOG.warn('Up Next add-on signal skipped, the videoid for the next episode does not exist in the database')
            self.upnext_info = None

    def on_playback_started(self, player_state):  # pylint: disable=unused-argument
        if self.upnext_info:
            LOG.debug('Sending initialization signal to Up Next Add-on')
            common.send_signal(common.Signals.UPNEXT_ADDON_INIT, self.upnext_info, non_blocking=True)

    def on_tick(self, player_state):
        pass

    def _get_upnext_info(self, info_data, metadata, is_played_from_strm):
        """Get the data to send to Up Next add-on"""
        upnext_info = {
            'current_episode': _upnext_info(self.videoid, *info_data[self.videoid.value]),
            'next_episode': _upnext_info(self.videoid_next_episode, *info_data[self.videoid_next_episode.value])
        }

        if is_played_from_strm:
            # The current video played is a STRM, then generate the path of next STRM file
            file_path = G.SHARED_DB.get_episode_filepath(
                self.videoid_next_episode.tvshowid,
                self.videoid_next_episode.seasonid,
                self.videoid_next_episode.episodeid)
            url = xbmcvfs.translatePath(file_path)
        else:
            url = common.build_url(videoid=self.videoid_next_episode,
                                   mode=G.MODE_PLAY,
                                   params={'profile_guid': G.LOCAL_DB.get_active_profile_guid()})
        upnext_info['play_url'] = url

        if 'creditsOffset' in metadata[0]:
            upnext_info['notification_offset'] = metadata[0]['creditsOffset']
        return upnext_info


def _upnext_info(videoid, infos, art):
    """Create a data dict for Up Next signal"""
    # Double check to 'rating' key, sometime can be an empty string, not accepted by Up Next add-on
    rating = infos.get('Rating', None)
    return {
        'episodeid': videoid.episodeid,
        'tvshowid': videoid.tvshowid,
        'title': infos['Title'],
        'art': {
            'tvshow.poster': art.get('poster', ''),
            'thumb': art.get('thumb', ''),
            'tvshow.fanart': art.get('fanart', ''),
            'tvshow.landscape': art.get('landscape', ''),
            'tvshow.clearart': art.get('clearart', ''),
            'tvshow.clearlogo': art.get('clearlogo', '')
        },
        'plot': infos.get('Plot', infos.get('PlotOutline', '')),
        'showtitle': infos['TVShowTitle'],
        'playcount': infos.get('PlayCount', 0),
        'runtime': infos['Duration'],
        'season': infos['Season'],
        'episode': infos['Episode'],
        'rating': rating if rating else None,
        'firstaired': infos.get('Year', '')
    }
