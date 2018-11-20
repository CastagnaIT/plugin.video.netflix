# -*- coding: utf-8 -*-
"""Manifest format conversion"""
from __future__ import unicode_literals

import base64
import uuid
import xml.etree.ElementTree as ET

import resources.lib.common as common


def convert_to_dash(manifest):
    """Convert a Netflix style manifest to MPEGDASH manifest"""
    seconds = manifest['runtime']/1000
    init_length = seconds / 2 * 12 + 20*1000
    duration = "PT"+str(seconds)+".00S"

    root = _mpd_manifest_root(duration)
    period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)
    protection = _protection_info(manifest)

    for video_track in manifest['videoTracks']:
        _convert_video_track(
            video_track, period, init_length, protection)

    for index, audio_track in enumerate(manifest['audioTracks']):
        # Assume that first listed track is the default
        _convert_audio_track(audio_track, period, init_length,
                             default=(index == 0))

    for text_track in manifest.get('textTracks'):
        _convert_text_track(text_track, period)

    xml = ET.tostring(root, encoding='utf-8', method='xml')
    common.save_file('manifest.mpd', xml)
    return xml.replace('\n', '').replace('\r', '')


def _mpd_manifest_root(duration):
    root = ET.Element('MPD')
    root.attrib['xmlns'] = 'urn:mpeg:dash:schema:mpd:2011'
    root.attrib['xmlns:cenc'] = 'urn:mpeg:cenc:2013'
    root.attrib['mediaPresentationDuration'] = duration
    return root


def _protection_info(manifest):
    try:
        pssh = manifest['psshb64'][0]
        psshbytes = base64.standard_b64decode(pssh)
        if len(psshbytes) == 52:
            keyid = psshbytes[36:]
    except (KeyError, AttributeError, IndexError):
        pssh = None
        keyid = None
    return {'pssh': pssh, 'keyid': keyid}


def _convert_video_track(video_track, period, init_length, protection):
    adaptation_set = ET.SubElement(
        parent=period,
        tag='AdaptationSet',
        mimeType='video/mp4',
        contentType='video')
    _add_protection_info(adaptation_set, **protection)
    for downloadable in video_track['downloadables']:
        _convert_video_downloadable(
            downloadable, adaptation_set, init_length)


def _add_protection_info(adaptation_set, pssh, keyid):
    if keyid:
        protection = ET.SubElement(
            parent=adaptation_set,
            tag='ContentProtection',
            value='cenc',
            schemeIdUri='urn:mpeg:dash:mp4protection:2011').set(
                'cenc:default_KID', str(uuid.UUID(bytes=keyid)))
    protection = ET.SubElement(
        parent=adaptation_set,
        tag='ContentProtection',
        schemeIdUri='urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED')
    ET.SubElement(
        parent=protection,
        tag='widevine:license',
        robustness_level='HW_SECURE_CODECS_REQUIRED')
    if pssh:
        ET.SubElement(protection, 'cenc:pssh').text = pssh


def _convert_video_downloadable(downloadable, adaptation_set,
                                init_length):
    representation = ET.SubElement(
        parent=adaptation_set,
        tag='Representation',
        width=str(downloadable['width']),
        height=str(downloadable['height']),
        bandwidth=str(downloadable['bitrate']*1024),
        hdcp=_determine_hdcp_version(downloadable['hdcpVersions']),
        nflxContentProfile=str(downloadable['contentProfile']),
        codecs=_determine_video_codec(downloadable['contentProfile']),
        mimeType='video/mp4')
    _add_base_url(representation, downloadable)
    _add_segment_base(representation, init_length)


def _determine_hdcp_version(hdcp_versions):
    hdcp_version = '0.0'
    for hdcp in hdcp_versions:
        if hdcp != 'none':
            hdcp_version = hdcp if hdcp != 'any' else '1.0'
    return hdcp_version


def _determine_video_codec(content_profile):
    if 'hevc' in content_profile:
        return 'hevc'
    elif content_profile == 'vp9-profile0-L30-dash-cenc':
        return 'vp9.0.30'
    elif content_profile == 'vp9-profile0-L31-dash-cenc':
        return 'vp9.0.31'
    return 'h264'


def _convert_audio_track(audio_track, period, init_length, default):
    adaptation_set = ET.SubElement(
        parent=period,
        tag='AdaptationSet',
        lang=audio_track['bcp47'],
        contentType='audio',
        mimeType='audio/mp4',
        impaired=str(audio_track.get('trackType') == 'ASSISTIVE').lower(),
        original=str(audio_track.get('language', '').find('[') > 0).lower(),
        default=str(default).lower())
    for downloadable in audio_track['downloadables']:
        _convert_audio_downloadable(
            downloadable, adaptation_set, init_length,
            audio_track.get('channelsCount'))


def _convert_audio_downloadable(downloadable, adaptation_set, init_length,
                                channels_count):
    is_dplus2 = downloadable['contentProfile'] == 'ddplus-2.0-dash'
    is_dplus5 = downloadable['contentProfile'] == 'ddplus-5.1-dash'
    representation = ET.SubElement(
        parent=adaptation_set,
        tag='Representation',
        codecs='ec-3' if is_dplus2 or is_dplus5 else 'aac',
        bandwidth=str(downloadable['bitrate']*1024),
        mimeType='audio/mp4')
    ET.SubElement(
        parent=representation,
        tag='AudioChannelConfiguration',
        schemeIdUri='urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
        value=str(channels_count))
    _add_base_url(representation, downloadable)
    _add_segment_base(representation, init_length)


def _convert_text_track(text_track, period):
    if text_track.get('downloadables'):
        # Only one subtitle representation per adaptationset
        downloadable = text_track['downloadables'][0]
        is_ios8 = downloadable.get('contentProfile') == 'webvtt-lssdh-ios8'
        adaptation_set = ET.SubElement(
            parent=period,
            tag='AdaptationSet',
            lang=text_track.get('bcp47'),
            codecs=('stpp', 'wvtt')[is_ios8],
            contentType='text',
            mimeType=('application/ttml+xml', 'text/vtt')[is_ios8])
        ET.SubElement(
            parent=adaptation_set,
            tag='Role',
            schemeIdUri='urn:mpeg:dash:role:2011',
            value='forced' if text_track.get('isForced') else 'main')
        representation = ET.SubElement(
            parent=adaptation_set,
            tag='Representation',
            nflxProfile=downloadable.get('contentProfile'))
        _add_base_url(representation, downloadable)


def _add_base_url(representation, downloadable):
    ET.SubElement(
        parent=representation,
        tag='BaseURL').text = downloadable['urls'].values()[0]


def _add_segment_base(representation, init_length):
    ET.SubElement(
        parent=representation,
        tag='SegmentBase',
        indexRange='0-' + str(init_length),
        indexRangeExact='true')
