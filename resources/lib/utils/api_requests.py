# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Methods to execute requests to Netflix API

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.common import cache_utils
from resources.lib.globals import G
from resources.lib.common.exceptions import LoginError, MissingCredentialsError, CacheMiss, HttpError401
from .api_paths import EPISODES_PARTIAL_PATHS, ART_PARTIAL_PATHS, build_paths
from .logging import LOG, measure_exec_time_decorator


def logout():
    """Logout of the current account"""
    common.make_call('logout')


def login(ask_credentials=True):
    """Perform a login"""
    try:
        credentials = None
        is_login_with_credentials = True
        if ask_credentials:
            is_login_with_credentials = ui.show_yesno_dialog('Login', common.get_local_string(30340),
                                                             yeslabel=common.get_local_string(30341),
                                                             nolabel=common.get_local_string(30342))
            if is_login_with_credentials:
                credentials = {'credentials': ui.ask_credentials()}
        if is_login_with_credentials:
            if common.make_call('login', credentials):
                return True
        else:
            data = common.run_nf_authentication_key()
            if not data:
                raise MissingCredentialsError
            password = ui.ask_for_password()
            if password and common.make_call('login_auth_data', {'data': data, 'password': password}):
                return True
    except MissingCredentialsError:
        # Aborted from user or leave an empty field
        ui.show_notification(common.get_local_string(30112))
        raise
    except LoginError as exc:
        # Login not valid
        ui.show_ok_dialog(common.get_local_string(30008), str(exc))
    return False


@measure_exec_time_decorator()
def get_video_raw_data(videoids, custom_partial_path=None):  # Do not apply cache to this method
    """Retrieve raw data for specified video id's"""
    video_ids = [int(videoid.value) for videoid in videoids]
    LOG.debug('Requesting video raw data for {}', video_ids)
    if not custom_partial_path:
        paths = build_paths(['videos', video_ids], EPISODES_PARTIAL_PATHS)
        if videoids[0].mediatype == common.VideoId.EPISODE:
            paths.extend(build_paths(['videos', int(videoids[0].tvshowid)], ART_PARTIAL_PATHS + [['title']]))
    else:
        paths = build_paths(['videos', video_ids], custom_partial_path)
    return common.make_call('path_request', paths)


@measure_exec_time_decorator()
def rate(videoid, rating):
    """Rate a video on Netflix"""
    LOG.debug('Rating {} as {}', videoid.value, rating)
    # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
    rating = min(10, max(0, rating)) / 2
    common.make_call(
        'post_safe',
        {'endpoint': 'set_video_rating',
         'data': {
             'titleId': int(videoid.value),
             'rating': rating}})
    ui.show_notification(common.get_local_string(30127).format(rating * 2))


@measure_exec_time_decorator()
def rate_thumb(videoid, rating, track_id_jaw):
    """Rate a video on Netflix"""
    LOG.debug('Thumb rating {} as {}', videoid.value, rating)
    event_uuid = common.get_random_uuid()
    common.make_call(
        'post_safe',
        {'endpoint': 'set_thumb_rating',
         'data': {
             'eventUuid': event_uuid,
             'titleId': int(videoid.value),
             'trackId': track_id_jaw,
             'rating': rating,
         }})
    ui.show_notification(common.get_local_string(30045).split('|')[rating])


def update_remindme(operation, videoid, trackid):
    """Call API to update "Remind Me" feature with either add or remove action"""
    cmd = 'addToRemindMeList' if operation == 'add' else 'removeFromRemindMeList'
    call_args = {
        'callpaths': [['videos', videoid.value, cmd]],
        'params': [trackid],
        'path': ['videos', videoid.value, 'inRemindMeList']
    }
    response = common.make_call('callpath_request', call_args)
    LOG.debug('update_remindme response: {}', response)


@measure_exec_time_decorator()
def update_my_list(videoid, operation, params):
    """Call API to update my list with either add or remove action"""
    LOG.debug('My List: {} {}', operation, videoid)
    common.make_call(
        'post_safe',
        {'endpoint': 'update_my_list',
         'data': {
             'operation': operation,
             'videoId': videoid.value}})
    _update_mylist_cache(videoid, operation, params)


