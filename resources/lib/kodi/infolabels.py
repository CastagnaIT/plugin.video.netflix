# -*- coding: utf-8 -*-
"""Helper functions for setting infolabels of list items"""
from __future__ import unicode_literals

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.api.paths as paths
import resources.lib.kodi.library as library

QUALITIES = [
    {'codec': 'h264', 'width': '960', 'height': '540'},
    {'codec': 'h264', 'width': '1920', 'height': '1080'},
    {'codec': 'h265', 'width': '3840', 'height': '2160'}
]

JSONRPC_MAPPINGS = {
    'showtitle': 'tvshowtitle',
    'userrating': 'rating'
}


def add_info(videoid, list_item, item, raw_data):
    """Add infolabels to the list_item. The passed in list_item is modified
    in place and the infolabels are returned."""
    # pylint: disable=too-many-locals
    try:
        cache_entry = g.CACHE.get(cache.CACHE_INFOLABELS, videoid)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except cache.CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data)
        g.CACHE.add(cache.CACHE_INFOLABELS, videoid,
                    {'infos': infos, 'quality_infos': quality_infos},
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
    list_item.setInfo('video', infos)
    if videoid.mediatype == common.VideoId.EPISODE or \
       videoid.mediatype == common.VideoId.MOVIE or \
       videoid.mediatype == common.VideoId.SUPPLEMENTAL:
        list_item.setProperty('isFolder', 'false')
        list_item.setProperty('IsPlayable', 'true')
    for stream_type, quality_infos in quality_infos.iteritems():
        list_item.addStreamInfo(stream_type, quality_infos)
    return infos


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


def parse_art(videoid, item, raw_data):
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
        infos = add_info(videoid, list_item, None, None)
        art = add_art(videoid, list_item, None)
        common.debug('Got infolabels and art from cache')
    except (AttributeError, TypeError):
        common.info('Infolabels or art were not in cache, retrieving from API')
        import resources.lib.api.shakti as api
        api_data = api.single_info(videoid)
        infos = add_info(videoid, list_item, api_data['videos'][videoid.value],
                         api_data)
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
