# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Playback tracking and coordination of several actions during playback

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import re
import threading
import time
from typing import TYPE_CHECKING

import xbmc

import resources.lib.common as common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.utils.logging import LOG
from .action_manager import ActionManager
from .am_playback import AMPlayback
from .am_section_skipping import AMSectionSkipper
from .am_stream_continuity import AMStreamContinuity
from .am_upnext_notifier import AMUpNextNotifier
from .am_video_events import AMVideoEvents

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.directorybuilder.dir_builder import DirectoryBuilder
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations
    from resources.lib.services.nfsession.msl.msl_handler import MSLHandler


class ActionController(xbmc.Monitor):
    """
    Tracks status and progress of video playbacks initiated by the add-on
    """
    def __init__(self, nfsession: 'NFSessionOperations', msl_handler: 'MSLHandler',
                 directory_builder: 'DirectoryBuilder'):
        xbmc.Monitor.__init__(self)
        self.nfsession = nfsession
        self.msl_handler = msl_handler
        self.directory_builder = directory_builder
        self._playback_tick = None
        self._init_data = None
        self.init_count = 0
        self.is_tracking_enabled = False
        self.active_player_id = None
        self.action_managers = None
        self._last_player_state = {}
        self._is_pause_called = False
        self._is_av_started = False
        self._av_change_last_ts = None
        self._is_delayed_seek = False
        self._is_ads_plan = G.LOCAL_DB.get_value('is_ads_plan', None, table=TABLE_SESSION)
        common.register_slot(self.initialize_playback, common.Signals.PLAYBACK_INITIATED, is_signal=True)

    def initialize_playback(self, **kwargs):
        """
        Callback for AddonSignal when this add-on has initiated a playback
        """
        self._init_data = kwargs
        self._init_data['videoid_parent'] = kwargs['videoid'].derive_parent(common.VideoId.SHOW)
        self._init_data['metadata'] = self.nfsession.get_metadata(kwargs['videoid'])
        self.active_player_id = None
        self.is_tracking_enabled = True

    def _initialize_am(self):
        self._last_player_state = {}
        self._is_pause_called = False
        self._av_change_last_ts = None
        self._is_delayed_seek = False
        if not self._init_data:
            return
        self.action_managers = [
            AMPlayback(),
            AMSectionSkipper(),
            AMStreamContinuity(),
            AMVideoEvents(self.nfsession, self.msl_handler, self.directory_builder),
            AMUpNextNotifier(self.nfsession)
        ]
        self.init_count += 1
        self._notify_all(ActionManager.call_initialize, self._init_data)
        self._init_data = None

    def onNotification(self, sender, method, data):  # pylint: disable=unused-argument,too-many-branches
        """
        Callback for Kodi notifications that handles and dispatches playback events
        """
        LOG.warn('ActionController: onNotification {} -- {}', method, data)
        # WARNING: Do not get playerid from 'data',
        # Because when Up Next add-on play a video while we are inside Netflix add-on and
        # not externally like Kodi library, the playerid become -1 this id does not exist
        if not self.is_tracking_enabled or not method.startswith('Player.'):
            return
        try:
            if method == 'Player.OnPlay':
                if self.init_count > 0:
                    # In this case the user has chosen to play another video while another one is in playing,
                    # then we send the missing Stop event for the current video
                    self._on_playback_stopped()
                self._initialize_am()
            elif method == 'Player.OnAVStart':
                self._is_av_started = True
                self._on_playback_started()
                if self._playback_tick is None or not self._playback_tick.is_alive():
                    self._playback_tick = PlaybackTick(self.on_playback_tick)
                    self._playback_tick.daemon = True
                    self._playback_tick.start()
            elif method == 'Player.OnSeek':
                if self._is_ads_plan:
                    # Workaround:
                    # Due to Kodi bug see JSONRPC "Player.GetProperties" info below,
                    # when a user do video seek while watching ADS parts, will change chapter and we receive "Player.OnSeek"
                    # but if we execute self._on_playback_seek immediately it will call JSONRPC "Player.GetProperties"
                    # that provide wrong data, so we have to delay it until we receive last "Player.OnAVChange" event
                    # at that time InputStreamAdaptive should have provided to kodi the streaming data and then
                    # JSONRPC "Player.GetProperties" should return the right data, at least most of the time
                    self._is_delayed_seek = True
                else:
                    self._on_playback_seek(json.loads(data)['player']['time'])
            elif method == 'Player.OnPause':
                self._is_pause_called = True
                self._on_playback_pause()
            elif method == 'Player.OnResume':
                # Kodi call this event instead the "Player.OnStop" event when you try to play a video
                # while another one is in playing (also if the current video is in pause) (not happen on RPI devices)
                # Can be one of following cases:
                # - When you use ctx menu "Play From Here", this happen when click to next button
                # - When you use UpNext add-on
                # - When you play a non-Netflix video when a Netflix video is in playback in background
                # - When you play a video over another in playback (back in menus)
                if not self._is_pause_called:
                    return
                if self.init_count == 0:
                    # This should never happen, we have to avoid this event when you try to play a video
                    # while another non-netflix video is in playing
                    return
                self._is_pause_called = False
                self._on_playback_resume()
            elif method == 'Player.OnStop':
                self.is_tracking_enabled = False
                if self.active_player_id is None:
                    # if playback does not start due to an error in streams initialization
                    # OnAVStart notification will not be called, then active_player_id will be None
                    LOG.debug('ActionController: Player.OnStop event has been ignored')
                    LOG.warn('ActionController: Action managers disabled due to a playback initialization error')
                    self.action_managers = None
                    self.init_count -= 1
                    return
                self._on_playback_stopped()
            elif method == 'Player.OnAVChange':
                # OnAVChange event can be sent by Kodi multiple times in a very short period of time,
                # one event per stream type (audio/video/subs) so depends on what stream kodi core request to ISAdaptive
                # this will try group all these events in a single one by storing the current time,
                # it's not a so safe solution, and also delay things about 2 secs, atm i have not found anything better
                if self._is_av_started or self._is_delayed_seek:
                    self._av_change_last_ts = time.time()
        except Exception:  # pylint: disable=broad-except
            import traceback
            LOG.error(traceback.format_exc())
            self.is_tracking_enabled = False
            self._is_av_started = False
            if self._playback_tick and self._playback_tick.is_alive():
                self._playback_tick.stop_join()
                self._playback_tick = None
            self.init_count = 0

    def on_playback_tick(self):
        """
        Notify to action managers that an second of playback has elapsed
        """
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if not player_state:
                return
            # If we are waiting for OnAVChange events, dont send call_on_tick otherwise will mix old/new player_state info
            if not self._av_change_last_ts:
                self._notify_all(ActionManager.call_on_tick, player_state)
            else:
                # If more than 1 second has elapsed since the last OnAVChange event received, process the following
                # usually 1 sec is enough time to receive up to 3 OnAVChange events (audio/video/subs)
                if (time.time() - self._av_change_last_ts) > 1:
                    if self._is_av_started:
                        self._is_av_started = False
                        self._on_avchange_delayed(player_state)
                    if self._is_delayed_seek:
                        self._is_delayed_seek = False
                        self._on_playback_seek(None)
                    self._av_change_last_ts = None

    def _on_avchange_delayed(self, player_state):
        self._notify_all(ActionManager.call_on_avchange_delayed, player_state)

    def _on_playback_started(self):
        player_id = _get_player_id()
        self._notify_all(ActionManager.call_on_playback_started, self._get_player_state(player_id))
        if LOG.is_enabled and G.ADDON.getSettingBool('show_codec_info'):
            common.json_rpc('Input.ExecuteAction', {'action': 'codecinfo'})
        self.active_player_id = player_id

    def _on_playback_seek(self, time_override):
        if self.active_player_id is not None:
            player_state = self._get_player_state(time_override=time_override)
            if player_state:
                self._notify_all(ActionManager.call_on_playback_seek,
                                 player_state)

    def _on_playback_pause(self):
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_pause,
                                 player_state)

    def _on_playback_resume(self):
        if self.active_player_id is not None:
            player_state = self._get_player_state()
            if player_state:
                self._notify_all(ActionManager.call_on_playback_resume,
                                 player_state)

    def _on_playback_stopped(self):
        if self._playback_tick and self._playback_tick.is_alive():
            self._playback_tick.stop_join()
            self._playback_tick = None
        self.active_player_id = None
        # Immediately send the request to release the license
        common.run_threaded(True, self.msl_handler.release_license)
        self._notify_all(ActionManager.call_on_playback_stopped,
                         self._last_player_state)
        self.action_managers = None
        self.init_count -= 1
        self._is_av_started = False

    def _notify_all(self, notification, data=None):
        LOG.debug('Notifying all action managers of {} (data={})', notification.__name__, data)
        for manager in self.action_managers:
            _notify_managers(manager, notification, data)

    def _get_player_state(self, player_id=None, time_override=None):
        # !! WARNING KODI BUG ON: Player.GetProperties and KODI CORE / GUI, FOR STREAMS WITH ADS CHAPTERS !!
        # todo: TO TAKE IN ACCOUNT FOR FUTURE ADS IMPROVEMENTS <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
        # When you are playing a stream with more chapters due to ADS,
        # every time a chapter is ended and start the next one (chapter change) InputStream Adaptive add-on send the
        # DEMUX_SPECIALID_STREAMCHANGE packet to Kodi buffer to signal the chapter change, but Kodi core instead of
        # follow the stream buffer apply immediately the chapter change, this means e.g. that while you are watching an
        # ADS, you can see on Kodi info GUI that the chapter is changed in advance (that should not happens)
        # this will cause problems also on the JSON RPC Player.GetProperties, will no longer provide info of what the
        # player is playing, but provides future information... therefore we have completely wrong playing info!
        # Needless to say, this causes a huge mess with all addon features managed here...

        # A bad hack workaround solution:
        # 1) With the DASH manifest converter (converter.py), we include to each chapter name a custom info to know what
        # chapter is an ADS and the offset PTS of when it starts, this custom info is inserted in the "name"
        # attribute of each Period/AdaptationSet tag with following format "(Id {movie_id})(pts offset {pts_offset})"
        # 2) We can get the custom info above, here as video stream name
        # 3) Being that the info retrieved JSON RPC Player.GetProperties could be "future" info and not the current
        # played, the only reliable value will be the current time, therefore if the pts_offset is ahead of the
        # current play time then (since ADS are placed all before the movie) means that kodi is still playing an ADS
        # 4) If the 3rd point result in an ADS, we force "nf_is_ads_stream" value on "player_state" to be True.

        # So each addon feature, BEFORE doing any operation MUST check always if "nf_is_ads_stream" value on
        # "player_state" is True, to prevent process wrong player_state info
        try:
            player_state = common.json_rpc('Player.GetProperties', {
                'playerid': self.active_player_id if player_id is None else player_id,
                'properties': [
                    'audiostreams',
                    'currentaudiostream',
                    'currentvideostream',
                    'subtitles',
                    'currentsubtitle',
                    'subtitleenabled',
                    'percentage',
                    'time',
                    'videostreams']
            })
        except IOError as exc:
            LOG.warn('_get_player_state: {}', exc)
            return {}
        if not player_state['currentaudiostream'] and player_state['audiostreams']:
            return {}  # if audio stream has not been loaded yet, there is empty currentaudiostream
        if not player_state['currentsubtitle'] and player_state['subtitles']:
            return {}  # if subtitle stream has not been loaded yet, there is empty currentsubtitle
        try:
            player_state['playerid'] = self.active_player_id if player_id is None else player_id
            # convert time dict to elapsed seconds
            player_state['elapsed_seconds'] = (player_state['time']['hours'] * 3600 +
                                               player_state['time']['minutes'] * 60 +
                                               player_state['time']['seconds'])

            if time_override:
                player_state['time'] = time_override
                elapsed_seconds = (time_override['hours'] * 3600 +
                                   time_override['minutes'] * 60 +
                                   time_override['seconds'])
                player_state['percentage'] = player_state['percentage'] / player_state[
                    'elapsed_seconds'] * elapsed_seconds
                player_state['elapsed_seconds'] = elapsed_seconds

            # Sometimes may happen that when you stop playback the player status is partial,
            # this is because the Kodi player stop immediately but the stop notification (from the Monitor)
            # arrives late, meanwhile in this interval of time a service tick may occur.
            if ((player_state['audiostreams'] and player_state['elapsed_seconds']) or
                    (player_state['audiostreams'] and not player_state[
                        'elapsed_seconds'] and not self._last_player_state)):
                # save player state
                self._last_player_state = player_state
            else:
                # use saved player state
                player_state = self._last_player_state

            # Get additional video track info added in the track name
            # These info are come from "name" attribute of "AdaptationSet" tag in the DASH manifest (see converter.py)
            video_stream = player_state['videostreams'][0]
            # Try to find the crop info from the track name
            result = re.search(r'\(Crop (\d+\.\d+)\)', video_stream['name'])
            player_state['nf_video_crop_factor'] = float(result.group(1)) if result else None
            # Try to find the video id from the track name (may change if ADS video parts are played)
            result = re.search(r'\(Id (\d+)(_[a-z]+)?\)', video_stream['name'])
            player_state['nf_stream_videoid'] = result.group(1) if result else None
            # Try to find the PTS offset from the track name
            #  The pts offset value is used with the ADS plan only, it provides the offset where the played chapter start
            result = re.search(r'\(pts offset (\d+)\)', video_stream['name'])
            pts_offset = 0
            if result:
                pts_offset = int(result.group(1))
            player_state['nf_is_ads_stream'] = 'ads' in video_stream['name']
            # Since the JSON RPC Player.GetProperties can provide wrongly info of not yet played chapter (the next one)
            # to check if the info retrieved by Player.GetProperties are they really referred about what is displayed on
            # the screen or not, by checking if the "pts_offset" does not exceed the current time...
            # ofc we do this check only when the last chapter is the "movie", because the ADS are placed all before it
            # (so when 'nf_is_ads_stream' is false)
            if not player_state['nf_is_ads_stream'] and pts_offset != 0 and player_state['elapsed_seconds'] <= pts_offset:
                player_state['nf_is_ads_stream'] = True # Force as ADS, because Player.GetProperties provided wrong info
                player_state['current_pts'] = player_state['elapsed_seconds']
            else:
                # "current_pts" is the current player time without the duration of ADS video parts chapters (if any)
                # ADS chapters are always placed before the "movie",
                # addon features should never work with ADS chapters then must be excluded from current PTS
                player_state['current_pts'] = player_state['elapsed_seconds'] - pts_offset
            player_state['nf_pts_offset'] = pts_offset
            return player_state
        except Exception:  # pylint: disable=broad-except
            # For example may fail when buffering video
            LOG.warn('_get_player_state fails with data: {}', player_state)
            import traceback
            LOG.error(traceback.format_exc())
            return {}


