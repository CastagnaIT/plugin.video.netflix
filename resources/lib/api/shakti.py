# -*- coding: utf-8 -*-
"""Access to Netflix's Shakti API"""
from __future__ import unicode_literals

import json

import resources.lib.common as common
from resources.lib.services.nfsession import NetflixSession
from resources.lib.cache import (cache_output, invalidate_cache, CACHE_COMMON,
                                 CACHE_VIDEO_LIST, CACHE_SEASONS,
                                 CACHE_EPISODES, CACHE_METADATA)

from .data_types import LoLoMo, VideoList, SeasonList, EpisodeList
from .paths import (VIDEO_LIST_PARTIAL_PATHS, SEASONS_PARTIAL_PATHS,
                    EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS)

class InvalidVideoListTypeError(Exception):
    """No video list of a given was available"""
    pass

def activate_profile(profile_id):
    """Activate the profile with the given ID"""
    invalidate_cache()
    common.make_call(NetflixSession.activate_profile, profile_id)

def logout():
    """Logout of the current account"""
    invalidate_cache()
    common.make_call(NetflixSession.logout)

def profiles():
    """Retrieve the list of available user profiles"""
    return common.make_call(NetflixSession.list_profiles)

@cache_output(CACHE_COMMON, fixed_identifier='root_lists')
def root_lists():
    """Retrieve initial video lists to display on homepage"""
    common.debug('Requesting root lists from API')
    return LoLoMo(common.make_call(
        NetflixSession.path_request,
        [['lolomo',
          {'from': 0, 'to': 40},
          ['displayName', 'context', 'id', 'index', 'length']]]))

@cache_output(CACHE_COMMON, 0, 'list_type')
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

@cache_output(CACHE_VIDEO_LIST, 0, 'list_id')
def video_list(list_id):
    """Retrieve a single video list"""
    common.debug('Requesting video list {}'.format(list_id))
    return VideoList(common.make_call(
        NetflixSession.path_request,
        build_paths(['lists', [list_id], {'from': 0, 'to': 40}, 'reference'],
                    VIDEO_LIST_PARTIAL_PATHS)))

@cache_output(CACHE_SEASONS, 0, 'tvshow_id')
def seasons(tvshow_id):
    """Retrieve seasons of a TV show"""
    common.debug('Requesting season list for show {}'.format(tvshow_id))
    return SeasonList(
        tvshow_id,
        common.make_call(
            NetflixSession.path_request,
            build_paths(['videos', tvshow_id],
                        SEASONS_PARTIAL_PATHS)))

@cache_output(CACHE_EPISODES, 1, 'season_id')
def episodes(tvshow_id, season_id):
    """Retrieve episodes of a season"""
    common.debug('Requesting episode list for show {}, season {}'
                 .format(tvshow_id, season_id))
    return EpisodeList(
        tvshow_id,
        season_id,
        common.make_call(
            NetflixSession.path_request,
            build_paths(['seasons', season_id, 'episodes',
                         {'from': 0, 'to': 40}],
                        EPISODES_PARTIAL_PATHS) +
            build_paths(['videos', tvshow_id],
                        ART_PARTIAL_PATHS +
                        [['title']])))

def browse_genre(genre_id):
    """Retrieve video lists for a genre"""
    pass

@cache_output(CACHE_METADATA, 0, 'video_id', ttl=common.CACHE_METADATA_TTL,
              to_disk=True)
def metadata(video_id):
    """Retrieve additional metadata for a video"""
    common.debug('Requesting metdata for {}'.format(video_id))
    return common.make_call(
        NetflixSession.get,
        {
            'component': 'metadata',
            'req_type': 'api',
            'params': {'movieid': video_id}
        })

def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path
    with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    common.debug(json.dumps(paths))
    return paths
