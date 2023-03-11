# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for setting infolabels of list items

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import copy
import time

import resources.lib.utils.api_paths as paths
import resources.lib.common as common
from resources.lib.common.exceptions import CacheMiss, ItemNotFound
from resources.lib.common.cache_utils import CACHE_BOOKMARKS, CACHE_INFOLABELS, CACHE_ARTINFO
from resources.lib.common.kodi_wrappers import ListItemW
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


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


def get_video_codec_hint():
    """Suggests which codec the video may have"""
    # The video lists do not provide the type of codec, it depends on many factors (device/SO/DRM/manifest request)
    # but we can rely on which codec is enabled from the settings, if there are more codecs enabled usually
    # the most efficient codec has the priority, e.g. HEVC > VP9 > H264
    # This could be not always reliable, depends also on the availability of stream types
    codec = 'h264'
    if G.ADDON.getSettingBool('enable_hevc_profiles'):
        codec = 'hevc'
    elif G.ADDON.getSettingBool('enable_vp9_profiles'):
        codec = 'vp9'
    return codec


def get_info(videoid, item, raw_data, profile_language_code='', delayed_db_op=False, common_data=None):
    """Get the infolabels data"""
    if common_data is None:
        common_data = {}
    cache_identifier = f'{videoid.value}_{profile_language_code}'
    try:
        cache_entry = G.CACHE.get(CACHE_INFOLABELS, cache_identifier)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data, common_data)
        G.CACHE.add(CACHE_INFOLABELS, cache_identifier, {'infos': infos, 'quality_infos': quality_infos},
                    delayed_db_op=delayed_db_op)
    # Use a deepcopy of dict to not reflect changes of the dictionary also to the cache
    infos_copy = copy.deepcopy(infos)
    # Not all skins support PlotOutline, so copy over Plot if it does not exist
    if 'Plot' not in infos_copy and 'PlotOutline' in infos_copy:
        infos_copy['Plot'] = infos_copy['PlotOutline']
    _add_supplemental_plot_info(infos_copy, item, common_data)
    return infos_copy, quality_infos


def add_info_list_item(list_item: ListItemW, videoid, item, raw_data, is_in_mylist, common_data, art_item=None,
                       is_in_remind_me=False):
    """Add infolabels and art to a ListItem"""
    infos, quality_infos = get_info(videoid, item, raw_data, delayed_db_op=True, common_data=common_data)
    list_item.addStreamInfoFromDict(quality_infos)
    if is_in_mylist and common_data.get('mylist_titles_color'):
        # Highlight ListItem title when the videoid is contained in "My list"
        list_item.setLabel(_colorize_text(common_data['mylist_titles_color'], list_item.getLabel()))
    elif is_in_remind_me:
        # Highlight ListItem title when a video is marked as "Remind me"
        list_item.setLabel(_colorize_text(common_data['rememberme_titles_color'], list_item.getLabel()))
    infos['Title'] = list_item.getLabel()
    if videoid.mediatype == common.VideoId.SHOW and not common_data['marks_tvshow_started']:
        infos.pop('PlayCount', None)
    list_item.setInfo('video', infos)
    list_item.setArt(get_art(videoid, art_item or item or {}, common_data['profile_language_code'],
                             delayed_db_op=True))


def _add_supplemental_plot_info(infos, item, common_data):
    """Add supplemental info to plot description"""
    suppl_info = []
    suppl_msg = None
    suppl_dp = item.get('dpSupplementalMessage', {})
    if suppl_dp.get('$type') != 'error':
        suppl_msg = suppl_dp.get('value')
    if suppl_msg:
        # Short information about future release of tv show episode/season or movie
        suppl_info.append(suppl_msg)
    else:
        # If there is no supplemental message, we provide a possible release date info
        avail_data = item.get('availability', {}).get('value', {})
        avail_text = avail_data.get('availabilityDate')
        if avail_text:
            avail_timestamp = avail_data.get('availabilityStartTime', 0) / 1000
            if avail_timestamp > time.time():
                suppl_info.append(common.get_local_string(30620).format(avail_text))
    # The 'sequiturEvidence' dict can be of type 'hook' or 'watched'
    sequitur_evid = item.get('sequiturEvidence', {}).get('value')
    if sequitur_evid and sequitur_evid.get('type') == 'hook':
        hook_value = sequitur_evid.get('value')
        if hook_value:
            # Short info about the actors career/awards and similarities/connections with others films or tv shows
            suppl_info.append(hook_value['text'])
    suppl_text = '[CR][CR]'.join(suppl_info)
    if suppl_text:
        suppl_text = _colorize_text(common_data.get('supplemental_info_color',
                                                    get_color_name(G.ADDON.getSettingInt('supplemental_info_color'))),
                                    suppl_text)
        plot = infos.get('Plot', '')
        if plot:
            plot += '[CR][CR]'
        plotoutline = infos.get('PlotOutline', '')
        if plotoutline:
            plotoutline += '[CR][CR]'
        infos.update({'Plot': plot + suppl_text})
        infos.update({'PlotOutline': plotoutline + suppl_text})


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


