# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for setting infolabels of list items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import copy

from future.utils import iteritems, itervalues

import resources.lib.api.paths as paths
import resources.lib.api.api_requests as api
import resources.lib.common as common
import resources.lib.kodi.library as library
from resources.lib.api.exceptions import CacheMiss
from resources.lib.common.cache_utils import CACHE_BOOKMARKS, CACHE_INFOLABELS, CACHE_ARTINFO
from resources.lib.globals import g

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

# For each videos Netflix provides multiple codecs and the resolutions depends on type of device/SO/DRM used
# it is not possible to provide specific info, then we set info according to the video properties of the video list data
# h264 is the entry-level codec always available to all streams, the 4k only works with HEVC
QUALITIES = [
    {'codec': 'h264', 'width': '960', 'height': '540'},
    {'codec': 'h264', 'width': '1920', 'height': '1080'},
    {'codec': 'hevc', 'width': '3840', 'height': '2160'}
]

JSONRPC_MAPPINGS = {
    'showtitle': 'tvshowtitle',
    'userrating': 'rating'
}

COLORS = [None, 'blue', 'red', 'green', 'white', 'yellow', 'black', 'gray']


def get_info(videoid, item, raw_data, profile_language_code=''):
    """Get the infolabels data"""
    cache_identifier = videoid.value + '_' + profile_language_code
    try:
        cache_entry = g.CACHE.get(CACHE_INFOLABELS, cache_identifier)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data)
        g.CACHE.add(CACHE_INFOLABELS, cache_identifier, {'infos': infos, 'quality_infos': quality_infos})
    return infos, quality_infos


def add_info_dict_item(dict_item, videoid, item, raw_data, is_in_mylist, common_data):
    """Add infolabels to a dict_item"""
    infos, quality_infos = get_info(videoid, item, raw_data)
    dict_item['quality_info'] = quality_infos
    # Use a deepcopy of dict to not reflect future changes to the dictionary also to the cache
    infos_copy = copy.deepcopy(infos)

    _add_supplemental_plot_info(infos_copy, item, common_data)
    if is_in_mylist and common_data.get('mylist_titles_color'):
        add_title_color(dict_item, infos_copy, common_data)
    dict_item['info'] = infos_copy


def _add_supplemental_plot_info(infos_copy, item, common_data):
    """Add supplemental info to plot description"""
    suppl_info = []
    if item.get('dpSupplementalMessage'):
        # Short information about future release of tv show season or other
        suppl_info.append(item['dpSupplementalMessage'])
    # The 'sequiturEvidence' dict can be of type 'hook' or 'watched'
    if (item.get('sequiturEvidence') and
            item['sequiturEvidence'].get('type') == 'hook' and
            item['sequiturEvidence'].get('value')):
        # Short information about the actors career/awards and similarities/connections with others films or tv shows
        suppl_info.append(item['sequiturEvidence']['value']['text'])
    suppl_text = '[CR][CR]'.join(suppl_info)
    if suppl_text and infos_copy['plot']:
        infos_copy['plot'] += '[CR][CR]'
    infos_copy['plot'] += _colorize_text(common_data['supplemental_info_color'], suppl_text)


def get_art(videoid, item, profile_language_code=''):
    """Get art infolabels"""
    return _get_art(videoid, item or {}, profile_language_code)


def _get_art(videoid, item, profile_language_code):
    # If item is None this method raise TypeError
    cache_identifier = videoid.value + '_' + profile_language_code
    try:
        art = g.CACHE.get(CACHE_ARTINFO, cache_identifier)
    except CacheMiss:
        art = parse_art(videoid, item)
        g.CACHE.add(CACHE_ARTINFO, cache_identifier, art)
    return art


def get_resume_info_from_library(videoid):
    """Retrieve the resume value from the Kodi library"""
    try:
        return get_info_from_library(videoid)[0].get('resume', {})
    except library.ItemNotFound:
        common.warn('Can not get resume value from the library')
    return {}


