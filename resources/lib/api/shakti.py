# -*- coding: utf-8 -*-
"""Access to Netflix's Shakti API"""
from __future__ import unicode_literals

from functools import wraps

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.kodi.ui as ui

from .data_types import (LoLoMo, VideoList, VideoListSorted, SeasonList, EpisodeList,
                         SearchVideoList, CustomVideoList)
from .paths import (VIDEO_LIST_PARTIAL_PATHS, SEASONS_PARTIAL_PATHS,
                    EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS,
                    GENRE_PARTIAL_PATHS, RANGE_SELECTOR)
from .exceptions import (InvalidVideoListTypeError, LoginFailedError, APIError,
                         NotLoggedInError, MissingCredentialsError)


def catch_api_errors(func):
    """Decorator that catches API errors and displays a notification"""
    # pylint: disable=missing-docstring
    @wraps(func)
    def api_error_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as exc:
            ui.show_notification(common.get_local_string(30118).format(exc))
    return api_error_wrapper


def activate_profile(profile_id):
    """Activate the profile with the given ID"""
    if common.make_call('activate_profile', profile_id):
        g.CACHE.invalidate()


def logout():
    """Logout of the current account"""
    try:
        common.make_call('logout')
        g.CACHE.invalidate()
    except (MissingCredentialsError, NotLoggedInError):
        ui.show_notification(common.get_local_string(30112))


def login():
    """Perform a login"""
    g.CACHE.invalidate()
    try:
        ui.ask_credentials()
        common.make_call('login')
    except (MissingCredentialsError, LoginFailedError) as exc:
        msg = 30009 if isinstance(exc, LoginFailedError) else 30112
        ui.show_notification(common.get_local_string(msg))
        return False
    return True


@common.time_execution(immediate=False)
def profiles():
    """Retrieve the list of available user profiles"""
    return common.make_call('list_profiles')


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON, fixed_identifier='root_lists')
def root_lists():
    """Retrieve initial video lists to display on homepage"""
    common.debug('Requesting root lists from API')
    return LoLoMo(common.make_call(
        'path_request',
        [['lolomo',
          {'from': 0, 'to': 40},
          ['displayName', 'context', 'id', 'index', 'length', 'genreId']]] +
        # Titles of first 4 videos in each video list
        [['lolomo',
          {'from': 0, 'to': 40},
          {'from': 0, 'to': 3}, 'reference', ['title', 'summary']]] +
        # Art for first video in each video list
        # (will be displayed as video list art)
        build_paths(['lolomo',
                     {'from': 0, 'to': 40},
                     {'from': 0, 'to': 0}, 'reference'],
                    ART_PARTIAL_PATHS)))


@cache.cache_output(g, cache.CACHE_COMMON, identifying_param_index=0,
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


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON, identifying_param_index=0,
                    identifying_param_name='list_id')
def video_list(list_id):
    """Retrieve a single video list
    this type of request seems to have results fixed at ~40 from netflix
    and the 'length' tag never return to the actual total count of the elements
    """
    common.debug('Requesting video list {}'.format(list_id))
    return VideoList(common.make_call(
        'perpetual_path_request',
        {
            'path_type': 'videolist',
            'paths':
                build_paths(['lists', list_id, RANGE_SELECTOR, 'reference'],
                            VIDEO_LIST_PARTIAL_PATHS),
            'length_params1': list_id
        }))


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON, identifying_param_index=1,
                    identifying_param_name='context_id')
def video_list_sorted(context_name, context_id=None):
    """Retrieve a single video list sorted
    this type of request allows to obtain more than ~40 results
    """
    common.debug('Requesting video list sorted {}'.format(context_id))
    call_data = {'length_params1': context_name}
    request_sort_order = 'az'
    if context_id:
        call_data['path_type'] = 'videolist_wid_sorted'
        call_data['paths'] = build_paths([context_name, context_id, request_sort_order, RANGE_SELECTOR],
                                         VIDEO_LIST_PARTIAL_PATHS)
        call_data['length_params2'] = context_id
    else:
        call_data['path_type'] = 'videolist_sorted'
        call_data['paths'] = build_paths([context_name, request_sort_order, RANGE_SELECTOR],
                                         VIDEO_LIST_PARTIAL_PATHS)
    return VideoListSorted(common.make_call(
        'perpetual_path_request',call_data), context_name, context_id)


@common.time_execution(immediate=False)
def custom_video_list(video_ids):
    """Retrieve a video list which contains the videos specified by
    video_ids"""
    common.debug('Requesting custom video list with {} videos'
                 .format(len(video_ids)))
    return CustomVideoList(common.make_call(
        'path_request',
        build_paths(['videos', video_ids], VIDEO_LIST_PARTIAL_PATHS)))


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_GENRES, identifying_param_index=0,
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
                    [['title', 'summary']] + ART_PARTIAL_PATHS) +
        # IDs and names of subgenres
        [['genres', genre_id, 'subgenres', {'from': 0, 'to': 30},
          ['id', 'name']]]))