def parse_info(videoid, item, raw_data, common_data):
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
        infos['TVShowTitle'] = raw_data['videos'][videoid.tvshowid]['title'].get('value', '')
    if item.get('watched', {}).get('value'):
        infos['PlayCount'] = 1

    infos.update(_parse_atomic_infos(item))
    infos.update(_parse_referenced_infos(item, raw_data))
    infos.update(_parse_tags(item))

    if videoid.mediatype == common.VideoId.EPISODE:
        # 01/12/2022: The 'delivery' info in the episode data are wrong (e.g. wrong resolution)
        # as workaround we get the 'delivery' info from tvshow data
        delivery_info = raw_data['videos'][videoid.tvshowid]['delivery'].get('value', '')
    else:
        delivery_info = item.get('delivery', {}).get('value')
    return infos, get_quality_infos(delivery_info, common_data.get('video_codec_hint', get_video_codec_hint()))


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
    return {target: [person['name']['value']
                     for _, person
                     in paths.resolve_refs(item.get(source, {}), raw_data)]
            for target, source in paths.REFERENCE_MAPPINGS.items()}


def _parse_tags(item):
    """Parse the tags"""
    return {'Tag': [tagdef['name']['value']
                    for tagdef
                    in item.get('tags', {}).values()
                    if isinstance(tagdef.get('name', {}), str)]}


def get_quality_infos(delivery, video_codec_hint):
    """Return audio and video quality infolabels"""
    quality_infos = {}
    if delivery:
        if delivery.get('hasUltraHD', False):  # 4k only with HEVC codec
            quality_infos['video'] = {'codec': 'hevc', 'width': 3840, 'height': 2160}
        elif delivery.get('hasHD'):
            quality_infos['video'] = {'codec': video_codec_hint, 'width': 1920, 'height': 1080}
        else:
            quality_infos['video'] = {'codec': video_codec_hint, 'width': 960, 'height': 540}
        quality_infos['audio'] = {'channels': 2 + 4 * delivery.get('has51Audio', False)}
        if G.ADDON.getSettingBool('enable_dolby_sound'):
            if delivery.get('hasDolbyAtmos', False):
                quality_infos['audio']['codec'] = 'truehd'
            else:
                quality_infos['audio']['codec'] = 'eac3'
        else:
            quality_infos['audio']['codec'] = 'aac'
        if delivery.get('hasDolbyVision', False):
            quality_infos['video']['hdrtype'] = 'dolbyvision'
        elif delivery.get('hasHDR', False):
            quality_infos['video']['hdrtype'] = 'hdr10'
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
    video_id = str(video_data['summary']['value']['id'])
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
        credits_offset_val = video_data.get('creditsOffset', {}).get('value')
        if credits_offset_val is not None:
            # To better ensure that a video is marked as watched also when a user do not reach the ending credits
            # we generally lower the watched threshold by 50 seconds for 50 minutes of video (3000 secs)
            lower_value = video_data['runtime']['value'] / 3000 * 50
            watched_threshold = credits_offset_val - lower_value
        else:
            # When missing the value should be only a video of movie type,
            # then we simulate the default Kodi playcount behaviour (playcountminimumpercent)
            watched_threshold = video_data['runtime']['value'] / 100 * 90
        # To avoid asking to the server again the entire list of titles (after watched a video)
        # to get the updated value, we override the value with the value saved in memory (see am_video_events.py)
        try:
            bookmark_position = G.CACHE.get(CACHE_BOOKMARKS, video_id)
        except CacheMiss:
            # NOTE shakti 'bookmarkPosition' tag when it is not set have -1 value
            bookmark_position = video_data['bookmarkPosition'].get('value', 0)
        playcount = 1 if bookmark_position >= watched_threshold else 0
        if playcount == 0 and bookmark_position > 0:
            resume_time = bookmark_position
    else:
        playcount = 1 if is_watched_user_overrided else 0
    # We have to set playcount with setInfo(), because the setProperty('PlayCount', ) have a bug
    # when a item is already watched and you force to set again watched, the override do not work
    list_item.updateInfo({'PlayCount': playcount})
    list_item.setProperty('TotalTime', str(video_data['runtime']['value']))
    list_item.setProperty('ResumeTime', str(resume_time))
