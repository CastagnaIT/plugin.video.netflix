# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Handle playback requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json

import xbmcgui
import xbmcplugin

import resources.lib.common as common
import resources.lib.kodi.infolabels as infolabels
import resources.lib.kodi.ui as ui
import resources.lib.utils.api_requests as api
from resources.lib.globals import G
from resources.lib.utils.api_paths import EVENT_PATHS
from resources.lib.common.exceptions import MetadataNotAvailable, InputStreamHelperError
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

# Note: On SERVICE_URL_FORMAT with python 3, using 'localhost' slowdown the call (Windows OS is affected),
# so the time that Kodi takes to start a video increases, (due to requests exchange between ISA and the add-on)
# not sure if it is an urllib issue

SERVICE_URL_FORMAT = 'http://127.0.0.1:{port}'
MANIFEST_PATH_FORMAT = '/manifest?id={videoid}'
LICENSE_PATH_FORMAT = '/license?id={videoid}'

INPUTSTREAM_SERVER_CERTIFICATE = (
    'Cr0CCAMSEOVEukALwQ8307Y2+LVP+0MYh/HPkwUijgIwggEKAoIBAQDm875btoWUbGqQD8eA'
    'GuBlGY+Pxo8YF1LQR+Ex0pDONMet8EHslcZRBKNQ/09RZFTP0vrYimyYiBmk9GG+S0wB3CRI'
    'TgweNE15cD33MQYyS3zpBd4z+sCJam2+jj1ZA4uijE2dxGC+gRBRnw9WoPyw7D8RuhGSJ95O'
    'Etzg3Ho+mEsxuE5xg9LM4+Zuro/9msz2bFgJUjQUVHo5j+k4qLWu4ObugFmc9DLIAohL58UR'
    '5k0XnvizulOHbMMxdzna9lwTw/4SALadEV/CZXBmswUtBgATDKNqjXwokohncpdsWSauH6vf'
    'S6FXwizQoZJ9TdjSGC60rUB2t+aYDm74cIuxAgMBAAE6EHRlc3QubmV0ZmxpeC5jb20SgAOE'
    '0y8yWw2Win6M2/bw7+aqVuQPwzS/YG5ySYvwCGQd0Dltr3hpik98WijUODUr6PxMn1ZYXOLo'
    '3eED6xYGM7Riza8XskRdCfF8xjj7L7/THPbixyn4mULsttSmWFhexzXnSeKqQHuoKmerqu0n'
    'u39iW3pcxDV/K7E6aaSr5ID0SCi7KRcL9BCUCz1g9c43sNj46BhMCWJSm0mx1XFDcoKZWhpj'
    '5FAgU4Q4e6f+S8eX39nf6D6SJRb4ap7Znzn7preIvmS93xWjm75I6UBVQGo6pn4qWNCgLYlG'
    'GCQCUm5tg566j+/g5jvYZkTJvbiZFwtjMW5njbSRwB3W4CrKoyxw4qsJNSaZRTKAvSjTKdqV'
    'DXV/U5HK7SaBA6iJ981/aforXbd2vZlRXO/2S+Maa2mHULzsD+S5l4/YGpSt7PnkCe25F+nA'
    'ovtl/ogZgjMeEdFyd/9YMYjOS4krYmwp3yJ7m9ZzYCQ6I8RQN4x/yLlHG5RH/+WNLNUs6JAZ'
    '0fFdCmw=')


@common.inject_video_id(path_offset=0, pathitems_arg='videoid', inject_full_pathitems=True)
def play_strm(videoid):
    _play(videoid, True)


@common.inject_video_id(path_offset=0, pathitems_arg='videoid', inject_full_pathitems=True)
def play(videoid):
    _play(videoid, False)


