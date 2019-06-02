# -*- coding: utf-8 -*-
"""Manifest format conversion"""
from __future__ import unicode_literals
from resources.lib.globals import g
import re
import base64
import uuid
import xbmc
import xml.etree.ElementTree as ET

import resources.lib.common as common


def convert_to_dash(manifest):
    """Convert a Netflix style manifest to MPEGDASH manifest"""
    seconds = manifest['duration'] / 1000
    init_length = seconds / 2 * 12 + 20 * 1000
    duration = "PT" + str(seconds) + ".00S"

    root = _mpd_manifest_root(duration)
    period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)
    protection = _protection_info(manifest)

    for video_track in manifest['video_tracks']:
        _convert_video_track(
            video_track, period, init_length, protection)

    _fix_locale_languages(manifest['audio_tracks'])
    _fix_locale_languages(manifest['timedtexttracks'])

    default_audio_language_index = _get_default_audio_language(manifest)
    for index, audio_track in enumerate(manifest['audio_tracks']):
        _convert_audio_track(audio_track, period, init_length,
                             default=(index == default_audio_language_index))

    default_subtitle_language_index = _get_default_subtitle_language(manifest)
    for index, text_track in enumerate(manifest['timedtexttracks']):
        if text_track['isNoneTrack']:
            continue
        _convert_text_track(text_track, period,
                            default=(index == default_subtitle_language_index))

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
        pssh = None
        keyid = None
        if 'drmHeader' in manifest:
            pssh = manifest['drmHeader']['bytes']
            keyid = manifest['drmHeader']['keyId']
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
    for downloadable in video_track['streams']:
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
        id=str(downloadable['urls'][0]['cdn_id']),
        width=str(downloadable['res_w']),
        height=str(downloadable['res_h']),
        bandwidth=str(downloadable['bitrate'] * 1024),
        nflxContentProfile=str(downloadable['content_profile']),
        codecs=_determine_video_codec(downloadable['content_profile']),
        frameRate=str(downloadable['framerate_value'] / downloadable['framerate_scale']),
        mimeType='video/mp4')
    _add_base_url(representation, downloadable['urls'][0]['url'])
    _add_segment_base(representation, init_length)


def _determine_video_codec(content_profile):
    if 'hevc' in content_profile:
        return 'hevc'
    elif 'vp9' in content_profile:
        return 'vp9.0.' + content_profile[14:16]
    return 'h264'


def _convert_audio_track(audio_track, period, init_length, default):
    channels_count = {'1.0': '1', '2.0': '2', '5.1': '6', '7.1': '8'}
    impaired = 'true' if audio_track['trackType'] == 'ASSISTIVE' else 'false'
    original = 'true' if audio_track['isNative'] else 'false'
    default = 'true' if default else 'false'

    adaptation_set = ET.SubElement(
        parent=period,
        tag='AdaptationSet',
        lang=audio_track['language'],
        contentType='audio',
        mimeType='audio/mp4',
        impaired=impaired,
        original=original,
        default=default)
    for downloadable in audio_track['streams']:
        _convert_audio_downloadable(
            downloadable, adaptation_set, init_length,
            channels_count[downloadable['channels']])


def _convert_audio_downloadable(downloadable, adaptation_set, init_length,
                                channels_count):
    codec_type = 'aac'
    if 'ddplus-' in downloadable['content_profile'] or 'dd-' in downloadable['content_profile']:
        codec_type = 'ec-3'
    representation = ET.SubElement(
        parent=adaptation_set,
        tag='Representation',
        id=str(downloadable['urls'][0]['cdn_id']),
        codecs=codec_type,
        bandwidth=str(downloadable['bitrate'] * 1024),
        mimeType='audio/mp4')
    ET.SubElement(
        parent=representation,
        tag='AudioChannelConfiguration',
        schemeIdUri='urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
        value=channels_count)
    _add_base_url(representation, downloadable['urls'][0]['url'])
    _add_segment_base(representation, init_length)


def _convert_text_track(text_track, period, default):
    if text_track.get('ttDownloadables'):
        # Only one subtitle representation per adaptationset
        downloadable = text_track['ttDownloadables']
        # common.save_file('downloadable.log', str(downloadable))

        content_profile = downloadable.keys()[0]
        is_ios8 = content_profile == 'webvtt-lssdh-ios8'

        adaptation_set = ET.SubElement(
            parent=period,
            tag='AdaptationSet',
            lang=text_track.get('language'),
            codecs=('stpp', 'wvtt')[is_ios8],
            contentType='text',
            mimeType=('application/ttml+xml', 'text/vtt')[is_ios8])
        role = ET.SubElement(
            parent=adaptation_set,
            tag='Role',
            schemeIdUri='urn:mpeg:dash:role:2011')
        if text_track.get('isForcedNarrative'):
            role.set("value", "forced")
        else:
            if default:
                role.set("value", "main")

        representation = ET.SubElement(
            parent=adaptation_set,
            tag='Representation',
            nflxProfile=content_profile)
        _add_base_url(representation, downloadable[content_profile]['downloadUrls'].values()[0])


