# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Access to Netflix's Shakti API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
from functools import wraps
from future.utils import iteritems

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.kodi.ui as ui

from .data_types import (LoLoMo, VideoList, VideoListSorted, SeasonList, EpisodeList,
                         SearchVideoList, CustomVideoList, SubgenreList)
from .paths import (VIDEO_LIST_PARTIAL_PATHS, VIDEO_LIST_BASIC_PARTIAL_PATHS,
                    SEASONS_PARTIAL_PATHS, EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS,
                    GENRE_PARTIAL_PATHS, RANGE_SELECTOR, MAX_PATH_REQUEST_SIZE,
                    TRAILER_PARTIAL_PATHS)
from .exceptions import (InvalidVideoListTypeError, APIError, MissingCredentialsError,
                         MetadataNotAvailable)
from .website import parse_profiles


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


def logout():
    """Logout of the current account"""
    common.make_call('logout', g.BASE_URL)
    g.CACHE.invalidate()


def login(ask_credentials=True):
    """Perform a login"""
    g.CACHE.invalidate()
    try:
        if ask_credentials:
            ui.ask_credentials()
        if not common.make_call('login'):
            # Login not validated
            # ui.show_notification(common.get_local_string(30009))
            return False
        return True
    except MissingCredentialsError:
        # Aborted from user or leave an empty field
        ui.show_notification(common.get_local_string(30112))
        raise


def update_profiles_data():
    """Update the profiles list data to the database"""
    profiles_data = common.make_call(
        'path_request',
        [['profilesList', 'summary'], ['profilesList', 'current', 'summary'],
         ['profilesList', {'to': 5}, 'summary'], ['profilesList', {'to': 5},
                                                  'avatar', 'images', 'byWidth', 320],
         ['lolomo']])
    parse_profiles(profiles_data)


def activate_profile(profile_id):
    """Activate the profile with the given ID"""
    if common.make_call('activate_profile', profile_id):
        g.CACHE.invalidate()


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON, fixed_identifier='root_lists')
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


@cache.cache_output(cache.CACHE_COMMON, identify_from_kwarg_name='list_type')
def list_id_for_type(list_type):
    """Return the dynamic video list ID for a video list of known type"""
    try:
        # list_id = next(root_lists().lists_by_context(list_type))[0]
        list_id = list(root_lists().lists_by_context(list_type))[0][0]
    except StopIteration:
        raise InvalidVideoListTypeError(
            'No lists of type {} available'.format(list_type))
    common.debug('Resolved list ID for {} to {}', list_type, list_id)
    return list_id


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON, identify_from_kwarg_name='list_id')
def video_list(list_id, perpetual_range_start=None):
    """Retrieve a single video list
    some of this type of request seems to have results fixed at ~40 from netflix
    and the 'length' tag never return to the actual total count of the elements
    """
    common.debug('Requesting video list {}', list_id)
    paths = build_paths(['lists', list_id, RANGE_SELECTOR, 'reference'],
                        VIDEO_LIST_PARTIAL_PATHS)
    callargs = {
        'paths': paths,
        'length_params': ['stdlist', ['lists', list_id]],
        'perpetual_range_start': perpetual_range_start
    }
    return VideoList(common.make_call('perpetual_path_request', callargs))


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON, identify_from_kwarg_name='context_id',
                    identify_append_from_kwarg_name='perpetual_range_start')
def video_list_sorted(context_name, context_id=None, perpetual_range_start=None, menu_data=None):
    """Retrieve a single video list sorted
    this type of request allows to obtain more than ~40 results
    """
    common.debug('Requesting video list sorted for context name: "{}", context id: "{}"',
                 context_name, context_id)
    base_path = [context_name]
    response_type = 'stdlist'
    if context_id:
        base_path.append(context_id)
        response_type = 'stdlist_wid'

    # enum order: AZ|ZA|Suggested|Year
    # sort order the "mylist" is supported only in US country, the only way to query is use 'az'
    sort_order_types = ['az', 'za', 'su', 'yr'] if not context_name == 'mylist' else ['az', 'az']
    req_sort_order_type = sort_order_types[
        int(g.ADDON.getSettingInt('_'.join(('menu_sortorder', menu_data['path'][1]))))]
    base_path.append(req_sort_order_type)
    paths = build_paths(base_path + [RANGE_SELECTOR], VIDEO_LIST_PARTIAL_PATHS)
    callargs = {
        'paths': paths,
        'length_params': [response_type, base_path],
        'perpetual_range_start': perpetual_range_start
    }
    return VideoListSorted(common.make_call('perpetual_path_request', callargs),
                           context_name, context_id, req_sort_order_type)


