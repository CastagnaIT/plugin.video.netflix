# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Manifest format conversion

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import uuid
import xml.etree.ElementTree as ET

import resources.lib.common as common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.utils.esn import ForceWidevine
from resources.lib.utils.logging import LOG


def convert_to_dash(manifest):
    """Convert a Netflix style manifest to MPEG-DASH manifest"""
    from xbmcaddon import Addon
    isa_version = G.remove_ver_suffix(G.py2_decode(Addon('inputstream.adaptive').getAddonInfo('version')))

    # If a CDN server has stability problems it may cause errors with streaming,
    # we allow users to select a different CDN server
    # (should be managed by ISA but is currently is not implemented)
    cdn_index = int(G.ADDON.getSettingString('cdn_server')[-1]) - 1

    seconds = manifest['duration'] / 1000
    init_length = int(seconds / 2 * 12 + 20 * 1000)
    duration = "PT" + str(int(seconds)) + ".00S"

    root = _mpd_manifest_root(duration)
    period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)

    has_video_drm_streams = manifest['video_tracks'][0].get('hasDrmStreams', False)
    video_protection_info = _get_protection_info(manifest['video_tracks'][0]) if has_video_drm_streams else None

    for video_track in manifest['video_tracks']:
        _convert_video_track(video_track, period, init_length, video_protection_info, has_video_drm_streams, cdn_index)

    common.fix_locale_languages(manifest['audio_tracks'])
    common.fix_locale_languages(manifest['timedtexttracks'])

    has_audio_drm_streams = manifest['audio_tracks'][0].get('hasDrmStreams', False)

    default_audio_track_id = _get_default_audio_track_id(manifest)
    for audio_track in manifest['audio_tracks']:
        is_default = default_audio_track_id == audio_track['id']
        _convert_audio_track(audio_track, period, init_length, is_default, has_audio_drm_streams, cdn_index)

    for text_track in manifest['timedtexttracks']:
        if text_track['isNoneTrack']:
            continue
        is_default = _is_default_subtitle(manifest, text_track)
        _convert_text_track(text_track, period, is_default, cdn_index, isa_version)

    xml = ET.tostring(root, encoding='utf-8', method='xml')
    if LOG.level == LOG.LEVEL_VERBOSE:
        common.save_file_def('manifest.mpd', xml)
    return xml.decode('utf-8').replace('\n', '').replace('\r', '').encode('utf-8')


def _mpd_manifest_root(duration):
    root = ET.Element('MPD')
    root.attrib['xmlns'] = 'urn:mpeg:dash:schema:mpd:2011'
    root.attrib['xmlns:cenc'] = 'urn:mpeg:cenc:2013'
    root.attrib['mediaPresentationDuration'] = duration
    return root


def _add_base_url(representation, base_url):
    ET.SubElement(representation, 'BaseURL').text = base_url


def _add_segment_base(representation, init_length):
    ET.SubElement(
        representation,  # Parent
        'SegmentBase',  # Tag
        indexRange='0-' + str(init_length),
        indexRangeExact='true')


def _get_protection_info(content):
    pssh = content.get('drmHeader', {}).get('bytes')
    keyid = content.get('drmHeader', {}).get('keyId')
    return {'pssh': pssh, 'keyid': keyid}


def _add_protection_info(adaptation_set, pssh, keyid):
    if keyid:
        # Signaling presence of encrypted content
        from base64 import standard_b64decode
        ET.SubElement(
            adaptation_set,  # Parent
            'ContentProtection',  # Tag
            attrib={
                'schemeIdUri': 'urn:mpeg:dash:mp4protection:2011',
                'cenc:default_KID': str(uuid.UUID(bytes=standard_b64decode(keyid))),
                'value': 'cenc'
            })
    # Define the DRM system configuration
    protection = ET.SubElement(
        adaptation_set,  # Parent
        'ContentProtection',  # Tag
        attrib={
            'schemeIdUri': 'urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED',
            'value': 'widevine'
        })
    # Add child tags to the DRM system configuration ('widevine:license' is an ISA custom tag)
    if (G.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1'
            and G.ADDON.getSettingString('force_widevine') == ForceWidevine.DISABLED):
        # The flag HW_SECURE_CODECS_REQUIRED is mandatory for L1 devices,
        # if it is set on L3 devices ISA already remove it automatically.
        # But some L1 devices with non regular Widevine library cause issues then need to be handled
        robustness_level = 'HW_SECURE_CODECS_REQUIRED'
    else:
        robustness_level = ''
    ET.SubElement(
        protection,  # Parent
        'widevine:license',  # Tag
        robustness_level=robustness_level)
    if pssh:
        ET.SubElement(protection, 'cenc:pssh').text = pssh


