# -*- coding: utf-8 -*-
"""Handle playback requests"""
from __future__ import unicode_literals

import xbmcplugin
import xbmcgui
import inputstreamhelper

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.infolabels as infolabels
import resources.lib.kodi.ui as ui
from resources.lib.services.playback import get_timeline_markers

SERVICE_URL_FORMAT = 'http://localhost:{port}'
MANIFEST_PATH_FORMAT = '/manifest?id={videoid}'
LICENSE_PATH_FORMAT = '/license?id={videoid}'

INPUTSTREAM_SERVER_CERTIFICATE = '''Cr0CCAMSEOVEukALwQ8307Y2+LVP+0MYh/HPkwUijg
IwggEKAoIBAQDm875btoWUbGqQD8eAGuBlGY+Pxo8YF1LQR+Ex0pDONMet8EHslcZRBKNQ/09RZFTP
0vrYimyYiBmk9GG+S0wB3CRITgweNE15cD33MQYyS3zpBd4z+sCJam2+jj1ZA4uijE2dxGC+gRBRnw
9WoPyw7D8RuhGSJ95OEtzg3Ho+mEsxuE5xg9LM4+Zuro/9msz2bFgJUjQUVHo5j+k4qLWu4ObugFmc
9DLIAohL58UR5k0XnvizulOHbMMxdzna9lwTw/4SALadEV/CZXBmswUtBgATDKNqjXwokohncpdsWS
auH6vfS6FXwizQoZJ9TdjSGC60rUB2t+aYDm74cIuxAgMBAAE6EHRlc3QubmV0ZmxpeC5jb20SgAOE
0y8yWw2Win6M2/bw7+aqVuQPwzS/YG5ySYvwCGQd0Dltr3hpik98WijUODUr6PxMn1ZYXOLo3eED6x
YGM7Riza8XskRdCfF8xjj7L7/THPbixyn4mULsttSmWFhexzXnSeKqQHuoKmerqu0nu39iW3pcxDV/
K7E6aaSr5ID0SCi7KRcL9BCUCz1g9c43sNj46BhMCWJSm0mx1XFDcoKZWhpj5FAgU4Q4e6f+S8eX39
nf6D6SJRb4ap7Znzn7preIvmS93xWjm75I6UBVQGo6pn4qWNCgLYlGGCQCUm5tg566j+/g5jvYZkTJ
vbiZFwtjMW5njbSRwB3W4CrKoyxw4qsJNSaZRTKAvSjTKdqVDXV/U5HK7SaBA6iJ981/aforXbd2vZ
lRXO/2S+Maa2mHULzsD+S5l4/YGpSt7PnkCe25F+nAovtl/ogZgjMeEdFyd/9YMYjOS4krYmwp3yJ7
m9ZzYCQ6I8RQN4x/yLlHG5RH/+WNLNUs6JAZ0fFdCmw='''


class InputstreamError(Exception):
    """There was an error with setting up inputstream.adaptive"""
    pass


@common.inject_video_id(path_offset=0)
@common.time_execution
def play(videoid):
    """Play an episode or movie as specified by the path"""
    common.debug('Playing {}'.format(videoid))
    metadata = api.metadata(videoid)
    common.debug('Metadata is {}'.format(metadata))

    if not _verify_pin(metadata[0].get('requiresPin', False)):
        ui.show_notification(common.get_local_string(30106))
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=False)
        return

    list_item = get_inputstream_listitem(videoid)
    infos, art = infolabels.add_info_for_playback(videoid, list_item)
    common.send_signal(common.Signals.PLAYBACK_INITIATED, {
        'videoid': videoid.to_dict(),
        'infos': infos,
        'art': art,
        'timeline_markers': get_timeline_markers(metadata[0]),
        'upnext_info': get_upnext_info(videoid, (infos, art), metadata)})
    xbmcplugin.setResolvedUrl(
        handle=g.PLUGIN_HANDLE,
        succeeded=True,
        listitem=list_item)


def get_inputstream_listitem(videoid):
    """Return a listitem that has all inputstream relevant properties set
    for playback of the given video_id"""
    service_url = SERVICE_URL_FORMAT.format(
        port=g.ADDON.getSetting('msl_service_port'))
    manifest_path = MANIFEST_PATH_FORMAT.format(videoid=videoid.value)
    list_item = xbmcgui.ListItem(path=service_url + manifest_path,
                                 offscreen=True)
    list_item.setContentLookup(False)
    list_item.setMimeType('application/dash+xml')

    is_helper = inputstreamhelper.Helper('mpd', drm='widevine')

    if not is_helper.check_inputstream():
        raise InputstreamError('inputstream.adaptive is not available')

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
    if (not pin_required or
            g.ADDON.getSetting('adultpin_enable').lower() == 'false'):
        return True
    pin = ui.ask_for_pin()
    return pin is not None and api.verify_pin(pin)


def get_upnext_info(videoid, current_episode, metadata):
    """Determine next episode and send an AddonSignal to UpNext addon"""
    try:
        next_episode_id = _find_next_episode(videoid, metadata)
    except (TypeError, KeyError):
        import traceback
        common.debug(traceback.format_exc())
        return {}

    next_episode = infolabels.add_info_for_playback(next_episode_id,
                                                    xbmcgui.ListItem())
    next_info = {
        'current_episode': upnext_info(*current_episode),
        'next_episode': upnext_info(*next_episode),
        'play_info': {'play_path': common.build_url(videoid=next_episode_id,
                                                    mode=g.MODE_PLAY)},
    }
    if 'creditsOffset' in metadata[0]:
        next_info['notification_time'] = (metadata[0]['runtime'] -
                                          metadata[0]['creditsOffset'])
    return next_info


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


def upnext_info(infos, art):
    """Create a data dict for upnext signal"""
    return {
        'episodeid': infos.get('DBID'),
        'tvshowid': infos.get('tvshowid'),
        'title': infos['title'],
        'art': {
            'tvshow.poster': art.get('tvshow.poster', ''),
            'thumb': art.get('thumb', ''),
            'tvshow.fanart': art.get('tvshow.fanart', ''),
            'tvshow.landscape': art.get('tvshow.landscape', ''),
            'tvshow.clearart': art.get('tvshow.clearart', ''),
            'tvshow.clearlogo': art.get('tvshow.clearlogo', '')
        },
        'plot': infos['plot'],
        'showtitle': infos['tvshowtitle'],
        'playcount': infos['playcount'],
        'season': infos['season'],
        'episode': infos['episode'],
        'rating': infos['rating'],
        'firstaired': infos['year']
    }
