# -*- coding: utf-8 -*-
"""Handle playback requests"""
from __future__ import unicode_literals

import xbmcplugin
import xbmcgui
import inputstreamhelper

import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.infolabels as infolabels
from resources.lib.services.playback import get_timeline_markers

SERVICE_URL_FORMAT = 'http://localhost:{port}'
MANIFEST_PATH_FORMAT = ('/manifest?id={videoid}'
                        '&dolby={enable_dolby}&hevc={enable_hevc}')
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
def play(videoid, needs_pin):
    """Play an episode or movie as specified by the path"""
    metadata = api.metadata(videoid)
    timeline_markers = get_timeline_markers(metadata)
    list_item = get_inputstream_listitem(videoid)
    infos, art = infolabels.add_info_for_playback(videoid, list_item)
    common.send_signal(common.Signals.PLAYBACK_INITIATED, {
        'videoid': videoid.to_dict(),
        'infos': infos,
        'art': art,
        'timeline_markers': timeline_markers})
    if videoid.mediatype == common.VideoId.EPISODE:
        integrate_upnext(videoid, infos, art, timeline_markers, metadata)
    xbmcplugin.setResolvedUrl(
        handle=common.PLUGIN_HANDLE,
        succeeded=True,
        listitem=list_item)

def get_inputstream_listitem(videoid):
    """Return a listitem that has all inputstream relevant properties set
    for playback of the given video_id"""
    service_url = SERVICE_URL_FORMAT.format(
        port=common.ADDON.getSetting('msl_service_port'))
    manifest_path = MANIFEST_PATH_FORMAT.format(
        videoid=videoid.value,
        enable_dolby=common.ADDON.getSetting('enable_dolby_sound'),
        enable_hevc=common.ADDON.getSetting('enable_hevc_profiles'))

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

def integrate_upnext(videoid, current_infos, current_art, timeline_markers,
                     metadata):
    """Determine next episode and send an AddonSignal to UpNext addon"""
    pass