def _convert_video_track(video_track, period, init_length, protection, has_drm_streams, cdn_index):
    adaptation_set = ET.SubElement(
        period,  # Parent
        'AdaptationSet',  # Tag
        mimeType='video/mp4',
        contentType='video')
    if protection:
        _add_protection_info(adaptation_set, **protection)

    limit_res = _limit_video_resolution(video_track['streams'], has_drm_streams)

    for downloadable in video_track['streams']:
        if downloadable['isDrm'] != has_drm_streams:
            continue
        if limit_res:
            if int(downloadable['res_h']) > limit_res:
                continue
        _convert_video_downloadable(downloadable, adaptation_set, init_length, cdn_index)


def _limit_video_resolution(video_tracks, has_drm_streams):
    """Limit max video resolution to user choice"""
    max_resolution = G.ADDON.getSettingString('stream_max_resolution')
    if max_resolution != '--':
        if max_resolution == 'SD 480p':
            res_limit = 480
        elif max_resolution == 'SD 576p':
            res_limit = 576
        elif max_resolution == 'HD 720p':
            res_limit = 720
        elif max_resolution == 'Full HD 1080p':
            res_limit = 1080
        elif max_resolution == 'UHD 4K':
            res_limit = 4096
        else:
            return None
        # At least an equal or lower resolution must exist otherwise disable the imposed limit
        for downloadable in video_tracks:
            if downloadable['isDrm'] != has_drm_streams:
                continue
            if int(downloadable['res_h']) <= res_limit:
                return res_limit
    return None


def _convert_video_downloadable(downloadable, adaptation_set, init_length, cdn_index):
    representation = ET.SubElement(
        adaptation_set,  # Parent
        'Representation',  # Tag
        id=str(downloadable['urls'][cdn_index]['cdn_id']),
        width=str(downloadable['res_w']),
        height=str(downloadable['res_h']),
        bandwidth=str(downloadable['bitrate'] * 1024),
        nflxContentProfile=str(downloadable['content_profile']),
        codecs=_determine_video_codec(downloadable['content_profile']),
        frameRate='{fps_rate}/{fps_scale}'.format(fps_rate=downloadable['framerate_value'],
                                                  fps_scale=downloadable['framerate_scale']),
        mimeType='video/mp4')
    _add_base_url(representation, downloadable['urls'][cdn_index]['url'])
    _add_segment_base(representation, init_length)


def _determine_video_codec(content_profile):
    if content_profile.startswith('hevc'):
        if content_profile.startswith('hevc-dv'):
            return 'dvhe'
        return 'hevc'
    if content_profile.startswith('vp9'):
        return 'vp9.0.' + content_profile[14:16]
    return 'h264'


# pylint: disable=unused-argument
def _convert_audio_track(audio_track, period, init_length, default, has_drm_streams, cdn_index):
    channels_count = {'1.0': '1', '2.0': '2', '5.1': '6', '7.1': '8'}
    impaired = 'true' if audio_track['trackType'] == 'ASSISTIVE' else 'false'
    original = 'true' if audio_track['isNative'] else 'false'
    default = 'true' if default else 'false'

    adaptation_set = ET.SubElement(
        period,  # Parent
        'AdaptationSet',  # Tag
        lang=audio_track['language'],
        contentType='audio',
        mimeType='audio/mp4',
        impaired=impaired,
        original=original,
        default=default)
    if audio_track['profile'].startswith('ddplus-atmos'):
        # Append 'ATMOS' description to the dolby atmos streams,
        # allows users to distinguish the atmos tracks in the audio stream dialog
        adaptation_set.set('name', 'ATMOS')
    for downloadable in audio_track['streams']:
        # Some audio stream has no drm
        # if downloadable['isDrm'] != has_drm_streams:
        #     continue
        _convert_audio_downloadable(downloadable, adaptation_set, init_length, channels_count[downloadable['channels']],
                                    cdn_index)


def _convert_audio_downloadable(downloadable, adaptation_set, init_length, channels_count, cdn_index):
    codec_type = 'aac'
    if 'ddplus-' in downloadable['content_profile'] or 'dd-' in downloadable['content_profile']:
        codec_type = 'ec-3'
    representation = ET.SubElement(
        adaptation_set,  # Parent
        'Representation',  # Tag
        id=str(downloadable['urls'][cdn_index]['cdn_id']),
        codecs=codec_type,
        bandwidth=str(downloadable['bitrate'] * 1024),
        mimeType='audio/mp4')
    ET.SubElement(
        representation,  # Parent
        'AudioChannelConfiguration',  # Tag
        schemeIdUri='urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
        value=channels_count)
    _add_base_url(representation, downloadable['urls'][cdn_index]['url'])
    _add_segment_base(representation, init_length)


