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
import re

from future.utils import iteritems, itervalues

import resources.lib.api.paths as paths
import resources.lib.api.shakti as api
import resources.lib.cache as cache
import resources.lib.common as common
import resources.lib.kodi.library as library
from resources.lib.globals import g

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

QUALITIES = [
    {'codec': 'h264', 'width': '960', 'height': '540'},
    {'codec': 'h264', 'width': '1920', 'height': '1080'},
    {'codec': 'h265', 'width': '3840', 'height': '2160'}
]

JSONRPC_MAPPINGS = {
    'showtitle': 'tvshowtitle',
    'userrating': 'rating'
}


def get_info(videoid, item, raw_data):
    """Get the infolabels data"""
    cache_identifier = unicode(videoid) + '_' + g.LOCAL_DB.get_profile_config('language', '')
    try:
        cache_entry = g.CACHE.get(cache.CACHE_INFOLABELS, cache_identifier)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except cache.CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data)
        g.CACHE.add(cache.CACHE_INFOLABELS, cache_identifier,
                    {'infos': infos, 'quality_infos': quality_infos},
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
    return infos, quality_infos


def add_info(videoid, list_item, item, raw_data, handle_highlighted_title=False):
    """Add infolabels to the list_item. The passed in list_item is modified
    in place and the infolabels are returned."""
    infos, quality_infos = get_info(videoid, item, raw_data)
    # Use a deepcopy of dict to not reflect future changes to the dictionary also to the cache
    infos_copy = copy.deepcopy(infos)
    if videoid.mediatype == common.VideoId.EPISODE or \
       videoid.mediatype == common.VideoId.MOVIE or \
       videoid.mediatype == common.VideoId.SUPPLEMENTAL:
        list_item.setProperty('isFolder', 'false')
        list_item.setProperty('IsPlayable', 'true')
        # Set the resume and watched status to the list item
        _set_progress_status(list_item, item, infos_copy)
    else:
        list_item.setProperty('isFolder', 'true')
    for stream_type, quality_infos in iteritems(quality_infos):
        list_item.addStreamInfo(stream_type, quality_infos)
    if item.get('dpSupplementalMessage'):
        # Short information about future release of tv show season or other
        infos_copy['plot'] += '[CR][COLOR green]{}[/COLOR]'.format(item['dpSupplementalMessage'])
    if handle_highlighted_title:
        add_highlighted_title(list_item, videoid, infos)
    list_item.setInfo('video', infos_copy)
    return infos_copy


def get_art(videoid, item, raw_data=None):
    """Get art infolabels"""
    try:
        art = g.CACHE.get(cache.CACHE_ARTINFO, videoid)
    except cache.CacheMiss:
        art = parse_art(videoid, item, raw_data)
        g.CACHE.add(cache.CACHE_ARTINFO, videoid, art,
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
    return art


def add_art(videoid, list_item, item, raw_data=None):
    """Add art infolabels to list_item"""
    art = get_art(videoid, item, raw_data)
    list_item.setArt(art)
    return art


@common.time_execution(immediate=False)
def get_info_for_playback(videoid, skip_add_from_library):
    """Get infolabels and art info"""
    # By getting the info from the library you can not get the length of video required for Up Next addon
    # waiting for a suitable solution we avoid this method by using skip_add_from_library
    if not skip_add_from_library:
        try:
            return get_info_from_library(videoid)
        except library.ItemNotFound:
            common.debug('Can not get infolabels from the library, submit a request to netflix')
    return get_info_from_netflix(videoid)


@common.time_execution(immediate=False)
def add_info_for_playback(videoid, list_item, skip_add_from_library):
    """Retrieve infolabels and art info and add them to the list_item"""
    # By getting the info from the library you can not get the length of video required for Up Next addon
    # waiting for a suitable solution we avoid this method by using skip_add_from_library
    if not skip_add_from_library:
        try:
            return add_info_from_library(videoid, list_item)
        except library.ItemNotFound:
            common.debug('Can not get infolabels from the library, submit a request to netflix')
    return add_info_from_netflix(videoid, list_item)


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

    infos.update(parse_atomic_infos(item))
    infos.update(parse_referenced_infos(item, raw_data))
    infos.update(parse_tags(item))

    return infos, get_quality_infos(item)


def parse_atomic_infos(item):
    """Parse those infos into infolabels that are directly accessible from the item dict"""
    infos = {target: _get_and_transform(source, target, item)
             for target, source in iteritems(paths.INFO_MAPPINGS)}
    # When you browse the seasons list, season numbering is provided from a different property
    season_shortname = infos.pop('season_shortname')
    if season_shortname:
        infos.update({'season': season_shortname})
    return infos


def _get_and_transform(source, target, item):
    """Get the value for source and transform it if neccessary"""
    value = common.get_path_safe(source, item)
    if isinstance(value, dict) or value is None:
        return ''
    return (paths.INFO_TRANSFORMATIONS[target](value)
            if target in paths.INFO_TRANSFORMATIONS
            else value)


def parse_referenced_infos(item, raw_data):
    """Parse those infos into infolabels that need their references
    resolved within the raw data"""
    return {target: [person['name']
                     for _, person
                     in paths.resolve_refs(item.get(source, {}), raw_data)]
            for target, source in iteritems(paths.REFERENCE_MAPPINGS)}


def parse_tags(item):
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
        quality_infos['audio'] = {
            'channels': 2 + 4 * delivery.get('has51Audio', False)}
        if g.ADDON.getSettingBool('enable_dolby_sound'):
            if delivery.get('hasDolbyAtmos', False):
                quality_infos['audio']['codec'] = 'truehd'
            else:
                quality_infos['audio']['codec'] = 'eac3'
        else:
            quality_infos['audio']['codec'] = 'aac'
    return quality_infos


def parse_art(videoid, item, raw_data):  # pylint: disable=unused-argument
    """Parse art info from a path request response to Kodi art infolabels"""
    boxarts = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[0] + ['url'], item)
    interesting_moment = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[1] + ['url'], item, {}).get(paths.ART_SIZE_FHD)
    clearlogo = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[3] + ['url'], item)
    fanart = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[4] + [0, 'url'], item)
    return assign_art(videoid,
                      boxart_large=boxarts[paths.ART_SIZE_FHD],
                      boxart_small=boxarts[paths.ART_SIZE_SD],
                      poster=boxarts[paths.ART_SIZE_POSTER],
                      interesting_moment=interesting_moment,
                      clearlogo=clearlogo,
                      fanart=fanart)


