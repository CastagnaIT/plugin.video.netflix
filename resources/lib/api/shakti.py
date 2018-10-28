# -*- coding: utf-8 -*-
"""Access to Netflix's Shakti API"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.cache as cache

from .data_types import LoLoMo, VideoList, SeasonList, EpisodeList
from .paths import (VIDEO_LIST_PARTIAL_PATHS, SEASONS_PARTIAL_PATHS,
                    EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS,
                    GENRE_PARTIAL_PATHS)

class InvalidVideoListTypeError(Exception):
    """No video list of a given was available"""
    pass

def activate_profile(profile_id):
    """Activate the profile with the given ID"""
    cache.invalidate_cache()
    common.make_call('activate_profile', profile_id)

def logout():
    """Logout of the current account"""
    cache.invalidate_cache()
    common.make_call('logout')

def login():
    """Perform a login"""
    cache.invalidate_cache()
    common.make_call('login')

def profiles():
    """Retrieve the list of available user profiles"""
    return common.make_call('list_profiles')

@cache.cache_output(cache.CACHE_COMMON, fixed_identifier='root_lists')
def root_lists():
    """Retrieve initial video lists to display on homepage"""
    common.debug('Requesting root lists from API')
    return LoLoMo(common.make_call(
        'path_request',
        [['lolomo',
          {'from': 0, 'to': 35},
          ['displayName', 'context', 'id', 'index', 'length', 'genreId']]] +
        # Titles and art of first 4 videos in each video list
        build_paths(['lolomo', {'from': 0, 'to': 35},
                     {'from': 0, 'to': 3}, 'reference'],
                    [['title']] + ART_PARTIAL_PATHS)))

@cache.cache_output(cache.CACHE_COMMON, identifying_param_index=0,
                    identifying_param_name='list_type')
def list_id_for_type(list_type):
    """Return the dynamic video list ID for a video list of known type"""
    try:
        list_id = next(root_lists().lists_by_context(list_type))[0]
    except StopIteration:
        raise InvalidVideoListTypeError(
            'No lists of type {} available'.format(list_type))
    common.debug(
        'Resolved list ID for {} to {}'.format(list_type, list_id))
    return list_id

@cache.cache_output(cache.CACHE_COMMON, identifying_param_index=0,
                    identifying_param_name='list_id')
def video_list(list_id):
    """Retrieve a single video list"""
    common.debug('Requesting video list {}'.format(list_id))
    return VideoList(common.make_call(
        'path_request',
        [['lists', [list_id], 'displayName']] +
        build_paths(['lists', [list_id], {'from': 0, 'to': 40}, 'reference'],
                    VIDEO_LIST_PARTIAL_PATHS)))

@cache.cache_output(cache.CACHE_GENRES, identifying_param_index=0,
                    identifying_param_name='genre_id')
def genre(genre_id):
    """Retrieve LoLoMos for the given genre"""
    common.debug('Requesting LoLoMos for genre {}'.format(genre_id))
    return LoLoMo(common.make_call(
        'path_request',
        build_paths(['genres', genre_id, 'rw'], GENRE_PARTIAL_PATHS) +
        # Titles and art of standard lists' items
        build_paths(['genres', genre_id, 'rw',
                     {"from": 0, "to": 50},
                     {"from": 0, "to": 3}, "reference"],
                    [['title']] + ART_PARTIAL_PATHS) +
        # IDs and names of subgenres
        [['genres', genre_id, 'subgenres', {'from': 0, 'to': 30},
          ['id', 'name']]]))

@cache.cache_output(cache.CACHE_COMMON)
def seasons(videoid):
    """Retrieve seasons of a TV show"""
    if videoid.mediatype != common.VideoId.SHOW:
        raise common.InvalidVideoId('Cannot request season list for {}'
                                    .format(videoid))
    common.debug('Requesting season list for show {}'.format(videoid))
    return SeasonList(
        videoid,
        common.make_call(
            'path_request',
            build_paths(['videos', videoid.tvshowid],
                        SEASONS_PARTIAL_PATHS)))

@cache.cache_output(cache.CACHE_COMMON)
def episodes(videoid):
    """Retrieve episodes of a season"""
    if videoid.mediatype != common.VideoId.SEASON:
        raise common.InvalidVideoId('Cannot request episode list for {}'
                                    .format(videoid))
    common.debug('Requesting episode list for {}'.format(videoid))
    return EpisodeList(
        videoid,
        common.make_call(
            'path_request',
            [['seasons', videoid.seasonid, 'summary']] +
            build_paths(['seasons', videoid.seasonid, 'episodes',
                         {'from': 0, 'to': 40}],
                        EPISODES_PARTIAL_PATHS) +
            build_paths(['videos', videoid.tvshowid],
                        ART_PARTIAL_PATHS +
                        [['title']])))

@cache.cache_output(cache.CACHE_COMMON)
def single_info(videoid):
    """Retrieve info for a single episode"""
    if videoid.mediatype not in [common.VideoId.EPISODE, common.VideoId.MOVIE]:
        raise common.InvalidVideoId('Cannot request info for {}'
                                    .format(videoid))
    common.debug('Requesting info for {}'.format(videoid))
    paths = build_paths(['videos', videoid.value], EPISODES_PARTIAL_PATHS)
    if videoid.mediatype == common.VideoId.EPISODE:
        paths.extend(build_paths(['videos', videoid.tvshowid],
                                 ART_PARTIAL_PATHS + [['title']]))
    return common.make_call('path_request', paths)

@cache.cache_output(cache.CACHE_COMMON, fixed_identifier='my_list_items')
def mylist_items():
    """Return a list of all the items currently contained in my list"""
    return [video_id
            for video_id, video in video_list(
                list_id_for_type('queue')).videos.iteritems()
            if video['queue'].get('inQueue', False)]

def rate(videoid, rating):
    """Rate a video on Netflix"""
    common.debug('Rating {} as {}'.format(videoid.value, rating))
    # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
    rating = min(10, max(0, rating)) / 2
    common.make_call(
        'post',
        {'component': 'set_video_rating',
         'headers': {
             'Content-Type': 'application/json',
             'Accept': 'application/json, text/javascript, */*'},
         'params': {
             'titleid': videoid.value,
             'rating': rating}})

def add_to_list(videoid):
    """Add a video to my list"""
    common.debug('Adding {} to my list'.format(videoid))
    _update_my_list(videoid.value, 'add')

def remove_from_list(videoid):
    """Remove a video from my list"""
    common.debug('Removing {} from my list'.format(videoid))
    _update_my_list(videoid.value, 'remove')

def _update_my_list(video_id, operation):
    """Call API to update my list with either add or remove action"""
    common.make_call(
        'post',
        {'component': 'update_my_list',
         'headers': {
             'Content-Type': 'application/json',
             'Accept': 'application/json, text/javascript, */*'},
         'data': {
             'operation': operation,
             'videoId': int(video_id)}})
    cache.invalidate_entry(cache.CACHE_COMMON,
                           list_id_for_type('queue'))
    cache.invalidate_entry(cache.CACHE_COMMON, 'queue')
    cache.invalidate_entry(cache.CACHE_COMMON, 'my_list_items')
    cache.invalidate_entry(cache.CACHE_COMMON, 'root_lists')

def metadata(videoid):
    """Retrieve additional metadata for the given VideoId"""
    if videoid.mediatype != common.VideoId.EPISODE:
        return _metadata(videoid.value)

    try:
        return common.find_episode(
            videoid.episodeid, _metadata(videoid.tvshowid)['seasons'])
    except KeyError:
        # Episode metadata may not exist if its a new episode and cached
        # data is outdated. In this case, invalidate the cache entry and
        # try again safely (if it doesn't exist this time, there is no
        # metadata for the episode, so we assign an empty dict).
        cache.invalidate_entry(cache.CACHE_METADATA, videoid.tvshowid)
        return common.find_episode(
            videoid.episodeid,
            _metadata(videoid.tvshowid).get('seasons', []),
            raise_exc=False)

@cache.cache_output(cache.CACHE_METADATA, 0, 'video_id',
                    ttl=common.CACHE_METADATA_TTL, to_disk=True)
def _metadata(video_id):
    """Retrieve additional metadata for a video.This is a separate method from
    metadata(videoid) to work around caching issues when new episodes are added
    to a show by Netflix."""
    common.debug('Requesting metdata for {}'.format(video_id))
    return common.make_call(
        'get',
        {
            'component': 'metadata',
            'req_type': 'api',
            'params': {'movieid': video_id}
        })['video']

def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path
    with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    return paths