@measure_exec_time_decorator()
def _play(videoid, is_played_from_strm=False):
    """Play an episode or movie as specified by the path"""
    is_upnext_enabled = G.ADDON.getSettingBool('UpNextNotifier_enabled')
    LOG.info('Playing {}{}{}',
             videoid,
             ' [STRM file]' if is_played_from_strm else '',
             ' [external call]' if G.IS_ADDON_EXTERNAL_CALL else '')

    # Profile switch when playing from a STRM file (library)
    if is_played_from_strm:
        if not _profile_switch():
            xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)
            return

    # Get metadata of videoid
    try:
        metadata = api.get_metadata(videoid)
        LOG.debug('Metadata is {}', json.dumps(metadata))
    except MetadataNotAvailable:
        LOG.warn('Metadata not available for {}', videoid)
        metadata = [{}, {}]

    # Check parental control PIN
    pin_result = _verify_pin(metadata[0].get('requiresPin', False))
    if not pin_result:
        if pin_result is not None:
            ui.show_notification(common.get_local_string(30106), time=8000)
        xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)
        return

    # Generate the xbmcgui.ListItem to be played
    list_item = get_inputstream_listitem(videoid)

    # STRM file resume workaround (Kodi library)
    resume_position = _strm_resume_workaroud(is_played_from_strm, videoid)
    if resume_position == '':
        xbmcplugin.setResolvedUrl(handle=G.PLUGIN_HANDLE, succeeded=False, listitem=list_item)
        return

    info_data = None
    event_data = {}
    videoid_next_episode = None

    # Get Infolabels and Arts for the videoid to be played, and for the next video if it is an episode (for UpNext)
    if is_played_from_strm or is_upnext_enabled or G.IS_ADDON_EXTERNAL_CALL:
        if is_upnext_enabled and videoid.mediatype == common.VideoId.EPISODE:
            # When UpNext is enabled, get the next episode to play
            videoid_next_episode = _upnext_get_next_episode_videoid(videoid, metadata)
        info_data = infolabels.get_info_from_netflix(
            [videoid, videoid_next_episode] if videoid_next_episode else [videoid])
        info, arts = info_data[videoid.value]
        # When a item is played from Kodi library or Up Next add-on is needed set info and art to list_item
        list_item.setInfo('video', info)
        list_item.setArt(arts)

    # Get event data for videoid to be played (needed for sync of watched status with Netflix)
    if (G.ADDON.getSettingBool('ProgressManager_enabled')
            and videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.EPISODE]):
        if not is_played_from_strm or is_played_from_strm and G.ADDON.getSettingBool('sync_watched_status_library'):
            event_data = _get_event_data(videoid)
            event_data['videoid'] = videoid.to_dict()
            event_data['is_played_by_library'] = is_played_from_strm

    # Start and initialize the action controller (see action_controller.py)
    LOG.debug('Sending initialization signal')
    # Do not use send_signal as threaded slow devices are not powerful to send in faster way and arrive late to service
    common.send_signal(common.Signals.PLAYBACK_INITIATED, {
        'videoid': videoid.to_dict(),
        'videoid_next_episode': videoid_next_episode.to_dict() if videoid_next_episode else None,
        'metadata': metadata,
        'info_data': info_data,
        'is_played_from_strm': is_played_from_strm,
        'resume_position': resume_position,
        'event_data': event_data})
    xbmcplugin.setResolvedUrl(handle=G.PLUGIN_HANDLE, succeeded=True, listitem=list_item)


def get_inputstream_listitem(videoid):
    """Return a listitem that has all inputstream relevant properties set for playback of the given video_id"""
    service_url = SERVICE_URL_FORMAT.format(
        port=G.LOCAL_DB.get_value('msl_service_port', 8000))
    manifest_path = MANIFEST_PATH_FORMAT.format(videoid=videoid.value)
    list_item = xbmcgui.ListItem(path=service_url + manifest_path, offscreen=True)
    list_item.setContentLookup(False)
    list_item.setMimeType('application/xml+dash')
    list_item.setProperty('isFolder', 'false')
    list_item.setProperty('IsPlayable', 'true')
    try:
        import inputstreamhelper
        is_helper = inputstreamhelper.Helper('mpd', drm='widevine')
        inputstream_ready = is_helper.check_inputstream()
        if not inputstream_ready:
            raise Exception(common.get_local_string(30046))

        list_item.setProperty(
            key=is_helper.inputstream_addon + '.stream_headers',
            value='user-agent=' + common.get_user_agent())
        list_item.setProperty(
            key=is_helper.inputstream_addon + '.license_type',
            value='com.widevine.alpha')
        list_item.setProperty(
            key=is_helper.inputstream_addon + '.manifest_type',
            value='mpd')
        list_item.setProperty(
            key=is_helper.inputstream_addon + '.license_key',
            value=service_url + LICENSE_PATH_FORMAT.format(videoid=videoid.value) + '||b{SSM}!b{SID}|')
        list_item.setProperty(
            key=is_helper.inputstream_addon + '.server_certificate',
            value=INPUTSTREAM_SERVER_CERTIFICATE)
        list_item.setProperty(
            key='inputstream',
            value=is_helper.inputstream_addon)
        return list_item
    except Exception as exc:  # pylint: disable=broad-except
        # Captures all types of ISH internal errors
        import traceback
        LOG.error(traceback.format_exc())
        raise InputStreamHelperError(str(exc)) from exc


