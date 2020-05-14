# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Methods to execute requests to Netflix API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common import cache_utils
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from .exceptions import APIError, MissingCredentialsError, MetadataNotAvailable, CacheMiss
from .paths import EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS, build_paths


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


def login(ask_credentials=True):
    """Perform a login"""
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


def update_lolomo_context(context_name):
    """Update the lolomo list by context"""
    lolomo_root = g.LOCAL_DB.get_value('lolomo_root_id', '', TABLE_SESSION)

    context_index = g.LOCAL_DB.get_value('lolomo_{}_index'.format(context_name.lower()), '', TABLE_SESSION)
    context_id = g.LOCAL_DB.get_value('lolomo_{}_id'.format(context_name.lower()), '', TABLE_SESSION)

    if not context_index:
        common.warn('Update lolomo context {} skipped due to missing lolomo index', context_name)
        return
    path = [['lolomos', lolomo_root, 'refreshListByContext']]
    # The fourth parameter is like a request-id, but it doesn't seem to match to
    # serverDefs/date/requestId of reactContext (g.LOCAL_DB.get_value('request_id', table=TABLE_SESSION))
    # nor to request_id of the video event request
    # has a kind of relationship with renoMessageId suspect with the logblob but i'm not sure because my debug crashed,
    # and i am no longer able to trace the source.
    # I noticed also that this request can also be made with the fourth parameter empty,
    # but it still doesn't update the continueWatching list of lolomo, that is strange because of no error
    params = [common.enclose_quotes(context_id),
              context_index,
              common.enclose_quotes(context_name),
              '']
    # path_suffixs = [
    #    [['trackIds', 'context', 'length', 'genreId', 'videoId', 'displayName', 'isTallRow', 'isShowAsARow',
    #      'impressionToken', 'showAsARow', 'id', 'requestId']],
    #    [{'from': 0, 'to': 100}, 'reference', 'summary'],
    #    [{'from': 0, 'to': 100}, 'reference', 'title'],
    #    [{'from': 0, 'to': 100}, 'reference', 'titleMaturity'],
    #    [{'from': 0, 'to': 100}, 'reference', 'userRating'],
    #    [{'from': 0, 'to': 100}, 'reference', 'userRatingRequestId'],
    #    [{'from': 0, 'to': 100}, 'reference', 'boxarts', '_342x192', 'jpg'],
    #    [{'from': 0, 'to': 100}, 'reference', 'promoVideo']
    # ]
    callargs = {
        'callpaths': path,
        'params': params,
        # 'path_suffixs': path_suffixs
    }
    try:
        response = common.make_http_call('callpath_request', callargs)
        common.debug('refreshListByContext response: {}', response)
        # The call response return the new context id of the previous invalidated lolomo context_id
        # and if path_suffixs is added return also the new video list data
    except Exception:  # pylint: disable=broad-except
        if not common.is_debug_verbose():
            return
        ui.show_notification(title=common.get_local_string(30105),
                             msg='An error prevented the update the lolomo context on netflix',
                             time=10000)


def update_videoid_bookmark(video_id):
    """Update the videoid bookmark position"""
    # You can check if this function works through the official android app
    # by checking if the status bar watched of the video will be updated
    callargs = {
        'callpaths': [['refreshVideoCurrentPositions']],
        'params': ['[' + video_id + ']', '[]'],
    }
    try:
        response = common.make_http_call('callpath_request', callargs)
        common.debug('refreshVideoCurrentPositions response: {}', response)
    except Exception:  # pylint: disable=broad-except
        ui.show_notification(title=common.get_local_string(30105),
                             msg='An error prevented the update the status watched on netflix',
                             time=10000)


@common.time_execution(immediate=False)
def get_video_raw_data(videoids, custom_partial_path=None):  # Do not apply cache to this method
    """Retrieve raw data for specified video id's"""
    video_ids = [int(videoid.value) for videoid in videoids]
    common.debug('Requesting video raw data for {}', video_ids)
    if not custom_partial_path:
        paths = build_paths(['videos', video_ids], EPISODES_PARTIAL_PATHS)
        if videoids[0].mediatype == common.VideoId.EPISODE:
            paths.extend(build_paths(['videos', int(videoids[0].tvshowid)], ART_PARTIAL_PATHS + [['title']]))
    else:
        paths = build_paths(['videos', video_ids], custom_partial_path)
    return common.make_call('path_request', paths)