def _notify_managers(manager, notification, data):
    notify_method = getattr(manager, notification.__name__)
    try:
        if data is not None:
            notify_method(data)
        else:
            notify_method()
    except Exception as exc:  # pylint: disable=broad-except
        manager.enabled = False
        msg = f'{manager.name} disabled due to exception: {exc}'
        import traceback
        LOG.error(traceback.format_exc())
        ui.show_notification(title=common.get_local_string(30105), msg=msg)


def _get_player_id():
    try:
        retry = 10
        while retry:
            result = common.json_rpc('Player.GetActivePlayers')
            if result:
                return result[0]['playerid']
            time.sleep(0.1)
            retry -= 1
        LOG.warn('Player ID not obtained, fallback to ID 1')
    except IOError:
        LOG.error('Player ID not obtained, fallback to ID 1')
    return 1


class PlaybackTick(threading.Thread):
    """Thread to send a notification every second of playback"""
    def __init__(self, on_playback_tick):
        self._on_playback_tick = on_playback_tick
        self._stop_event = threading.Event()
        self.is_playback_paused = False
        super().__init__()

    def run(self):
        while not self._stop_event.is_set():
            self._on_playback_tick()
            if self._stop_event.wait(1):
                break  # Stop requested by stop_join

    def stop_join(self):
        self._stop_event.set()
        self.join()