@common.time_execution(immediate=False)
def custom_video_list(video_ids, custom_paths=None):
    """Retrieve a video list which contains the videos specified by
    video_ids"""
    common.debug('Requesting custom video list with {} videos', len(video_ids))
    return CustomVideoList(common.make_call(
        'path_request',
        build_paths(['videos', video_ids],
                    custom_paths if custom_paths else VIDEO_LIST_PARTIAL_PATHS)))


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_GENRES, identify_from_kwarg_name='genre_id')
def genre(genre_id):
    """Retrieve LoLoMos for the given genre"""
    common.debug('Requesting LoLoMos for genre {}', genre_id)
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


def subgenre(genre_id):
    """Retrieve subgenres for the given genre"""
    common.debug('Requesting subgenres for genre {}', genre_id)
    return SubgenreList(common.make_call(
        'path_request',
        [['genres', genre_id, 'subgenres', {'from': 0, 'to': 47}, ['id', 'name']]]))


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON)
def seasons(videoid):
    """Retrieve seasons of a TV show"""
    if videoid.mediatype != common.VideoId.SHOW:
        raise common.InvalidVideoId('Cannot request season list for {}'
                                    .format(videoid))
    common.debug('Requesting season list for show {}', videoid)
    paths = build_paths(['videos', videoid.tvshowid], SEASONS_PARTIAL_PATHS)
    callargs = {
        'paths': paths,
        'length_params': ['stdlist_wid', ['videos', videoid.tvshowid, 'seasonList']]
    }
    return SeasonList(videoid, common.make_call('perpetual_path_request', callargs))


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON, identify_from_kwarg_name='videoid_value',
                    identify_append_from_kwarg_name='perpetual_range_start')
def episodes(videoid, videoid_value, perpetual_range_start=None):  # pylint: disable=unused-argument
    """Retrieve episodes of a season"""
    if videoid.mediatype != common.VideoId.SEASON:
        raise common.InvalidVideoId('Cannot request episode list for {}'
                                    .format(videoid))
    common.debug('Requesting episode list for {}', videoid)
    paths = [['seasons', videoid.seasonid, 'summary']]
    paths.extend(build_paths(['seasons', videoid.seasonid, 'episodes', RANGE_SELECTOR],
                             EPISODES_PARTIAL_PATHS))
    paths.extend(build_paths(['videos', videoid.tvshowid],
                             ART_PARTIAL_PATHS + [['title']]))
    callargs = {
        'paths': paths,
        'length_params': ['stdlist_wid', ['seasons', videoid.seasonid, 'episodes']],
        'perpetual_range_start': perpetual_range_start
    }
    return EpisodeList(videoid, common.make_call('perpetual_path_request', callargs))


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_SUPPLEMENTAL)
def supplemental_video_list(videoid, supplemental_type):
    """Retrieve a supplemental video list"""
    if videoid.mediatype != common.VideoId.SHOW and videoid.mediatype != common.VideoId.MOVIE:
        raise common.InvalidVideoId('Cannot request supplemental list for {}'
                                    .format(videoid))
    common.debug('Requesting supplemental ({}) list for {}', supplemental_type, videoid)
    callargs = build_paths(
        ['videos', videoid.value, supplemental_type,
         {"from": 0, "to": 35}], TRAILER_PARTIAL_PATHS)
    return VideoListSorted(common.make_call('path_request', callargs),
                           'videos', videoid.value, supplemental_type)


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_COMMON)
def single_info(videoid):
    """Retrieve info for a single episode"""
    if videoid.mediatype not in [common.VideoId.EPISODE, common.VideoId.MOVIE,
                                 common.VideoId.SUPPLEMENTAL]:
        raise common.InvalidVideoId('Cannot request info for {}'
                                    .format(videoid))
    common.debug('Requesting info for {}', videoid)
    paths = build_paths(['videos', videoid.value], EPISODES_PARTIAL_PATHS)
    if videoid.mediatype == common.VideoId.EPISODE:
        paths.extend(build_paths(['videos', videoid.tvshowid],
                                 ART_PARTIAL_PATHS + [['title']]))
    return common.make_call('path_request', paths)


