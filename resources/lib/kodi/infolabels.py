# -*- coding: utf-8 -*-
"""Helper functions for setting infolabels of list items"""
from __future__ import absolute_import, division, unicode_literals

import copy
import re

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


def add_info(videoid, list_item, item, raw_data, set_info=False):
    """Add infolabels to the list_item. The passed in list_item is modified
    in place and the infolabels are returned."""
    # pylint: disable=too-many-locals
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
    # Use a deepcopy of dict to not reflect future changes to the dictionary also to the cache
    infos_copy = copy.deepcopy(infos)
    if videoid.mediatype == common.VideoId.EPISODE or \
       videoid.mediatype == common.VideoId.MOVIE or \
       videoid.mediatype == common.VideoId.SUPPLEMENTAL:
        list_item.setProperty('isFolder', 'false')
        list_item.setProperty('IsPlayable', 'true')
    else:
        list_item.setProperty('isFolder', 'true')
    for stream_type, quality_infos in quality_infos.iteritems():
        list_item.addStreamInfo(stream_type, quality_infos)
    if item.get('dpSupplementalMessage'):
        # Short information about future release of tv show season or other
        infos_copy['plot'] += ' [COLOR green]{}[/COLOR]'.format(item['dpSupplementalMessage'])
    if set_info:
        list_item.setInfo('video', infos_copy)
    return infos_copy


def add_art(videoid, list_item, item, raw_data=None):
    """Add art infolabels to list_item"""
    try:
        art = g.CACHE.get(cache.CACHE_ARTINFO, videoid)
    except cache.CacheMiss:
        art = parse_art(videoid, item, raw_data)
        g.CACHE.add(cache.CACHE_ARTINFO, videoid, art,
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
    list_item.setArt(art)
    return art


@common.time_execution(immediate=False)
def add_info_for_playback(videoid, list_item):
    """Retrieve infolabels and art info and add them to the list_item"""
    try:
        return add_info_from_library(videoid, list_item)
    except library.ItemNotFound as exc:
        common.debug(exc)
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
    """Parse those infos into infolabels that are directly accesible from
    the item dict"""
    return {target: _get_and_transform(source, target, item)
            for target, source
            in paths.INFO_MAPPINGS.iteritems()}


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
            for target, source in paths.REFERENCE_MAPPINGS.iteritems()}


def parse_tags(item):
    """Parse the tags"""
    return {'tag': [tagdef['name']
                    for tagdef
                    in item.get('tags', {}).itervalues()
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
                      boxarts[paths.ART_SIZE_FHD],
                      boxarts[paths.ART_SIZE_SD],
                      boxarts[paths.ART_SIZE_POSTER],
                      interesting_moment,
                      clearlogo,
                      fanart)


def assign_art(videoid, boxart_large, boxart_small, poster, interesting_moment,
               clearlogo, fanart):
    """Assign the art available from Netflix to appropriate Kodi art"""
    # pylint: disable=too-many-arguments
    art = {'poster': _best_art([poster]),
           'fanart': _best_art([fanart, interesting_moment, boxart_large,
                                boxart_small]),
           'thumb': ((interesting_moment
                      if videoid.mediatype == common.VideoId.EPISODE or
                      videoid.mediatype == common.VideoId.SUPPLEMENTAL else '')
                     or boxart_large or boxart_small)}
    art['landscape'] = art['thumb']
    if videoid.mediatype != common.VideoId.UNSPECIFIED:
        art['clearlogo'] = _best_art([clearlogo])
    return art


def _best_art(arts):
    """Return the best art (determined by list order of arts) or
    an empty string if none is available"""
    return next((art for art in arts if art), '')


def add_info_from_netflix(videoid, list_item):
    """Apply infolabels with info from Netflix API"""
    try:
        infos = add_info(videoid, list_item, None, None, True)
        art = add_art(videoid, list_item, None)
        common.debug('Got infolabels and art from cache')
    except (AttributeError, TypeError):
        common.info('Infolabels or art were not in cache, retrieving from API')
        api_data = api.single_info(videoid)
        infos = add_info(videoid, list_item, api_data['videos'][videoid.value], api_data, True)
        art = add_art(videoid, list_item, api_data['videos'][videoid.value])
    return infos, art


def add_info_from_library(videoid, list_item):
    """Apply infolabels with info from Kodi library"""
    details = library.get_item(videoid)
    common.debug('Got fileinfo from library: {}'.format(details))
    art = details.pop('art', {})
    # Resuming for strm files in library is currently broken in all kodi versions
    # keeping this for reference / in hopes this will get fixed
    resume = details.pop('resume', {})
    # if resume:
    #     start_percent = resume['position'] / resume['total'] * 100.0
    #     list_item.setProperty('startPercent', str(start_percent))
    infos = {
        'DBID': details.pop('{}id'.format(videoid.mediatype)),
        'mediatype': videoid.mediatype
    }
    # WARNING!! Remove unsupported ListItem.setInfo keys from 'details' reference ListItem.cpp, using _sanitize_infos
    _sanitize_infos(details)
    infos.update(details)
    list_item.setInfo('video', infos)
    list_item.setArt(art)
    # Workaround for resuming strm files from library
    infos['resume'] = resume
    return infos, art


def _sanitize_infos(details):
    for source, target in JSONRPC_MAPPINGS.items():
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
        updated_title = _colorize_title(list_item.getVideoInfoTag().getTitle().decode("utf-8"),
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