def parse_info(videoid, item, raw_data):
    """Parse info from a path request response into Kodi infolabels"""
    if (videoid.mediatype == common.VideoId.UNSPECIFIED and
            hasattr(item, 'contained_titles')):
        # Special handling for VideoLists
        return {
            'plot':
                common.get_local_string(30087).format(
                    ', '.join(item.contained_titles))
                if item.contained_titles
                else common.get_local_string(30111)
        }, {}

    infos = {'mediatype': ('tvshow'
                           if videoid.mediatype == common.VideoId.SHOW or
                           videoid.mediatype == common.VideoId.SUPPLEMENTAL
                           else videoid.mediatype)}
    if videoid.mediatype in common.VideoId.TV_TYPES:
        infos['tvshowtitle'] = raw_data['videos'][videoid.tvshowid]['title']
    if item.get('watched', False):
        infos['playcount'] = 1

    infos.update(_parse_atomic_infos(item))
    infos.update(_parse_referenced_infos(item, raw_data))
    infos.update(_parse_tags(item))

    return infos, get_quality_infos(item)


def _parse_atomic_infos(item):
    """Parse those infos into infolabels that are directly accessible from the item dict"""
    infos = {target: _get_and_transform(source, target, item)
             for target, source in iteritems(paths.INFO_MAPPINGS)}
    # When you browse the seasons list, season numbering is provided from a different property
    season_shortname = infos.pop('season_shortname')
    if season_shortname:
        infos.update({'season': season_shortname})
    return infos


def _get_and_transform(source, target, item):
    """Get the value for source and transform it if necessary"""
    value = common.get_path_safe(source, item)
    if isinstance(value, dict) or value is None:
        return ''
    return (paths.INFO_TRANSFORMATIONS[target](value)
            if target in paths.INFO_TRANSFORMATIONS
            else value)


def _parse_referenced_infos(item, raw_data):
    """Parse those infos into infolabels that need their references
    resolved within the raw data"""
    return {target: [person['name']
                     for _, person
                     in paths.resolve_refs(item.get(source, {}), raw_data)]
            for target, source in iteritems(paths.REFERENCE_MAPPINGS)}


def _parse_tags(item):
    """Parse the tags"""
    return {'tag': [tagdef['name']
                    for tagdef
                    in itervalues(item.get('tags', {}))
                    if isinstance(tagdef.get('name', {}), unicode)]}


def get_quality_infos(item):
    """Return audio and video quality infolabels"""
    quality_infos = {}
    delivery = item.get('delivery')
    if delivery:
        quality_infos['video'] = QUALITIES[
            min((delivery.get('hasUltraHD', False) << 1 |
                 delivery.get('hasHD')), 2)]
        quality_infos['audio'] = {'channels': 2 + 4 * delivery.get('has51Audio', False)}
        if g.ADDON.getSettingBool('enable_dolby_sound'):
            if delivery.get('hasDolbyAtmos', False):
                quality_infos['audio']['codec'] = 'truehd'
            else:
                quality_infos['audio']['codec'] = 'eac3'
        else:
            quality_infos['audio']['codec'] = 'aac'
    return quality_infos


def parse_art(videoid, item):
    """Parse art info from a path request response to Kodi art infolabels"""
    boxarts = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[0] + ['url'], item, {})
    interesting_moment = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[1] + ['url'], item, {})
    clearlogo = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[2] + ['url'], item)
    fanart = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[3] + [0, 'url'], item)
    return _assign_art(videoid,
                       boxart_large=boxarts.get(paths.ART_SIZE_FHD),
                       boxart_small=boxarts.get(paths.ART_SIZE_SD),
                       poster=boxarts.get(paths.ART_SIZE_POSTER),
                       interesting_moment=interesting_moment.get(paths.ART_SIZE_FHD),
                       clearlogo=clearlogo,
                       fanart=fanart)


def _assign_art(videoid, **kwargs):
    """Assign the art available from Netflix to appropriate Kodi art"""
    art = {'poster': _best_art([kwargs['poster']]),
           'fanart': _best_art([kwargs['fanart'],
                                kwargs['interesting_moment'],
                                kwargs['boxart_large'],
                                kwargs['boxart_small']]),
           'thumb': ((kwargs['interesting_moment']
                      if videoid.mediatype == common.VideoId.EPISODE or
                      videoid.mediatype == common.VideoId.SUPPLEMENTAL else '')
                     or kwargs['boxart_large'] or kwargs['boxart_small'])}
    art['landscape'] = art['thumb']
    if videoid.mediatype != common.VideoId.UNSPECIFIED:
        art['clearlogo'] = _best_art([kwargs['clearlogo']])
    return art