def custom_video_list_basicinfo(context_name, switch_profiles=False):
    """
    Retrieve a single video list
    used only to know which videos are in my list without requesting additional information
    """
    common.debug('Requesting custom video list basic info for {}', context_name)
    paths = build_paths([context_name, 'az', RANGE_SELECTOR],
                        VIDEO_LIST_BASIC_PARTIAL_PATHS)
    callargs = {
        'paths': paths,
        'length_params': ['stdlist', [context_name, 'az']],
        'perpetual_range_start': None,
        'no_limit_req': True
    }
    # When the list is empty the server returns an empty response
    callname = 'perpetual_path_request_switch_profiles'\
        if switch_profiles else 'perpetual_path_request'
    path_response = common.make_call(callname, callargs)
    return {} if not path_response else VideoListSorted(path_response, context_name, None, 'az')


# Custom ttl to mylist_items (ttl=10min*60)
# We can not have the changes in real-time, if my-list is modified using other apps,
# every 10 minutes will be updated with the new data
# Never disable the cache to this function, it would cause plentiful requests to the service!
@cache.cache_output(cache.CACHE_COMMON, fixed_identifier='my_list_items', ttl=600)
def mylist_items():
    """Return a list of all the items currently contained in my list"""
    common.debug('Try to perform a request to get the id list of the videos in my list')
    try:
        items = []
        videos = custom_video_list_basicinfo(g.MAIN_MENU_ITEMS['myList']['request_context_name'])
        if videos:
            # pylint: disable=unused-variable
            items = [common.VideoId.from_videolist_item(video)
                     for video_id, video in iteritems(videos.videos)
                     if video['queue'].get('inQueue', False)]
        return items
    except InvalidVideoListTypeError:
        return []


# Used only to library auto update with the sync to Netflix "My List" enabled
# It may happen that the user browses the frontend with a different profile used by library sync,
# and it could cause a wrong query request to nf server.
# So this is an attempt to find a workaround to avoid conflict between frontend navigation
# and the library auto update from the service.
# The scope is (when necessary): switch the profile, get My List items and restore previous
# active profile in a single call to try limit execution in faster way.
def mylist_items_switch_profiles():
    """Return a list of all the items currently contained in my list"""
    common.debug('Perform a request to get the id list'
                 'of the videos in my list with profiles switching')
    try:
        items = []
        videos = custom_video_list_basicinfo(g.MAIN_MENU_ITEMS['myList']['request_context_name'],
                                             True)
        if videos:
            # pylint: disable=unused-variable
            items = [common.VideoId.from_videolist_item(video)
                     for video_id, video in iteritems(videos.videos)
                     if video['queue'].get('inQueue', False)]
        return items
    except InvalidVideoListTypeError:
        return []


@catch_api_errors
@common.time_execution(immediate=False)
def rate(videoid, rating):
    """Rate a video on Netflix"""
    common.debug('Rating {} as {}', videoid.value, rating)
    # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
    rating = min(10, max(0, rating)) / 2
    common.make_call(
        'post',
        {'component': 'set_video_rating',
         'data': {
             'titleId': int(videoid.value),
             'rating': rating}})
    ui.show_notification(common.get_local_string(30127).format(rating * 2))


@catch_api_errors
@common.time_execution(immediate=False)
def rate_thumb(videoid, rating, track_id_jaw):
    """Rate a video on Netflix"""
    common.debug('Thumb rating {} as {}', videoid.value, rating)
    event_uuid = common.get_random_uuid()
    response = common.make_call(
        'post',
        {'component': 'set_thumb_rating',
         'data': {
             'eventUuid': event_uuid,
             'titleId': int(videoid.value),
             'trackId': track_id_jaw,
             'rating': rating,
         }})
    if response.get('status', '') == 'success':
        ui.show_notification(common.get_local_string(30045).split('|')[rating])
    else:
        common.error('Rating thumb error, response detail: {}', response)
        ui.show_error_info('Rating error', 'Error type: {}' + response.get('status', '--'),
                           True, True)


@catch_api_errors
@common.time_execution(immediate=False)
def update_my_list(videoid, operation):
    """Call API to update my list with either add or remove action"""
    common.debug('My List: {} {}', operation, videoid)
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
        # This is necessary to have the my-list menu updated when you open it
        if operation == 'remove':
            # Delete item manually to speedup operations on page load
            cached_video_list_sorted = g.CACHE.get(cache.CACHE_COMMON, 'mylist')
            del cached_video_list_sorted.videos[videoid.value]
        else:
            # Force reload items on page load
            g.CACHE.invalidate_entry(cache.CACHE_COMMON, 'mylist')
    except cache.CacheMiss:
        pass
    # Invalidate my_list_items to allow reload updated my_list_items results when page refresh
    g.CACHE.invalidate_entry(cache.CACHE_COMMON, 'my_list_items')


