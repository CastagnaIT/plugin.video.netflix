# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Handle playback requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmcgui
import xbmcplugin

import resources.lib.common as common
import resources.lib.kodi.infolabels as infolabels
import resources.lib.kodi.ui as ui
from resources.lib.globals import G
from resources.lib.common.exceptions import InputStreamHelperError
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

MANIFEST_PATH_FORMAT = common.IPC_ENDPOINT_MSL + '/get_manifest?videoid={}'
LICENSE_PATH_FORMAT = common.IPC_ENDPOINT_MSL + '/get_license?videoid={}'

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

PSSH_KID = 'AAAANHBzc2gAAAAA7e+LqXnWSs6jyCfc1R0h7QAAABQIARIQAAAAAAPSZ0kAAAAAAAAAAA==|AAAAAAPSZ0kAAAAAAAAAAA=='


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
    if is_played_from_strm and not _profile_switch():
        xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)
        return

    # Generate the xbmcgui.ListItem to be played
    list_item = get_inputstream_listitem(videoid)

    # STRM file resume workaround (Kodi library)
    resume_position = _strm_resume_workaroud(is_played_from_strm, videoid)
    if resume_position == '':
        xbmcplugin.setResolvedUrl(handle=G.PLUGIN_HANDLE, succeeded=False, listitem=list_item)
        return

    # When a video is played from Kodi library or Up Next add-on is needed set infoLabels and art info to list_item
    if is_played_from_strm or is_upnext_enabled or G.IS_ADDON_EXTERNAL_CALL:
        info, arts = common.make_call('get_videoid_info', videoid)
        list_item.setInfo('video', info)
        list_item.setArt(arts)

    # Start and initialize the action controller (see action_controller.py)
    LOG.debug('Sending initialization signal')
    # Do not use send_signal as threaded slow devices are not powerful to send in faster way and arrive late to service
    common.send_signal(common.Signals.PLAYBACK_INITIATED, {
        'videoid': videoid,
        'is_played_from_strm': is_played_from_strm,
        'resume_position': resume_position})
    xbmcplugin.setResolvedUrl(handle=G.PLUGIN_HANDLE, succeeded=True, listitem=list_item)


def get_inputstream_listitem(videoid):
    """Return a listitem that has all inputstream relevant properties set for playback of the given video_id"""
    service_url = f'http://127.0.0.1:{G.LOCAL_DB.get_value("nf_server_service_port")}'
    manifest_path = MANIFEST_PATH_FORMAT.format(videoid.value)
    list_item = xbmcgui.ListItem(path=service_url + manifest_path, offscreen=True)
    list_item.setContentLookup(False)
    list_item.setMimeType('application/xml+dash')
    list_item.setProperty('IsPlayable', 'true')
    # Allows the add-on to always have play callbacks also when using the playlist (Kodi versions >= 20)
    list_item.setProperty('ForceResolvePlugin', 'true')
    try:
        import inputstreamhelper
        is_helper = inputstreamhelper.Helper('mpd', drm='widevine')
        inputstream_ready = is_helper.check_inputstream()
    except Exception as exc:  # pylint: disable=broad-except
        # Captures all types of ISH internal errors
        import traceback
        LOG.error(traceback.format_exc())
        raise InputStreamHelperError(str(exc)) from exc
    if not inputstream_ready:
        raise Exception(common.get_local_string(30046))
    list_item.setProperty(
        key='inputstream.adaptive.stream_headers',
        value=f'user-agent={common.get_user_agent()}')
    list_item.setProperty(
        key='inputstream.adaptive.license_type',
        value='com.widevine.alpha')
    list_item.setProperty(
        key='inputstream.adaptive.manifest_type',
        value='mpd')
    list_item.setProperty(
        key='inputstream.adaptive.license_key',
        value=service_url + LICENSE_PATH_FORMAT.format(videoid.value) + '||b{SSM}!b{SID}|')
    list_item.setProperty(
        key='inputstream.adaptive.server_certificate',
        value=INPUTSTREAM_SERVER_CERTIFICATE)
    list_item.setProperty(
        key='inputstream',
        value='inputstream.adaptive')
    # Set PSSH/KID to pre-initialize the DRM to get challenge/session ID data in the ISA manifest proxy callback
    list_item.setProperty(
        key='inputstream.adaptive.pre_init_data',
        value=PSSH_KID)
    return list_item


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
