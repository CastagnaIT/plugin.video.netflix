# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Handle playback requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc
import xbmcplugin
import xbmcgui

from resources.lib.api.exceptions import MetadataNotAvailable
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.infolabels as infolabels
import resources.lib.kodi.library as library
import resources.lib.kodi.ui as ui
from resources.lib.services.playback import get_timeline_markers

SERVICE_URL_FORMAT = 'http://localhost:{port}'
MANIFEST_PATH_FORMAT = '/manifest?id={videoid}'
LICENSE_PATH_FORMAT = '/license?id={videoid}'

INPUTSTREAM_SERVER_CERTIFICATE = (
    'Cr0CCAMSEOVEukALwQ8307Y2+LVP+0MYh/HPkwUijgIwggEKAoIBAQDm875btoWUbGqQD8eA'
    'GuBlGY+Pxo8YF1LQR+Ex0pDONMet8EHslcZRBKNQ/09RZFTP0vrYimyYiBmk9GG+S0wB3CRI'
    'TgweNE15cD33MQYyS3zpBd4z+sCJam2+jj1ZA4uijE2dxGC+gRBRnw9WoPyw7D8RuhGSJ95O'
    'Etzg3Ho+mEsxuE5xg9LM4+Zuro/9msz2bFgJUjQUVHo5j+k4qLWu4ObugFmc9DLIAohL58UR'
    '5k0XnvizulOHbMMxdzna9lwTw/4SALadEV/CZXBmswUtBgATDKNqjXwokohncpdsWSauH6vf'
    'S6FXwizQoZJ9TdjSGC60rUB2t+aYDm74cIuxAgMBAAE6EHRlc3QubmV0ZmxpeC5jb20SgAOE'
    '0y8yWw2Win6M2/bw7+aqVuQPwzS/YG5ySYvwCGQd0Dltr3hpik98WijUODUr6PxMn1ZYXOLo'
    '3eED6xYGM7Riza8XskRdCfF8xjj7L7/THPbixyn4mULsttSmWFhexzXnSeKqQHuoKmerqu0n'
    'u39iW3pcxDV/K7E6aaSr5ID0SCi7KRcL9BCUCz1g9c43sNj46BhMCWJSm0mx1XFDcoKZWhpj'
    '5FAgU4Q4e6f+S8eX39nf6D6SJRb4ap7Znzn7preIvmS93xWjm75I6UBVQGo6pn4qWNCgLYlG'
    'GCQCUm5tg566j+/g5jvYZkTJvbiZFwtjMW5njbSRwB3W4CrKoyxw4qsJNSaZRTKAvSjTKdqV'
    'DXV/U5HK7SaBA6iJ981/aforXbd2vZlRXO/2S+Maa2mHULzsD+S5l4/YGpSt7PnkCe25F+nA'
    'ovtl/ogZgjMeEdFyd/9YMYjOS4krYmwp3yJ7m9ZzYCQ6I8RQN4x/yLlHG5RH/+WNLNUs6JAZ'
    '0fFdCmw=')


class InputstreamError(Exception):
    """There was an error with setting up inputstream.adaptive"""


@common.inject_video_id(path_offset=0, pathitems_arg='videoid', inject_full_pathitems=True)
@common.time_execution(immediate=False)
def play(videoid):
    """Play an episode or movie as specified by the path"""
    common.info('Playing {}', videoid)
    is_up_next_enabled = g.ADDON.getSettingBool('UpNextNotifier_enabled')
    metadata = [{}, {}]
    try:
        metadata = api.metadata(videoid)
        common.debug('Metadata is {}', metadata)
    except MetadataNotAvailable:
        common.warn('Metadata not available for {}', videoid)

    # Parental control PIN
    pin_result = _verify_pin(metadata[0].get('requiresPin', False))
    if not pin_result:
        if pin_result is not None:
            ui.show_notification(common.get_local_string(30106), time=10000)
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)
        return

    list_item = get_inputstream_listitem(videoid)
    infos, art = infolabels.add_info_for_playback(videoid, list_item, is_up_next_enabled)

    resume_position = {}
    event_data = {}

    if g.IS_SKIN_CALL:
        # Workaround for resuming strm files from library
        resume_position = infos.get('resume', {}).get('position') \
            if g.ADDON.getSettingBool('ResumeManager_enabled') else None
        if resume_position:
            index_selected = ui.ask_for_resume(resume_position) if g.ADDON.getSettingBool('ResumeManager_dialog') else None
            if index_selected == -1:
                xbmcplugin.setResolvedUrl(handle=g.PLUGIN_HANDLE, succeeded=False, listitem=list_item)
                return
            if index_selected == 1:
                resume_position = None
    elif (g.ADDON.getSettingBool('ProgressManager_enabled') and
          videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.EPISODE]):
        # To now we have this limits:
        # - enabled only with items played inside the addon then not Kodi library, need impl. JSON-RPC lib update code
        event_data = _get_event_data(videoid)
        event_data['videoid'] = videoid.to_dict()
        event_data['is_played_by_library'] = g.IS_SKIN_CALL

    if 'raspberrypi' in common.get_system_platform():
        # OMX Player is not compatible with netflix video streams
        value = common.json_rpc('Settings.GetSettingValue', {'setting': 'videoplayer.useomxplayer'})
        if value.get('value'):
            common.json_rpc('Settings.SetSettingValue', {'setting': 'videoplayer.useomxplayer', 'value': False})

    xbmcplugin.setResolvedUrl(handle=g.PLUGIN_HANDLE, succeeded=True, listitem=list_item)

    upnext_info = get_upnext_info(videoid, (infos, art), metadata) if is_up_next_enabled else None

    g.LOCAL_DB.set_value('last_videoid_played', videoid.to_dict(), table=TABLE_SESSION)

    common.debug('Sending initialization signal')
    common.send_signal(common.Signals.PLAYBACK_INITIATED, {
        'videoid': videoid.to_dict(),
        'infos': infos,
        'art': art,
        'timeline_markers': get_timeline_markers(metadata[0]),
        'upnext_info': upnext_info,
        'resume_position': resume_position,
        'event_data': event_data}, non_blocking=True)