@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON)
def seasons(videoid):
    """Retrieve seasons of a TV show"""
    if videoid.mediatype != common.VideoId.SHOW:
        raise common.InvalidVideoId('Cannot request season list for {}'
                                    .format(videoid))
    common.debug('Requesting season list for show {}'.format(videoid))
    return SeasonList(
        videoid,
        common.make_call(
            'perpetual_path_request',
            {
                'path_type': 'seasonlist',
                'paths': build_paths(['videos', videoid.tvshowid],
                                     SEASONS_PARTIAL_PATHS),
                'length_params1': videoid.tvshowid
            }))


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON)
def episodes(videoid):
    """Retrieve episodes of a season"""
    if videoid.mediatype != common.VideoId.SEASON:
        raise common.InvalidVideoId('Cannot request episode list for {}'
                                    .format(videoid))
    common.debug('Requesting episode list for {}'.format(videoid))
    return EpisodeList(
        videoid,
        common.make_call(
            'perpetual_path_request',
            {
                'path_type': 'episodelist',
                'paths':
                    [['seasons', videoid.seasonid, 'summary']] +
                    build_paths(
                        ['seasons', videoid.seasonid, 'episodes',
                         RANGE_SELECTOR],
                        EPISODES_PARTIAL_PATHS) +
                    build_paths(
                        ['videos', videoid.tvshowid],
                        ART_PARTIAL_PATHS + [['title']]),
                'length_params1': videoid.seasonid
            }))


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_COMMON)
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


@cache.cache_output(g, cache.CACHE_COMMON,
                    fixed_identifier='my_list_items')
def mylist_items():
    """Return a list of all the items currently contained in my list"""
    common.debug('Try to perform a request to get the id list of the videos in my list')
    try:
        return [video_id
                for video_id, video in
                video_list_sorted(g.MAIN_MENU_ITEMS['myList']['request_context_name']).videos.iteritems()
                if video['queue'].get('inQueue', False)]
    except InvalidVideoListTypeError:
        return []


@catch_api_errors
@common.time_execution(immediate=False)
def rate(videoid, rating):
    """Rate a video on Netflix"""
    common.debug('Rating {} as {}'.format(videoid.value, rating))
    # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
    rating = min(10, max(0, rating)) / 2
    common.make_call(
        'post',
        {'component': 'set_video_rating',
         'params': {
             'titleid': videoid.value,
             'rating': rating}})
    ui.show_notification(common.get_local_string(30127).format(rating * 2))


@catch_api_errors
@common.time_execution(immediate=False)
def update_my_list(videoid, operation):
    """Call API to update my list with either add or remove action"""
    common.debug('My List: {} {}'.format(operation, videoid))
    # We want the tvshowid for seasons and episodes (such videoids may be
    # passed by the mylist/library auto-sync feature)
    videoid_value = (videoid.movieid
                     if videoid.mediatype == common.VideoId.MOVIE
                     else videoid.tvshowid)
    common.make_call(
        'post',
        {'component': 'update_my_list',
         'data': {
             'operation': operation,
             'videoId': int(videoid_value)}})
    ui.show_notification(common.get_local_string(30119))
    try:
        g.CACHE.invalidate_entry(cache.CACHE_COMMON, list_id_for_type('queue'))
    except InvalidVideoListTypeError:
        pass
    g.CACHE.invalidate_entry(cache.CACHE_COMMON, 'queue')
    g.CACHE.invalidate_entry(cache.CACHE_COMMON, 'my_list_items')
    g.CACHE.invalidate_entry(cache.CACHE_COMMON, 'root_lists')


@common.time_execution(immediate=False)
def metadata(videoid):
    """Retrieve additional metadata for the given VideoId"""
    if videoid.mediatype != common.VideoId.EPISODE:
        return _metadata(videoid.value), None

    try:
        return _episode_metadata(videoid)
    except KeyError as exc:
        # Episode metadata may not exist if its a new episode and cached
        # data is outdated. In this case, invalidate the cache entry and
        # try again safely (if it doesn't exist this time, there is no
        # metadata for the episode, so we assign an empty dict).
        common.debug('{}, refreshing cache'.format(exc))
        g.CACHE.invalidate_entry(cache.CACHE_METADATA, videoid.tvshowid)
        try:
            return _episode_metadata(videoid)
        except KeyError as exc:
            common.error(exc)
            return {}, None


@common.time_execution(immediate=False)
def _episode_metadata(videoid):
    show_metadata = _metadata(videoid.tvshowid)
    episode_metadata, season_metadata = common.find_episode_metadata(
        videoid, show_metadata)
    return episode_metadata, season_metadata, show_metadata


@common.time_execution(immediate=False)
@cache.cache_output(g, cache.CACHE_METADATA, 0, 'video_id',
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
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


@common.time_execution(immediate=False)
def search(search_term):
    """Retrieve a video list of search results"""
    common.debug('Searching for {}'.format(search_term))
    base_path = ['search', 'byTerm', '|' + search_term, 'titles', 40]
    return SearchVideoList(common.make_call(
        'path_request',
        [base_path + ['referenceId', 'id', 'length', 'name', 'trackIds',
                      'requestId', 'regularSynopsis', 'evidence']] +
        build_paths(base_path + [{'from': 0, 'to': 40}, 'reference'],
                    VIDEO_LIST_PARTIAL_PATHS)))


@common.time_execution(immediate=False)
def verify_pin(pin):
    """Send adult PIN to Netflix and verify it."""
    # pylint: disable=broad-except
    try:
        return common.make_call(
            'post',
            {'component': 'adult_pin',
             'data': {
                 'pin': pin}}).get('success', False)
    except Exception:
        return False


def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path
    with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    return paths