def _best_art(arts):
    """Return the best art (determined by list order of arts) or an empty string if none is available"""
    return next((art for art in arts if art), '')


def get_info_from_netflix(videoids):
    """Get infolabels and arts from cache (if exist) or Netflix API, for multiple videoid"""
    profile_language_code = g.LOCAL_DB.get_profile_config('language', '')
    videoids_to_request = []
    info_data = {}
    for videoid in videoids:
        try:
            infos = get_info(videoid, None, None, profile_language_code)[0]
            art = _get_art(videoid, None, profile_language_code)
            info_data[videoid.value] = infos, art
            common.debug('Got infolabels and art from cache for videoid {}', videoid)
        except (AttributeError, TypeError):
            videoids_to_request.append(videoid)

    if videoids_to_request:
        # Retrieve missing data from API
        common.debug('Retrieving infolabels and art from API for {} videoids', len(videoids_to_request))
        raw_data = api.get_video_raw_data(videoids_to_request)
        for videoid in videoids_to_request:
            infos = get_info(videoid, raw_data['videos'][videoid.value], raw_data, profile_language_code)[0]
            art = get_art(videoid, raw_data['videos'][videoid.value], profile_language_code)
            info_data[videoid.value] = infos, art
    return info_data


def get_info_from_library(videoid):
    """Get infolabels with info from Kodi library"""
    details = library.get_item(videoid)
    common.debug('Got file info from library: {}'.format(details))
    art = details.pop('art', {})
    infos = {
        'DBID': details.pop('{}id'.format(videoid.mediatype)),
        'mediatype': videoid.mediatype
    }
    infos.update(details)
    return infos, art


def add_title_color(dict_item, infos_copy, common_data):
    """Highlight list item title when the videoid is contained in my-list"""
    updated_title = _colorize_text(common_data['mylist_titles_color'], infos_copy['title'])
    if dict_item['is_folder']:
        dict_item['label'] = updated_title
    # When a xbmcgui.Listitem is not a folder 'label' is replaced by 'title' property of infoLabel
    infos_copy['title'] = updated_title


def _colorize_text(color_name, text):
    if color_name:
        return '[COLOR {}]{}[/COLOR]'.format(color_name, text)
    return text


def get_color_name(color_index):
    return COLORS[color_index]


def set_watched_status(dict_item, video_data, common_data):
    """Check and set progress status (watched and resume)"""
    if not common_data['set_watched_status'] or dict_item['is_folder']:
        return

    video_id = str(video_data['summary']['id'])
    # Check from db if user has manually changed the watched status
    profile_guid = g.LOCAL_DB.get_active_profile_guid()
    override_is_watched = g.SHARED_DB.get_watched_status(profile_guid, video_id, None, bool)
    resume_time = 0

    if override_is_watched is None:
        # NOTE shakti 'watched' tag value:
        # in my tests playing a video (via web browser) until to the end this value is not changed to True
        # seem not respect really if a video is watched to the end or this tag have other purposes
        # to now, the only way to know if a video is watched is compare the bookmarkPosition with creditsOffset value

        # NOTE shakti 'creditsOffset' tag not exists on video type 'movie',
        # then simulate the default Kodi playcount behaviour (playcountminimumpercent)
        watched_threshold = min(video_data['runtime'] / 100 * 90,
                                video_data.get('creditsOffset', video_data['runtime']))

        # To avoid asking to the server again the entire list of titles (after watched a video)
        # to get the updated value, we override the value with the value saved in memory (see am_video_events.py)
        try:
            bookmark_position = g.CACHE.get(CACHE_BOOKMARKS, video_id)
        except CacheMiss:
            # NOTE shakti 'bookmarkPosition' tag when it is not set have -1 value
            bookmark_position = video_data['bookmarkPosition']

        playcount = '1' if bookmark_position >= watched_threshold else '0'
        if playcount == '0' and bookmark_position > 0:
            resume_time = bookmark_position
    else:
        playcount = '1' if override_is_watched else '0'
    # We have to set playcount with setInfo(), because the setProperty('PlayCount', ) have a bug
    # when a item is already watched and you force to set again watched, the override do not work
    dict_item['info']['PlayCount'] = playcount
    dict_item['TotalTime'] = str(video_data['runtime'])
    dict_item['ResumeTime'] = str(resume_time)