def get_inputstream_listitem(videoid):
    """Return a listitem that has all inputstream relevant properties set
    for playback of the given video_id"""
    service_url = SERVICE_URL_FORMAT.format(
        port=g.LOCAL_DB.get_value('msl_service_port', 8000))
    manifest_path = MANIFEST_PATH_FORMAT.format(videoid=videoid.value)
    list_item = xbmcgui.ListItem(path=service_url + manifest_path,
                                 offscreen=True)
    list_item.setContentLookup(False)
    list_item.setMimeType('application/dash+xml')

    import inputstreamhelper
    is_helper = inputstreamhelper.Helper('mpd', drm='widevine')

    if not is_helper.check_inputstream():
        raise InputstreamError(common.get_local_string(30046))

    list_item.setProperty(
        key=is_helper.inputstream_addon + '.stream_headers',
        value='user-agent=' + common.get_user_agent())
    list_item.setProperty(
        key=is_helper.inputstream_addon + '.license_type',
        value='com.widevine.alpha')
    list_item.setProperty(
        key=is_helper.inputstream_addon + '.manifest_type',
        value='mpd')
    list_item.setProperty(
        key=is_helper.inputstream_addon + '.license_key',
        value=service_url + LICENSE_PATH_FORMAT.format(videoid=videoid.value) +
        '||b{SSM}!b{SID}|')
    list_item.setProperty(
        key=is_helper.inputstream_addon + '.server_certificate',
        value=INPUTSTREAM_SERVER_CERTIFICATE)
    list_item.setProperty(
        key='inputstreamaddon',
        value=is_helper.inputstream_addon)
    return list_item


def _verify_pin(pin_required):
    if not pin_required:
        return True
    pin = ui.ask_for_pin()
    return None if not pin else api.verify_pin(pin)


def _get_event_data(videoid):
    """Get data needed to send event requests to Netflix and for resume from last position"""
    api_data = api.event_info(videoid)
    if not api_data:
        return {}
    videoid_data = api_data['videos'][videoid.value]
    common.debug('Event data: {}', videoid_data)

    event_data = {'resume_position':
                  videoid_data['bookmarkPosition'] if videoid_data['bookmarkPosition'] > -1 else None,
                  'runtime': videoid_data['runtime'],
                  'request_id': videoid_data['requestId'],
                  'watched': videoid_data['watched'],
                  'is_in_mylist': videoid_data['queue'].get('inQueue', False)}
    if videoid.mediatype == common.VideoId.EPISODE:
        event_data['track_id'] = videoid_data['trackIds']['trackId_jawEpisode']
    else:
        event_data['track_id'] = videoid_data['trackIds']['trackId_jaw']
    return event_data


@common.time_execution(immediate=False)
def get_upnext_info(videoid, current_episode, metadata):
    """Determine next episode and send an AddonSignal to UpNext addon"""
    try:
        next_episode_id = _find_next_episode(videoid, metadata)
    except (TypeError, KeyError):
        # import traceback
        # common.debug(traceback.format_exc())
        common.debug('There is no next episode, not setting up Up Next')
        return {}

    common.debug('Next episode is {}', next_episode_id)
    next_episode = infolabels.get_info_for_playback(next_episode_id, True)
    next_info = {
        'current_episode': _upnext_info(videoid, *current_episode),
        'next_episode': _upnext_info(next_episode_id, *next_episode)
    }

    if (xbmc.getInfoLabel('Container.PluginName') != g.ADDON.getAddonInfo('id') and
            library.is_in_library(next_episode_id)):
        filepath = g.SHARED_DB.get_episode_filepath(
            next_episode_id.tvshowid,
            next_episode_id.seasonid,
            next_episode_id.episodeid)
        # next_info['play_info'] = {'play_path': g.py2_decode(xbmc.translatePath(filepath))}
        next_info['play_url'] = g.py2_decode(xbmc.translatePath(filepath))
    else:
        # next_info['play_info'] = {'play_path': common.build_url(videoid=next_episode_id,
        #                                                         mode=g.MODE_PLAY)}
        next_info['play_url'] = common.build_url(videoid=next_episode_id, mode=g.MODE_PLAY)
    if 'creditsOffset' in metadata[0]:
        next_info['notification_offset'] = metadata[0]['creditsOffset']
    return next_info


@common.time_execution(immediate=False)
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


def _upnext_info(videoid, infos, art):
    """Create a data dict for upnext signal"""
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