def _update_mylist_cache(videoid, operation, params):
    """Update the my list cache to speeding up page load"""
    # Avoids making a new request to the server to request the entire list updated
    perpetual_range_start = params.get('perpetual_range_start')
    mylist_identifier = 'mylist'
    if perpetual_range_start and perpetual_range_start != 'None':
        mylist_identifier += f'_{perpetual_range_start}'
    if operation == 'remove':
        try:
            video_list_sorted_data = G.CACHE.get(cache_utils.CACHE_MYLIST, mylist_identifier)
            del video_list_sorted_data.videos[videoid.value]
            G.CACHE.add(cache_utils.CACHE_MYLIST, mylist_identifier, video_list_sorted_data)
        except CacheMiss:
            pass
        try:
            my_list_videoids = G.CACHE.get(cache_utils.CACHE_MYLIST, 'my_list_items')
            my_list_videoids.remove(videoid)
            G.CACHE.add(cache_utils.CACHE_MYLIST, 'my_list_items', my_list_videoids)
        except CacheMiss:
            pass
    else:
        common.make_call('add_videoids_to_video_list_cache', {'cache_bucket': cache_utils.CACHE_MYLIST,
                                                              'cache_identifier': mylist_identifier,
                                                              'video_ids': [videoid.value]})
        try:
            my_list_videoids = G.CACHE.get(cache_utils.CACHE_MYLIST, 'my_list_items')
            my_list_videoids.append(videoid)
            G.CACHE.add(cache_utils.CACHE_MYLIST, 'my_list_items', my_list_videoids)
        except CacheMiss:
            pass


@measure_exec_time_decorator()
def get_parental_control_data(guid, password):
    """Get the parental control data"""
    return common.make_call('parental_control_data', {'guid': guid, 'password': password})


@measure_exec_time_decorator()
def set_parental_control_data(data):
    """Set the parental control data"""
    common.make_call(
        'post_safe',
        {'endpoint': 'content_restrictions',
         'data': {'action': 'update',
                  'authURL': data['token'],
                  'experience': data['experience'],
                  'guid': data['guid'],
                  'maturity': data['maturity']}}
    )


@measure_exec_time_decorator()
def verify_profile_lock(guid, pin):
    """Send profile PIN to Netflix and verify it."""
    try:
        common.make_call(
            'post_safe',
            {'endpoint': 'profile_lock',
             'data': {'pin': pin,
                      'action': 'verify',
                      'guid': guid}}
        )
        return True
    except HttpError401:  # Wrong PIN
        return False


def get_available_audio_languages():
    """Get the list of available audio languages of videos"""
    call_args = {
        'paths': [['spokenAudioLanguages', {'from': 0, 'to': 25}, ['id', 'name']]]
    }
    response = common.make_call('path_request', call_args)
    lang_list = {}
    for lang_dict in response.get('spokenAudioLanguages', {}).values():
        lang_list[lang_dict['id']] = lang_dict['name']
    return lang_list


def get_available_subtitles_languages():
    """Get the list of available subtitles languages of videos"""
    call_args = {
        'paths': [['subtitleLanguages', {'from': 0, 'to': 25}, ['id', 'name']]]
    }
    response = common.make_call('path_request', call_args)
    lang_list = {}
    for lang_dict in response.get('subtitleLanguages', {}).values():
        lang_list[lang_dict['id']] = lang_dict['name']
    return lang_list


def get_genre_title(genre_id):
    """
    Get the title of a genre list of given ID
    :return None if the ID not exists
    """
    call_args = {
        'paths': [['genres', int(genre_id), ['name']]]
    }
    response = common.make_call('path_request', call_args)
    return response['genres'].get(genre_id, {}).get('name')


def remove_watched_status(videoid):
    """Request to Netflix service to delete the watched status (delete also the item from "continue watching" list)"""
    # WARNING: THE NF SERVICE MAY TAKE UNTIL TO 24 HOURS TO REMOVE IT
    try:
        data = common.make_call(
            'post_safe',
            {'endpoint': 'viewing_activity',
             'data': {'movieID': videoid.value,
                      'seriesAll': videoid.mediatype == common.VideoId.SHOW,
                      'guid': G.LOCAL_DB.get_active_profile_guid()}}
        )
        return data.get('status', False)
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('remove_watched_status raised this error: {}', exc)
        return False


def get_metadata(videoid, refresh=False):
    return common.make_call('get_metadata', {'videoid': videoid,
                                             'refresh': refresh})


def get_mylist_videoids_profile_switch():
    return common.make_call('get_mylist_videoids_profile_switch')