@common.time_execution(immediate=False)
def metadata(videoid, refresh=False):
    """Retrieve additional metadata for the given VideoId"""
    # Invalidate cache if we need to refresh the all metadata
    if refresh:
        g.CACHE.invalidate_entry(cache.CACHE_METADATA, videoid, True)
    metadata_data = {}, None
    if videoid.mediatype not in [common.VideoId.EPISODE, common.VideoId.SEASON]:
        metadata_data = _metadata(videoid), None
    elif videoid.mediatype == common.VideoId.SEASON:
        metadata_data = _metadata(videoid.derive_parent(None)), None
    else:
        try:
            metadata_data = _episode_metadata(videoid)
        except KeyError as exc:
            # Episode metadata may not exist if its a new episode and cached
            # data is outdated. In this case, invalidate the cache entry and
            # try again safely (if it doesn't exist this time, there is no
            # metadata for the episode, so we assign an empty dict).
            common.debug('{}, refreshing cache', exc)
            g.CACHE.invalidate_entry(cache.CACHE_METADATA, videoid.tvshowid)
            try:
                metadata_data = _episode_metadata(videoid)
            except KeyError as exc:
                common.error(exc)
    return metadata_data


@common.time_execution(immediate=False)
def _episode_metadata(videoid):
    show_metadata = _metadata(videoid)
    episode_metadata, season_metadata = common.find_episode_metadata(
        videoid, show_metadata)
    return episode_metadata, season_metadata, show_metadata


@common.time_execution(immediate=False)
@cache.cache_output(cache.CACHE_METADATA, identify_from_kwarg_name='video_id',
                    ttl=g.CACHE_METADATA_TTL, to_disk=True)
def _metadata(video_id):
    """Retrieve additional metadata for a video.This is a separate method from
    metadata(videoid) to work around caching issues when new episodes are added
    to a show by Netflix."""
    common.debug('Requesting metadata for {}', video_id)
    # Always use params 'movieid' to all videoid identifier
    metadata_data = common.make_call(
        'get',
        {
            'component': 'metadata',
            'req_type': 'api',
            'params': {'movieid': video_id.value}
        })
    if not metadata_data:
        # This return empty
        # - if the metadata is no longer available
        # - if it has been exported a tv show/movie from a specific language profile that is not
        #   available using profiles with other languages
        raise MetadataNotAvailable
    return metadata_data['video']


@common.time_execution(immediate=False)
def search(search_term, perpetual_range_start=None):
    """Retrieve a video list of search results"""
    common.debug('Searching for {}', search_term)
    base_path = ['search', 'byTerm', '|' + search_term, 'titles', MAX_PATH_REQUEST_SIZE]
    paths = [base_path + [['id', 'name', 'requestId']]]
    paths.extend(build_paths(base_path + [RANGE_SELECTOR, 'reference'],
                             VIDEO_LIST_PARTIAL_PATHS))
    callargs = {
        'paths': paths,
        'length_params': ['searchlist', ['search', 'byReference']],
        'perpetual_range_start': perpetual_range_start
    }
    return SearchVideoList(common.make_call('perpetual_path_request', callargs))


@common.time_execution(immediate=False)
def get_parental_control_data(password):
    """Get the parental control data"""
    return common.make_call('parental_control_data', {'password': password})


@common.time_execution(immediate=False)
def set_parental_control_data(data):
    """Set the parental control data"""
    try:
        return common.make_call(
            'post',
            {'component': 'pin_service',
             'data': {'maturityLevel': data['maturity_level'],
                      'password': common.get_credentials().get('password'),
                      'pin': data['pin']}}
        )
    except Exception:  # pylint: disable=broad-except
        return {}


@common.time_execution(immediate=False)
def verify_pin(pin):
    """Send adult PIN to Netflix and verify it."""
    try:
        return common.make_call(
            'post',
            {'component': 'pin_service',
             'data': {'pin': pin}}
        ).get('success', False)
    except Exception:  # pylint: disable=broad-except
        return False


def build_paths(base_path, partial_paths):
    """Build a list of full paths by concatenating each partial path
    with the base path"""
    paths = [base_path + partial_path for partial_path in partial_paths]
    return paths