def assign_art(videoid, **kwargs):
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
    """Return the best art (determined by list order of arts) or
    an empty string if none is available"""
    return next((art for art in arts if art), '')


def get_info_from_netflix(videoid):
    """Get infolabels with info from Netflix API"""
    try:
        infos = get_info(videoid, None, None)[0]
        art = get_art(videoid, None)
        common.debug('Got infolabels and art from cache')
    except (AttributeError, TypeError):
        common.debug('Infolabels or art were not in cache, retrieving from API')
        api_data = api.single_info(videoid)
        infos = get_info(videoid, api_data['videos'][videoid.value], api_data)[0]
        art = get_art(videoid, api_data['videos'][videoid.value])
    return infos, art


def add_info_from_netflix(videoid, list_item):
    """Apply infolabels with info from Netflix API"""
    try:
        infos = add_info(videoid, list_item, None, None)
        art = add_art(videoid, list_item, None)
        common.debug('Got infolabels and art from cache')
    except (AttributeError, TypeError):
        common.debug('Infolabels or art were not in cache, retrieving from API')
        api_data = api.single_info(videoid)
        infos = add_info(videoid, list_item, api_data['videos'][videoid.value], api_data)
        art = add_art(videoid, list_item, api_data['videos'][videoid.value])
    return infos, art


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


