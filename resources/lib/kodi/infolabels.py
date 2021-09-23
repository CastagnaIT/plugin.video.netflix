# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for setting infolabels of list items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import copy

import resources.lib.utils.api_paths as paths
import resources.lib.common as common
from resources.lib.common.exceptions import CacheMiss, ItemNotFound
from resources.lib.common.cache_utils import CACHE_BOOKMARKS, CACHE_INFOLABELS, CACHE_ARTINFO
from resources.lib.common.kodi_wrappers import ListItemW
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


# For each videos Netflix provides multiple codecs and the resolutions depends on type of device/SO/DRM used
# it is not possible to provide specific info, then we set info according to the video properties of the video list data
# h264 is the entry-level codec always available to all streams, the 4k only works with HEVC
QUALITIES = [
    {'codec': 'h264', 'width': '960', 'height': '540'},
    {'codec': 'h264', 'width': '1920', 'height': '1080'},
    {'codec': 'hevc', 'width': '3840', 'height': '2160'}
]

COLORS = [None, 'blue', 'red', 'green', 'white', 'yellow', 'black', 'gray']

# Mapping of videoid type to ListItem.MediaType
MEDIA_TYPE_MAPPINGS = {
    common.VideoId.SHOW: 'tvshow',
    common.VideoId.SEASON: 'season',
    common.VideoId.EPISODE: 'episode',
    common.VideoId.MOVIE: 'movie',
    common.VideoId.SUPPLEMENTAL: 'video',
    common.VideoId.UNSPECIFIED: 'video'
}


def get_info(videoid, item, raw_data, profile_language_code='', delayed_db_op=False):
    """Get the infolabels data"""
    cache_identifier = f'{videoid.value}_{profile_language_code}'
    try:
        cache_entry = G.CACHE.get(CACHE_INFOLABELS, cache_identifier)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data)
        G.CACHE.add(CACHE_INFOLABELS, cache_identifier, {'infos': infos, 'quality_infos': quality_infos},
                    delayed_db_op=delayed_db_op)
    return infos, quality_infos


def add_info_list_item(list_item: ListItemW, videoid, item, raw_data, is_in_mylist, common_data, art_item=None):
    """Add infolabels and art to a ListItem"""
    infos, quality_infos = get_info(videoid, item, raw_data,
                                    delayed_db_op=True)
    list_item.addStreamInfoFromDict(quality_infos)
    # Use a deepcopy of dict to not reflect future changes to the dictionary also to the cache
    infos_copy = copy.deepcopy(infos)
    if 'Plot' not in infos_copy and 'PlotOutline' in infos_copy:
        # Not all skins support read value from PlotOutline
        infos_copy['Plot'] = infos_copy['PlotOutline']
    _add_supplemental_plot_info(infos_copy, item, common_data)
    if is_in_mylist and common_data.get('mylist_titles_color'):
        # Highlight ListItem title when the videoid is contained in my-list
        list_item.setLabel(_colorize_text(common_data['mylist_titles_color'], list_item.getLabel()))
    infos_copy['title'] = list_item.getLabel()
    list_item.setInfo('video', infos_copy)
    list_item.setArt(get_art(videoid, art_item or item or {}, common_data['profile_language_code'],
                             delayed_db_op=True))


def _add_supplemental_plot_info(infos_copy, item, common_data):
    """Add supplemental info to plot description"""
    suppl_info = []
    if item.get('summary', {}).get('availabilityDateMessaging'):
        suppl_info.append(item['summary']['availabilityDateMessaging'])
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
    plot = infos_copy.get('Plot', '')
    plotoutline = infos_copy.get('PlotOutline', '')
    if suppl_text:
        suppl_text = _colorize_text(common_data['supplemental_info_color'], suppl_text)
        if plot:
            plot += '[CR][CR]'
        if plotoutline:
            plotoutline += '[CR][CR]'
        infos_copy.update({'Plot': plot + suppl_text})
        infos_copy.update({'PlotOutline': plotoutline + suppl_text})


def get_art(videoid, item, profile_language_code='', delayed_db_op=False):
    """Get art infolabels - NOTE: If 'item' arg is None this method can raise TypeError when there is not cache"""
    cache_identifier = f'{videoid.value}_{profile_language_code}'
    try:
        art = G.CACHE.get(CACHE_ARTINFO, cache_identifier)
    except CacheMiss:
        art = parse_art(videoid, item)
        G.CACHE.add(CACHE_ARTINFO, cache_identifier, art,
                    delayed_db_op=delayed_db_op)
    return art


def get_resume_info_from_library(videoid):
    """Retrieve the resume value from the Kodi library"""
    try:
        return get_info_from_library(videoid)[0].get('resume', {})
    except ItemNotFound:
        LOG.warn('Can not get resume value from the library')
    return {}


def parse_info(videoid, item, raw_data):
    """Parse info from a path request response into Kodi infolabels"""
    if (videoid.mediatype == common.VideoId.UNSPECIFIED and
            hasattr(item, 'contained_titles')):
        # Special handling for VideoLists
        return {
            'Plot':
                common.get_local_string(30087).format(
                    ', '.join(item.contained_titles))
                if item.contained_titles
                else common.get_local_string(30111)
        }, {}

    infos = {'MediaType': MEDIA_TYPE_MAPPINGS[videoid.mediatype]}
    if videoid.mediatype in common.VideoId.TV_TYPES:
        infos['TVShowTitle'] = raw_data['videos'][videoid.tvshowid]['title']
    if item.get('watched', False):
        infos['PlayCount'] = 1

    infos.update(_parse_atomic_infos(item))
    infos.update(_parse_referenced_infos(item, raw_data))
    infos.update(_parse_tags(item))

    return infos, get_quality_infos(item)