@catch_api_errors
@common.time_execution(immediate=False)
def rate(videoid, rating):
    """Rate a video on Netflix"""
    common.debug('Rating {} as {}', videoid.value, rating)
    # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
    rating = min(10, max(0, rating)) / 2
    common.make_call(
        'post',
        {'endpoint': 'set_video_rating',
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
        {'endpoint': 'set_thumb_rating',
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
def update_my_list(videoid, operation, params):
    """Call API to update my list with either add or remove action"""
    common.debug('My List: {} {}', operation, videoid)
    common.make_call(
        'post',
        {'endpoint': 'update_my_list',
         'data': {
             'operation': operation,
             'videoId': videoid.value}})
    ui.show_notification(common.get_local_string(30119))
    _update_mylist_cache(videoid, operation, params)


def _update_mylist_cache(videoid, operation, params):
    """Update the my list cache to speeding up page load"""
    # Avoids making a new request to the server to request the entire list updated
    perpetual_range_start = params.get('perpetual_range_start')
    mylist_identifier = 'mylist'
    if perpetual_range_start and perpetual_range_start != 'None':
        mylist_identifier += '_' + perpetual_range_start
    if operation == 'remove':
        try:
            video_list_sorted_data = g.CACHE.get(cache_utils.CACHE_MYLIST, mylist_identifier)
            del video_list_sorted_data.videos[videoid.value]
            g.CACHE.add(cache_utils.CACHE_MYLIST, mylist_identifier, video_list_sorted_data)
        except CacheMiss:
            pass
        try:
            my_list_videoids = g.CACHE.get(cache_utils.CACHE_MYLIST, 'my_list_items')
            my_list_videoids.remove(videoid)
            g.CACHE.add(cache_utils.CACHE_MYLIST, 'my_list_items', my_list_videoids)
        except CacheMiss:
            pass
    else:
        try:
            common.make_call('add_videoids_to_video_list_cache', {'cache_bucket': cache_utils.CACHE_MYLIST,
                                                                  'cache_identifier': mylist_identifier,
                                                                  'video_ids': [videoid.value]})
        except CacheMiss:
            pass
        try:
            my_list_videoids = g.CACHE.get(cache_utils.CACHE_MYLIST, 'my_list_items')
            my_list_videoids.append(videoid)
            g.CACHE.add(cache_utils.CACHE_MYLIST, 'my_list_items', my_list_videoids)
        except CacheMiss:
            pass


@common.time_execution(immediate=False)
def get_metadata(videoid, refresh=False):
    """Retrieve additional metadata for the given VideoId"""
    metadata_data = {}, None
    # Delete the cache if we need to refresh the all metadata
    if refresh:
        videoid_cache = (videoid.derive_parent(0)
                         if videoid.mediatype in [common.VideoId.EPISODE, common.VideoId.SEASON]
                         else videoid)
        g.CACHE.delete(cache_utils.CACHE_METADATA, str(videoid_cache))
    if videoid.mediatype not in [common.VideoId.EPISODE, common.VideoId.SEASON]:
        # videoid of type tvshow, movie, supplemental
        metadata_data = _metadata(video_id=videoid), None
    elif videoid.mediatype == common.VideoId.SEASON:
        metadata_data = _metadata(video_id=videoid.derive_parent(None)), None
    else:  # it is an episode
        try:
            metadata_data = _episode_metadata(videoid)
        except KeyError as exc:
            # Episode metadata may not exist if its a new episode and cached
            # data is outdated. In this case, delete the cache entry and
            # try again safely (if it doesn't exist this time, there is no
            # metadata for the episode, so we assign an empty dict).
            common.debug('find_episode_metadata raised an error: {}, refreshing cache', exc)
            try:
                metadata_data = _episode_metadata(videoid, refresh_cache=True)
            except KeyError as exc:
                common.error('Episode metadata not found, find_episode_metadata raised an error: {}', exc)
    return metadata_data


def _episode_metadata(videoid, refresh_cache=False):
    tvshow_videoid = videoid.derive_parent(0)
    if refresh_cache:
        g.CACHE.delete(cache_utils.CACHE_METADATA, str(tvshow_videoid))
    show_metadata = _metadata(video_id=tvshow_videoid)
    episode_metadata, season_metadata = common.find_episode_metadata(videoid, show_metadata)
    return episode_metadata, season_metadata, show_metadata


@common.time_execution(immediate=False)
@cache_utils.cache_output(cache_utils.CACHE_METADATA, identify_from_kwarg_name='video_id')
def _metadata(video_id):
    """Retrieve additional metadata for a video.
    This is a separate method from get_metadata(videoid) to work around caching issues
    when new episodes are added to a tv show by Netflix."""
    import time
    common.debug('Requesting metadata for {}', video_id)
    # Always use params 'movieid' to all videoid identifier
    ipc_call = common.make_http_call if g.IS_SERVICE else common.make_call
    metadata_data = ipc_call(
        'get',
        {
            'endpoint': 'metadata',
            'params': {'movieid': video_id.value,
                       '_': int(time.time())}
        })
    if not metadata_data:
        # This return empty
        # - if the metadata is no longer available
        # - if it has been exported a tv show/movie from a specific language profile that is not
        #   available using profiles with other languages
        raise MetadataNotAvailable
    return metadata_data['video']


@common.time_execution(immediate=False)
def get_parental_control_data(password):
    """Get the parental control data"""
    return common.make_call('parental_control_data', {'password': password})


@common.time_execution(immediate=False)
def set_parental_control_data(data):
    """Set the parental control data"""
    try:
        common.make_call(
            'post',
            {'endpoint': 'content_restrictions',
             'data': {'action': 'update',
                      'authURL': data['token'],
                      'experience': data['experience'],
                      'guid': data['guid'],
                      'maturity': data['maturity']}}
        )
        return True
    except Exception as exc:  # pylint: disable=broad-except
        common.error('Api call profile_hub raised an error: {}', exc)
    return False


@common.time_execution(immediate=False)
def verify_pin(pin):
    """Send adult PIN to Netflix and verify it."""
    try:
        return common.make_call(
            'post',
            {'endpoint': 'pin_service',
             'data': {'pin': pin}}
        ).get('success', False)
    except Exception:  # pylint: disable=broad-except
        return False


@common.time_execution(immediate=False)
def verify_profile_lock(guid, pin):
    """Send profile PIN to Netflix and verify it."""
    try:
        return common.make_call(
            'post',
            {'endpoint': 'profile_lock',
             'data': {'pin': pin,
                      'action': 'verify',
                      'guid': guid}}
        ).get('success', False)
    except Exception:  # pylint: disable=broad-except
        return False