def _add_base_url(representation, base_url):
    ET.SubElement(
        parent=representation,
        tag='BaseURL').text = base_url


def _add_segment_base(representation, init_length):
    ET.SubElement(
        parent=representation,
        tag='SegmentBase',
        indexRange='0-' + str(init_length),
        indexRangeExact='true')


def _get_default_audio_language(manifest):
    channelList = {'1.0': '1', '2.0': '2'}
    channelListDolby = {'5.1': '6', '7.1': '8'}

    # Read language in kodi settings
    audio_language = common.json_rpc('Settings.GetSettingValue', {'setting': 'locale.audiolanguage'})
    audio_language = xbmc.convertLanguage(audio_language['value'].encode('utf-8'), xbmc.ISO_639_1)
    audio_language = audio_language if audio_language else xbmc.getLanguage(xbmc.ISO_639_1, False)
    audio_language = audio_language if audio_language else 'en'

    # Try to find the preferred language with the right channels
    if g.ADDON.getSettingBool('enable_dolby_sound'):
        for index, audio_track in enumerate(manifest['audio_tracks']):
            if audio_track['language'] == audio_language and audio_track['channels'] in channelListDolby:
                return index
    # If dolby audio track not exists check other channels list
    for index, audio_track in enumerate(manifest['audio_tracks']):
        if audio_track['language'] == audio_language and audio_track['channels'] in channelList:
            return index

    # If there is no matches to preferred language, try to sets the original language track as default
        # Check if the dolby audio track in selected language exists
    if g.ADDON.getSettingBool('enable_dolby_sound'):
        for index, audio_track in enumerate(manifest['audio_tracks']):
            if audio_track['isNative'] and audio_track['channels'] in channelListDolby:
                return index
    # If dolby audio track not exists check other channels list
    for index, audio_track in enumerate(manifest['audio_tracks']):
        if audio_track['isNative'] and audio_track['channels'] in channelList:
            return index
    return 0


def _get_default_subtitle_language(manifest):
    subtitle_language = common.json_rpc('Settings.GetSettingValue', {'setting': 'locale.subtitlelanguage'})
    if subtitle_language['value'] == 'forced_only':
        # Leave the selection of forced subtitles to kodi
        return -1
    else:
        subtitle_language = xbmc.convertLanguage(subtitle_language['value'].encode('utf-8'), xbmc.ISO_639_1)
        subtitle_language = subtitle_language if subtitle_language else xbmc.getLanguage(xbmc.ISO_639_1, False)
        subtitle_language = subtitle_language if subtitle_language else 'en'

        for index, text_track in enumerate(manifest['timedtexttracks']):
            if text_track['isNoneTrack']:
                continue
            if not text_track.get('isForcedNarrative') and text_track['language'] == subtitle_language:
                return index
        return -1


def _fix_locale_languages(data_list):
    """Replace locale code, Kodi does not understand the country code"""
    # Get all the ISO 639-1 codes (without country)
    locale_list_nocountry = []
    for item in data_list:
        if item.get('isNoneTrack',False):
            continue
        if len(item['language']) == 2 and not item['language'] in locale_list_nocountry:
            locale_list_nocountry.append(item['language'])
    # Replace the locale languages with country with a new one
    for item in data_list:
        if item.get('isNoneTrack',False):
            continue
        if len(item['language']) == 2:
            continue
        item['language'] = _adjust_locale(item['language'], item['language'][0:2] in locale_list_nocountry)


def _adjust_locale(locale_code, lang_code_without_country_exists):
    """
    Locale conversion helper
    Conversion table to prevent Kodi to display es-ES as Spanish - Spanish, pt-BR as Portuguese - Breton, and so on
    """
    locale_conversion_table = {
        'es-ES': 'es-Spain',
        'pt-BR': 'pt-Brazil',
        'fr-CA': 'fr-Canada',
        'ar-EG': 'ar-Egypt',
        'nl-BE': 'nl-Belgium'
    }
    language_code = locale_code[0:2]
    if not lang_code_without_country_exists:
        return language_code
    else:
        if locale_code in locale_conversion_table:
            return locale_conversion_table[locale_code]
        else:
            common.debug('AdjustLocale - missing mapping conversion for locale: {}'.format(locale_code))
            return locale_code