def _parse_atomic_infos(item):
    """Parse those infos into infolabels that are directly accessible from the item dict"""
    infos = {}
    for target, source in paths.INFO_MAPPINGS:
        value = common.get_path_safe(source, item)
        # The dict check is needed when the info requested is not available
        # and jsonGraph return a dict of $type sentinel
        if not isinstance(value, dict) and value is not None:
            infos[target] = _transform_value(target, value)
    return infos


def _transform_value(target, value):
    """Transform a target value if necessary"""
    return (paths.INFO_TRANSFORMATIONS[target](value)
            if target in paths.INFO_TRANSFORMATIONS
            else value)


def _parse_referenced_infos(item, raw_data):
    """Parse those infos into infolabels that need their references
    resolved within the raw data"""
    return {target: [person['name']
                     for _, person
                     in paths.resolve_refs(item.get(source, {}), raw_data)]
            for target, source in paths.REFERENCE_MAPPINGS.items()}


def _parse_tags(item):
    """Parse the tags"""
    return {'tag': [tagdef['name']
                    for tagdef
                    in item.get('tags', {}).values()
                    if isinstance(tagdef.get('name', {}), str)]}


def get_quality_infos(item):
    """Return audio and video quality infolabels"""
    quality_infos = {}
    delivery = item.get('delivery')
    if delivery:
        quality_infos['video'] = QUALITIES[
            min((delivery.get('hasUltraHD', False) << 1 |
                 delivery.get('hasHD')), 2)]
        quality_infos['audio'] = {'channels': 2 + 4 * delivery.get('has51Audio', False)}
        if G.ADDON.getSettingBool('enable_dolby_sound'):
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
                      if videoid.mediatype in (common.VideoId.EPISODE, common.VideoId.SUPPLEMENTAL) else '')
                     or kwargs['boxart_large'] or kwargs['boxart_small'])}
    art['landscape'] = art['thumb']
    if videoid.mediatype != common.VideoId.UNSPECIFIED:
        art['clearlogo'] = _best_art([kwargs['clearlogo']])
    return art


def _best_art(arts):
    """Return the best art (determined by list order of arts) or an empty string if none is available"""
    return next((art for art in arts if art), '')


def get_info_from_library(videoid):
    """Get infolabels with info from Kodi library"""
    details = common.get_library_item_by_videoid(videoid)
    LOG.debug('Got file info from library: {}', details)
    art = details.pop('art', {})
    infos = {
        'DBID': details.pop(f'{videoid.mediatype}id'),
        'MediaType': MEDIA_TYPE_MAPPINGS[videoid.mediatype]
    }
    infos.update(details)
    return infos, art


def _colorize_text(color_name, text):
    if color_name:
        return f'[COLOR {color_name}]{text}[/COLOR]'
    return text


def get_color_name(color_index):
    return COLORS[color_index]


def set_watched_status(list_item: ListItemW, video_data, common_data):
    """Check and set progress status (watched and resume)"""
    if not common_data['set_watched_status']:
        return
    video_id = str(video_data['summary']['id'])
    # Check from db if user has manually changed the watched status
    is_watched_user_overrided = G.SHARED_DB.get_watched_status(common_data['active_profile_guid'], video_id, None, bool)
    resume_time = 0
    if is_watched_user_overrided is None:
        # Note to shakti properties:
        # 'watched':  unlike the name this value is used to other purposes, so not to set a video as watched
        # 'watchedToEndOffset':  this value is used to determine if a video is watched but
        #                        is available only with the metadata api and only for "episode" video type
        # 'creditsOffset' :  this value is used as position where to show the (play) "Next" (episode) button
        #                    on the website, but it may not be always available with the "movie" video type
        if 'creditsOffset' in video_data:
            # To better ensure that a video is marked as watched also when a user do not reach the ending credits
            # we generally lower the watched threshold by 50 seconds for 50 minutes of video (3000 secs)
            lower_value = video_data['runtime'] / 3000 * 50
            watched_threshold = video_data['creditsOffset'] - lower_value
        else:
            # When missing the value should be only a video of movie type,
            # then we simulate the default Kodi playcount behaviour (playcountminimumpercent)
            watched_threshold = video_data['runtime'] / 100 * 90
        # To avoid asking to the server again the entire list of titles (after watched a video)
        # to get the updated value, we override the value with the value saved in memory (see am_video_events.py)
        try:
            bookmark_position = G.CACHE.get(CACHE_BOOKMARKS, video_id)
        except CacheMiss:
            # NOTE shakti 'bookmarkPosition' tag when it is not set have -1 value
            bookmark_position = video_data['bookmarkPosition']
        playcount = '1' if bookmark_position >= watched_threshold else '0'
        if playcount == '0' and bookmark_position > 0:
            resume_time = bookmark_position
    else:
        playcount = '1' if is_watched_user_overrided else '0'
    # We have to set playcount with setInfo(), because the setProperty('PlayCount', ) have a bug
    # when a item is already watched and you force to set again watched, the override do not work
    list_item.updateInfo({'PlayCount': playcount})
    list_item.setProperty('TotalTime', str(video_data['runtime']))
    list_item.setProperty('ResumeTime', str(resume_time))