def _convert_text_track(text_track, period, default, cdn_index, isa_version):
    # Only one subtitle representation per adaptationset
    downloadable = text_track.get('ttDownloadables')
    if not text_track:
        return

    content_profile = list(downloadable)[0]
    is_ios8 = content_profile == 'webvtt-lssdh-ios8'
    impaired = 'true' if text_track['trackType'] == 'ASSISTIVE' else 'false'
    forced = 'true' if text_track['isForcedNarrative'] else 'false'
    default = 'true' if default else 'false'

    adaptation_set = ET.SubElement(
        period,  # Parent
        'AdaptationSet',  # Tag
        lang=text_track['language'],
        codecs=('stpp', 'wvtt')[is_ios8],
        contentType='text',
        mimeType=('application/ttml+xml', 'text/vtt')[is_ios8])
    role = ET.SubElement(
        adaptation_set,  # Parent
        'Role',  # Tag
        schemeIdUri='urn:mpeg:dash:role:2011')
    # In the future version of InputStream Adaptive, you can set the stream parameters
    # in the same way as the video stream
    if common.is_less_version(isa_version, '2.4.3'):
        # To be removed when the new version is released
        if forced == 'true':
            role.set('value', 'forced')
        else:
            if default == 'true':
                role.set('value', 'main')
    else:
        adaptation_set.set('impaired', impaired)
        adaptation_set.set('forced', forced)
        adaptation_set.set('default', default)
        role.set('value', 'subtitle')

    representation = ET.SubElement(
        adaptation_set,  # Parent
        'Representation',  # Tag
        nflxProfile=content_profile)
    _add_base_url(representation, list(downloadable[content_profile]['downloadUrls'].values())[cdn_index])


def _get_default_audio_track_id(manifest):
    """Get the track id of the audio track to be set as default"""
    channels_stereo = ['1.0', '2.0']
    channels_multi = ['5.1', '7.1']
    is_prefer_stereo = G.ADDON.getSettingBool('prefer_audio_stereo')
    audio_language = common.get_kodi_audio_language()
    audio_stream = {}
    if audio_language == 'mediadefault':
        # Netflix do not have a "Media default" track then we rely on the language of current nf profile,
        # due to current Kodi locale problems this could not be accurate.
        profile_language_code = G.LOCAL_DB.get_profile_config('language')
        audio_language = profile_language_code[0:2]
    if not audio_language == 'original':
        # If set give priority to the same audio language with different country
        if G.ADDON.getSettingBool('prefer_alternative_lang'):
            # Here we have only the language code without country code, we do not know the country code to be used,
            # usually there are only two tracks with the same language and different countries,
            # then we try to find the language with the country code
            stream = next((audio_track for audio_track in manifest['audio_tracks']
                           if audio_track['language'].startswith(audio_language + '-')), None)
            if stream:
                audio_language = stream['language']
        # Try find the default track based on the Netflix profile language
        if not is_prefer_stereo:
            audio_stream = _find_audio_stream(manifest, 'language', audio_language, channels_multi)
        if not audio_stream:
            audio_stream = _find_audio_stream(manifest, 'language', audio_language, channels_stereo)
    # Try find the default track based on the original audio language
    if not audio_stream and not is_prefer_stereo:
        audio_stream = _find_audio_stream(manifest, 'isNative', True, channels_multi)
    if not audio_stream:
        audio_stream = _find_audio_stream(manifest, 'isNative', True, channels_stereo)
    return audio_stream.get('id')


def _find_audio_stream(manifest, property_name, property_value, channels_list):
    return next((audio_track for audio_track in manifest['audio_tracks']
                 if audio_track[property_name] == property_value
                 and audio_track['channels'] in channels_list
                 and not audio_track['trackType'] == 'ASSISTIVE'), {})


def _is_default_subtitle(manifest, current_text_track):
    """Check if the subtitle is to be set as default"""
    # Kodi subtitle default flag:
    #  The subtitle default flag is meant for is for where there are multiple subtitle tracks for the
    #  same language so the default flag is used to tell which track should be picked as default
    if current_text_track['isForcedNarrative'] or current_text_track['trackType'] == 'ASSISTIVE':
        return False
    # Check only regular subtitles that have other tracks in same language
    if any(text_track['language'] == current_text_track['language'] and
           (text_track['isForcedNarrative'] or text_track['trackType'] == 'ASSISTIVE')
           for text_track in manifest['timedtexttracks']):
        return True
    return False
