# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Relay playback info to Up Next add-on

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import TYPE_CHECKING

import xbmc
import xbmcvfs

import resources.lib.common as common
from resources.lib.common.exceptions import DBRecordNotExistError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class AMUpNextNotifier(ActionManager):
    """
    Prepare the data and trigger the AddonSignal for Up Next add-on integration.
    The signal must be sent after playback started.
    """

    SETTING_ID = 'UpNextNotifier_enabled'

    def __init__(self, nfsession: 'NFSessionOperations'):
        super().__init__()
        self.nfsession = nfsession
        self.upnext_info = None

    def __str__(self):
        return f'enabled={self.enabled}'

    def initialize(self, data):
        if not xbmc.getCondVisibility('System.AddonIsEnabled(service.upnext)'):
            return
        videoid_next_ep = _upnext_get_next_episode_videoid(data['videoid'], data['metadata'])
        if not videoid_next_ep:
            return
        info_next_ep = self.nfsession.get_videoid_info(videoid_next_ep)
        try:
            self.upnext_info = self._get_upnext_info(videoid_next_ep,
                                                     info_next_ep,
                                                     data['metadata'],
                                                     data['is_played_from_strm'])
        except DBRecordNotExistError:
            # The videoid record of the STRM episode is missing in add-on database when:
            # - The metadata have a new episode, but the STRM is not exported yet
            # - User try to play STRM files copied from another/previous add-on installation (without import them)
            # - User try to play STRM files from a shared path (like SMB) of another device (without use shared db)
            LOG.warn('Up Next add-on signal skipped, the videoid for the next episode does not exist in the database')

    def on_playback_started(self, player_state):  # pylint: disable=unused-argument
        if self.upnext_info:
            LOG.debug('Sending initialization signal to Up Next Add-on')
            import AddonSignals
            AddonSignals.sendSignal(
                source_id=G.ADDON_ID,
                signal='upnext_data',
                data=self.upnext_info)

    def on_tick(self, player_state):
        pass

    def _get_upnext_info(self, videoid_next_ep, info_next_ep, metadata, is_played_from_strm):
        """Get the data to send to Up Next add-on"""
        upnext_info = {
            'current_episode': _upnext_curr_ep_info(self.videoid),
            'next_episode': _upnext_next_ep_info(videoid_next_ep, *info_next_ep)
        }
        if is_played_from_strm:
            # The current video played is a STRM, then generate the path of next STRM file
            file_path = G.SHARED_DB.get_episode_filepath(
                videoid_next_ep.tvshowid, videoid_next_ep.seasonid, videoid_next_ep.episodeid)
            url = xbmcvfs.translatePath(file_path)
        else:
            url = common.build_url(videoid=videoid_next_ep,
                                   mode=G.MODE_PLAY,
                                   params={'profile_guid': G.LOCAL_DB.get_active_profile_guid()})
        upnext_info['play_url'] = url
        if 'creditsOffset' in metadata[0]:
            upnext_info['notification_offset'] = metadata[0]['creditsOffset']
        return upnext_info


def _upnext_curr_ep_info(videoid):
    """Create the Up Next data for the current episode"""
    return {
        'episodeid': videoid.episodeid,
        'tvshowid': videoid.tvshowid,
    }


def _upnext_next_ep_info(videoid, infos, art):
    """Create the Up Next data for the next episode"""
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


def _upnext_get_next_episode_videoid(videoid, metadata):
    """Determine the next episode and get the videoid"""
    try:
        videoid_next_episode = _find_next_episode(videoid, metadata)
        LOG.debug('Next episode is {}', videoid_next_episode)
        return videoid_next_episode
    except (TypeError, KeyError):
        # import traceback
        # LOG.debug(traceback.format_exc())
        LOG.debug('There is no next episode, not setting up Up Next')
        return None


def _find_next_episode(videoid, metadata):
    try:
        # Find next episode in current season
        episode = common.find(metadata[0]['seq'] + 1, 'seq',
                              metadata[1]['episodes'])
        return common.VideoId(tvshowid=videoid.tvshowid,
                              seasonid=videoid.seasonid,
                              episodeid=episode['id'])
    except (IndexError, KeyError):
        # Find first episode of next season
        next_season = common.find(metadata[1]['seq'] + 1, 'seq',
                                  metadata[2]['seasons'])
        episode = common.find(1, 'seq', next_season['episodes'])
        return common.VideoId(tvshowid=videoid.tvshowid,
                              seasonid=next_season['id'],
                              episodeid=episode['id'])