def _profile_switch():
    """Profile switch to play from the library"""
    # This is needed to play videos with the appropriate Netflix profile to avoid problems like:
    #   Missing audio/subtitle languages; Missing metadata; Wrong age restrictions;
    #   Video content not available; Sync with netflix watched status to wrong profile
    # Of course if the user still selects the wrong profile the problems remains,
    # but now will be caused only by the user for inappropriate use.
    library_playback_profile_guid = G.LOCAL_DB.get_value('library_playback_profile_guid')
    if library_playback_profile_guid:
        selected_guid = library_playback_profile_guid
    else:
        selected_guid = ui.show_profiles_dialog(title_prefix=common.get_local_string(15213),
                                                preselect_guid=G.LOCAL_DB.get_active_profile_guid())
    if not selected_guid:
        return False
    # Perform the profile switch
    # The profile switch is done to NFSession, the MSL part will be switched automatically
    from resources.lib.navigation.directory_utils import activate_profile
    if not activate_profile(selected_guid):
        return False
    return True


def _verify_pin(pin_required):
    if not pin_required:
        return True
    pin = ui.show_dlg_input_numeric(common.get_local_string(30002))
    return None if not pin else api.verify_pin(pin)


def _strm_resume_workaroud(is_played_from_strm, videoid):
    """Workaround for resuming STRM files from library"""
    if not is_played_from_strm or not G.ADDON.getSettingBool('ResumeManager_enabled'):
        return None
    # The resume workaround will fail when:
    # - The metadata have a new episode, but the STRM is not exported yet
    # - User try to play STRM files copied from another/previous add-on installation (without import them)
    # - User try to play STRM files from a shared path (like SMB) of another device (without use shared db)
    resume_position = infolabels.get_resume_info_from_library(videoid).get('position')
    if resume_position:
        index_selected = (ui.ask_for_resume(resume_position)
                          if G.ADDON.getSettingBool('ResumeManager_dialog') else None)
        if index_selected == -1:
            # Cancel playback
            return ''
        if index_selected == 1:
            resume_position = None
    return resume_position


def _get_event_data(videoid):
    """Get data needed to send event requests to Netflix and for resume from last position"""
    is_episode = videoid.mediatype == common.VideoId.EPISODE
    req_videoids = [videoid]
    if is_episode:
        # Get also the tvshow data
        req_videoids.append(videoid.derive_parent(common.VideoId.SHOW))

    raw_data = api.get_video_raw_data(req_videoids, EVENT_PATHS)
    if not raw_data:
        return {}
    LOG.debug('Event data: {}', raw_data)
    videoid_data = raw_data['videos'][videoid.value]

    if is_episode:
        # Get inQueue from tvshow data
        is_in_mylist = raw_data['videos'][str(req_videoids[1].value)]['queue'].get('inQueue', False)
    else:
        is_in_mylist = videoid_data['queue'].get('inQueue', False)

    event_data = {'resume_position':
                  videoid_data['bookmarkPosition'] if videoid_data['bookmarkPosition'] > -1 else None,
                  'runtime': videoid_data['runtime'],
                  'request_id': videoid_data['requestId'],
                  'watched': videoid_data['watched'],
                  'is_in_mylist': is_in_mylist}
    if videoid.mediatype == common.VideoId.EPISODE:
        event_data['track_id'] = videoid_data['trackIds']['trackId_jawEpisode']
    else:
        event_data['track_id'] = videoid_data['trackIds']['trackId_jaw']
    return event_data


def _upnext_get_next_episode_videoid(videoid, metadata):
    """Determine the next episode and get the videoid"""
    try:
        videoid_next_episode = _find_next_episode(videoid, metadata)
        LOG.debug('Next episode is {}', videoid_next_episode)
        return videoid_next_episode
    except (TypeError, KeyError):
        # import traceback
        # LOG.debug(traceback.format_exc())
        LOG.debug('There is no next episode, not setting up Up Next')
        return None


def _find_next_episode(videoid, metadata):
    try:
        # Find next episode in current season
        episode = common.find(metadata[0]['seq'] + 1, 'seq',
                              metadata[1]['episodes'])
        return common.VideoId(tvshowid=videoid.tvshowid,
                              seasonid=videoid.seasonid,
                              episodeid=episode['id'])
    except (IndexError, KeyError):
        # Find first episode of next season
        next_season = common.find(metadata[1]['seq'] + 1, 'seq',
                                  metadata[2]['seasons'])
        episode = common.find(1, 'seq', next_season['episodes'])
        return common.VideoId(tvshowid=videoid.tvshowid,
                              seasonid=next_season['id'],
                              episodeid=episode['id'])
