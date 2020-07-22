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

from future.utils import itervalues

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common import cache_utils
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from .exceptions import APIError, MissingCredentialsError, CacheMiss
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
    common.make_call('logout')


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


def update_loco_context(context_name):
    """Update a loco list by context"""
    # This api seem no more needed to update the continueWatching loco list
    loco_root = g.LOCAL_DB.get_value('loco_root_id', '', TABLE_SESSION)

    context_index = g.LOCAL_DB.get_value('loco_{}_index'.format(context_name.lower()), '', TABLE_SESSION)
    context_id = g.LOCAL_DB.get_value('loco_{}_id'.format(context_name.lower()), '', TABLE_SESSION)

    if not context_index:
        common.warn('Update loco context {} skipped due to missing loco index', context_name)
        return
    path = [['locos', loco_root, 'refreshListByContext']]
    # After the introduction of LoCo, the following notes are to be reviewed (refers to old LoLoMo):
    #   The fourth parameter is like a request-id, but it doesn't seem to match to
    #   serverDefs/date/requestId of reactContext (g.LOCAL_DB.get_value('request_id', table=TABLE_SESSION))
    #   nor to request_id of the video event request,
    #   has a kind of relationship with renoMessageId suspect with the logblob but i'm not sure because my debug crashed
    #   and i am no longer able to trace the source.
    #   I noticed also that this request can also be made with the fourth parameter empty.
    params = [common.enclose_quotes(context_id),
              context_index,
              common.enclose_quotes(context_name),
              '']
    # path_suffixs = [
    #    [{'from': 0, 'to': 100}, 'itemSummary'],
    #    [['componentSummary']]
    # ]
    callargs = {
        'callpaths': path,
        'params': params,
        # 'path_suffixs': path_suffixs
    }
    try:
        response = common.make_http_call('callpath_request', callargs)
        common.debug('refreshListByContext response: {}', response)
        # The call response return the new context id of the previous invalidated loco context_id
        # and if path_suffixs is added return also the new video list data
    except Exception:  # pylint: disable=broad-except
        if not common.is_debug_verbose():
            return
        ui.show_notification(title=common.get_local_string(30105),
                             msg='An error prevented the update the loco context on netflix',
                             time=10000)


def update_videoid_bookmark(video_id):
    """Update the videoid bookmark position"""
    # You can check if this function works through the official android app
    # by checking if the red status bar of watched time position appears and will be updated,
    # or also if continueWatching list will be updated (e.g. try to play a new tvshow not contained in the "my list")
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
        'post_safe',
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
        'post_safe',
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
        'post_safe',
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
        common.make_call('add_videoids_to_video_list_cache', {'cache_bucket': cache_utils.CACHE_MYLIST,
                                                              'cache_identifier': mylist_identifier,
                                                              'video_ids': [videoid.value]})
        try:
            my_list_videoids = g.CACHE.get(cache_utils.CACHE_MYLIST, 'my_list_items')
            my_list_videoids.append(videoid)
            g.CACHE.add(cache_utils.CACHE_MYLIST, 'my_list_items', my_list_videoids)
        except CacheMiss:
            pass


@common.time_execution(immediate=False)
def get_parental_control_data(password):
    """Get the parental control data"""
    return common.make_call('parental_control_data', {'password': password})


@common.time_execution(immediate=False)
def set_parental_control_data(data):
    """Set the parental control data"""
    try:
        common.make_call(
            'post_safe',
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
            'post_safe',
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
            'post_safe',
            {'endpoint': 'profile_lock',
             'data': {'pin': pin,
                      'action': 'verify',
                      'guid': guid}}
        ).get('success', False)
    except Exception:  # pylint: disable=broad-except
        return False


def get_available_audio_languages():
    """Get the list of available audio languages of videos"""
    call_args = {
        'paths': [['spokenAudioLanguages', {'from': 0, 'to': 25}, ['id', 'name']]]
    }
    response = common.make_call('path_request', call_args)
    lang_list = {}
    for lang_dict in itervalues(response.get('spokenAudioLanguages', {})):
        lang_list[lang_dict['id']] = lang_dict['name']
    return lang_list


def get_available_subtitles_languages():
    """Get the list of available subtitles languages of videos"""
    call_args = {
        'paths': [['subtitleLanguages', {'from': 0, 'to': 25}, ['id', 'name']]]
    }
    response = common.make_call('path_request', call_args)
    lang_list = {}
    for lang_dict in itervalues(response.get('subtitleLanguages', {})):
        lang_list[lang_dict['id']] = lang_dict['name']
    return lang_list


def remove_watched_status(videoid):
    """Request to Netflix service to delete the watched status (delete also the item from "continue watching" list)"""
    # WARNING: THE NF SERVICE MAY TAKE UNTIL TO 24 HOURS TO REMOVE IT
    try:
        data = common.make_call(
            'post_safe',
            {'endpoint': 'viewing_activity',
             'data': {'movieID': videoid.value,
                      'seriesAll': videoid.mediatype == common.VideoId.SHOW,
                      'guid': g.LOCAL_DB.get_active_profile_guid()}}
        )
        return data.get('status', False)
    except Exception as exc:  # pylint: disable=broad-except
        common.error('remove_watched_status raised this error: {}', exc)
        return False


def get_metadata(videoid, refresh=False):
    return common.make_call('get_metadata', {'videoid': videoid.to_path(),
                                             'refresh': refresh})


def get_mylist_videoids_profile_switch():
    return common.make_call('get_mylist_videoids_profile_switch')
