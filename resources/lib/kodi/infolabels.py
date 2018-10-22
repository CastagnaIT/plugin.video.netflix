# -*- coding: utf-8 -*-
"""Helper functions to build plugin listings for Kodi"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.api.paths as paths

def add_info(list_item, item, item_id, raw_data, tvshowid=None):
    """Add infolabels to the list_item. The passed in list_item is modified
    in place and the infolabels are returned."""
    # pylint: disable=too-many-locals
    try:
        cache_entry = cache.get(cache.CACHE_INFOLABELS, item_id)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except cache.CacheMiss:
        # Only season items don't have a type in their summary, thus, if
        # there's no type, it's a season
        mediatype = item['summary'].get('type', 'season')
        if mediatype == 'show':
            # Type from Netflix doesn't match Kodi's expectations
            mediatype = 'tvshow'

        infos = {
            'mediatype': mediatype,
        }
        quality_infos = get_quality_infos(item)

        if mediatype == 'tvshow':
            infos['tvshowtitle'] = item['title']
        elif tvshowid and mediatype in ['season', 'episode']:
            infos['tvshowtitle'] = raw_data['videos'][tvshowid]['title']

        for target, source in paths.INFO_MAPPINGS.iteritems():
            value = (common.get_path_safe(source, item)
                     if isinstance(source, list)
                     else item.get(source))
            if isinstance(value, dict):
                value = None
            if value is None:
                common.debug('Infolabel {} not available'.format(target))
                continue
            if target in paths.INFO_TRANSFORMATIONS:
                value = paths.INFO_TRANSFORMATIONS[target](value)
            infos[target] = value

        for target, source in paths.REFERENCE_MAPPINGS.iteritems():
            infos[target] = [
                person['name']
                for _, person
                in paths.resolve_refs(item.get(source, {}), raw_data)]

        infos['tag'] = [tagdef['name']
                        for tagdef
                        in item.get('tags', {}).itervalues()
                        if isinstance(tagdef.get('name', {}), unicode)]

        cache.add(cache.CACHE_INFOLABELS,
                  item_id,
                  {'infos': infos, 'quality_infos': quality_infos},
                  ttl=common.CACHE_METADATA_TTL, to_disk=True)

    list_item.setInfo('video', infos)
    if infos['mediatype'] in ['episode', 'movie']:
        list_item.setProperty('IsPlayable', 'true')
    for stream_type, quality_infos in quality_infos.iteritems():
        list_item.addStreamInfo(stream_type, quality_infos)
    return infos

def get_quality_infos(item):
    """Return audio and video quality infolabels"""
    quality_infos = {}
    delivery = item.get('delivery')
    if delivery:
        if delivery.get('hasHD'):
            quality_infos['video'] = {'width': '1920', 'height': '1080'}
        elif delivery.get('hasUltraHD'):
            quality_infos['video'] = {'width': '3840', 'height': '2160'}
        else:
            quality_infos['video'] = {'width': '960', 'height': '540'}
            # quality_infos = {'width': '1280', 'height': '720'}
        if delivery.get('has51Audio'):
            quality_infos['audio'] = {'channels': 6}
        else:
            quality_infos['audio'] = {'channels': 2}
    return quality_infos

def add_art(list_item, item, item_id):
    """Add art infolabels to list_item"""
    try:
        art = cache.get(cache.CACHE_ARTINFO, item_id)
    except cache.CacheMiss:
        boxarts = common.get_multiple_paths(
            paths.ART_PARTIAL_PATHS[0] + ['url'], item)
        boxart_large = boxarts[paths.ART_SIZE_FHD]
        boxart_small = boxarts[paths.ART_SIZE_SD]
        poster = boxarts[paths.ART_SIZE_POSTER]
        interesting_moment = common.get_multiple_paths(
            paths.ART_PARTIAL_PATHS[1] + ['url'], item)[paths.ART_SIZE_FHD]
        clearlogo = common.get_path_safe(
            paths.ART_PARTIAL_PATHS[3] + ['url'], item)
        fanart = common.get_path_safe(
            paths.ART_PARTIAL_PATHS[4] + [0, 'url'], item)
        if boxart_large or boxart_small:
            art = {
                'thumb': boxart_large or boxart_small,
                'landscape': boxart_large or boxart_small,
                'fanart': boxart_large or boxart_small,
            }
        else:
            art = {}
        if poster:
            art['poster'] = poster
        if clearlogo:
            art['clearlogo'] = clearlogo
        if interesting_moment:
            art['fanart'] = interesting_moment
            if item.get('summary', {}).get('type') == 'episode':
                art['thumb'] = interesting_moment
                art['landscape'] = interesting_moment
        if fanart:
            art['fanart'] = fanart
        cache.add(cache.CACHE_ARTINFO, item_id, art,
                  ttl=common.CACHE_METADATA_TTL, to_disk=True)
    list_item.setArt(art)
    return art