def add_info_from_library(videoid, list_item):
    """Apply infolabels with info from Kodi library"""
    infos, art = get_info_from_library(videoid)
    # Resuming for strm files in library is currently broken in all kodi versions
    # keeping this for reference / in hopes this will get fixed
    resume = infos.pop('resume', {})
    # if resume:
    #     start_percent = resume['position'] / resume['total'] * 100.0
    #     list_item.setProperty('startPercent', str(start_percent))
    # WARNING!! Remove unsupported ListItem.setInfo keys from 'details' by using _sanitize_infos
    # reference to Kodi ListItem.cpp
    _sanitize_infos(infos)
    list_item.setInfo('video', infos)
    list_item.setArt(art)
    # Workaround for resuming strm files from library
    infos['resume'] = resume
    return infos, art


def _sanitize_infos(details):
    for source, target in iteritems(JSONRPC_MAPPINGS):
        if source in details:
            details[target] = details.pop(source)
    for prop in ['file', 'label', 'runtime']:
        details.pop(prop, None)


def add_highlighted_title(list_item, videoid, infos):
    """Highlight menu item title when the videoid is contained in my-list"""
    highlight_index = g.ADDON.getSettingInt('highlight_mylist_titles')
    if not highlight_index:
        return
    highlight_color = ['black', 'blue', 'red', 'green', 'white', 'yellow'][highlight_index]
    remove_color = videoid not in api.mylist_items()
    if list_item.getProperty('isFolder') == 'true':
        updated_title = _colorize_title(g.py2_decode(list_item.getVideoInfoTag().getTitle()),
                                        highlight_color,
                                        remove_color)
        list_item.setLabel(updated_title)
        infos['title'] = updated_title
    else:
        # When menu item is not a folder 'label' is replaced by 'title' property of infoLabel
        infos['title'] = _colorize_title(infos['title'], highlight_color, remove_color)


def _colorize_title(text, color, remove_color=False):
    matches = re.match(r'(\[COLOR\s.+\])(.*)(\[/COLOR\])', text)
    if remove_color:
        if matches:
            return matches.groups()[1]
    else:
        if not matches:
            return '[COLOR {}]{}[/COLOR]'.format(color, text)
    return text


def _set_progress_status(list_item, video_data, infos):
    """Check and set progress status (watched and resume)"""
    if not g.ADDON.getSettingBool('ProgressManager_enabled'):
        return

    video_id = video_data['summary']['id']
    # Check from db if user has manually changed the watched status
    profile_guid = g.LOCAL_DB.get_active_profile_guid()
    override_is_watched = g.SHARED_DB.get_watched_status(profile_guid, video_id, None, bool)

    if override_is_watched is None:
        # NOTE shakti 'watched' tag value:
        # in my tests playing a video (via web browser) until to the end this value is not changed to True
        # seem not respect really if a video is watched to the end or this tag have other purposes
        # to now, the only way to know if a video is watched is compare the bookmarkPosition with creditsOffset value

        # NOTE shakti 'creditsOffset' tag not exists on video type 'movie',
        # then simulate the default Kodi playcount behaviour (playcountminimumpercent)
        watched_threshold = video_data['runtime'] / 100 * 90
        if video_data.get('creditsOffset') and video_data['creditsOffset'] < watched_threshold:
            watched_threshold = video_data['creditsOffset']

        # NOTE shakti 'bookmarkPosition' tag when it is not set have -1 value
        playcount = '1' if video_data['bookmarkPosition'] >= watched_threshold else '0'
        if playcount == '0' and video_data['bookmarkPosition'] > 0:
            list_item.setProperty('ResumeTime', str(video_data['bookmarkPosition']))
            list_item.setProperty('TotalTime', str(video_data['runtime']))
    else:
        playcount = '1' if override_is_watched else '0'
    # We have to set playcount with setInfo(), because the setProperty('PlayCount', ) have a bug
    # when a item is already watched and you force to set again watched, the override do not work
    infos['PlayCount'] = playcount
