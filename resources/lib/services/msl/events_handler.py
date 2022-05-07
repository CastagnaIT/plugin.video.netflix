# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Handle and build Netflix events

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import random
import threading
import time

import xbmc

from resources.lib import common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.services.msl import msl_utils
from resources.lib.services.msl.msl_utils import EVENT_START, EVENT_STOP, EVENT_ENGAGE, ENDPOINTS, create_req_params
from resources.lib.utils.esn import get_esn
from resources.lib.utils.logging import LOG

try:
    import Queue as queue
except ImportError:  # Python 3
    import queue


class EventsHandler(threading.Thread):
    """Handle and build Netflix event requests"""

    def __init__(self, chunked_request):
        super(EventsHandler, self).__init__()
        self.chunked_request = chunked_request
        # session_id, app_id are common to all events
        self.session_id = int(time.time()) * 10000 + random.randint(1, 10001)
        self.app_id = None
        self.queue_events = queue.Queue(maxsize=10)
        self.cache_data_events = {}
        self.banned_events_ids = []
        common.register_slot(signal=common.Signals.QUEUE_VIDEO_EVENT, callback=self.callback_event_video_queue)
        self._stop_requested = False
        self.loco_data = None

    def run(self):
        """Monitor and process the event queue"""
        LOG.debug('[Event queue monitor] Thread started')
        monitor = xbmc.Monitor()

        while not monitor.abortRequested() and not self._stop_requested:
            try:
                # Take the first queued item
                event_type, event_data, player_state = self.queue_events.get_nowait()
                # Process the request
                self._process_event_request(event_type, event_data, player_state)
            except queue.Empty:
                pass
            except Exception as exc:  # pylint: disable=broad-except
                LOG.error('[Event queue monitor] An error has occurred: {}', exc)
                import traceback
                LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
                self.clear_queue()
            monitor.waitForAbort(0.5)

    def _process_event_request(self, event_type, event_data, player_state):
        """Build and make the event post request"""
        if event_type == EVENT_START:
            # We get at every new video playback a fresh LoCo data
            self.loco_data = common.make_http_call('get_loco_data', None)
        url = event_data['manifest']['links']['events']['href']
        from resources.lib.services.msl.msl_request_builder import MSLRequestBuilder
        request_data = MSLRequestBuilder.build_request_data(url,
                                                            self._build_event_params(event_type,
                                                                                     event_data,
                                                                                     player_state,
                                                                                     event_data['manifest'],
                                                                                     self.loco_data))
        # Request attempts can be made up to a maximum of 3 times per event
        LOG.info('EVENT [{}] - Executing request', event_type)
        endpoint_url = ENDPOINTS['events'] + create_req_params('events/{}'.format(event_type))
        try:
            response = self.chunked_request(endpoint_url, request_data, get_esn(),
                                            disable_msl_switch=False)
            # Malformed/wrong content in requests are ignored without returning any error in the response or exception
            LOG.debug('EVENT [{}] - Request response: {}', event_type, response)
            if event_type == EVENT_STOP:
                if event_data['allow_request_update_loco']:
                    if 'list_context_name' in self.loco_data:
                        common.make_http_call('update_loco_context', {
                            'loco_root_id': self.loco_data['root_id'],
                            'list_context_name': self.loco_data['list_context_name'],
                            'list_id': self.loco_data['list_id'],
                            'list_index': self.loco_data['list_index']})
                    else:
                        LOG.debug('EventsHandler: LoCo list not updated no list context data provided')
                    # video_id = request_data['params']['sessionParams']['uiplaycontext']['video_id']
                    # common.make_http_call('update_videoid_bookmark', {'video_id': video_id})
                self.loco_data = None
        except Exception as exc:  # pylint: disable=broad-except
            LOG.error('EVENT [{}] - The request has failed: {}', event_type, exc)
            # Ban future event requests from this event xid
            # self.banned_events_xid.append(request_data['xid'])
            # Todo: this has been disabled because unstable Wi-Fi connections may cause consecutive errors
            #   probably this should be handled in a different way

    def stop_join(self):
        self._stop_requested = True
        self.join()

    def callback_event_video_queue(self, data=None):
        """Callback to add a video event"""
        try:
            self.add_event_to_queue(data['event_type'], data['event_data'], data['player_state'])
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
            show_addon_error_info(exc)

    def add_event_to_queue(self, event_type, event_data, player_state):
        """Adds an event in the queue of events to be processed"""
        videoid = common.VideoId.from_dict(event_data['videoid'])
        previous_data, _ = self.cache_data_events.get(videoid.value, ({}, None))
        if previous_data.get('xid') in self.banned_events_ids:
            LOG.warn('EVENT [{}] - Not added to the queue. The xid {} is banned due to a previous failed request',
                     event_type, previous_data.get('xid'))
            return
        try:
            self.queue_events.put_nowait((event_type, event_data, player_state))
            LOG.debug('EVENT [{}] - Added to queue', event_type)
        except queue.Full:
            LOG.warn('EVENT [{}] - Not added to the queue. The event queue is full.', event_type)

    def clear_queue(self):
        """Clear all queued events"""
        with self.queue_events.mutex:
            self.queue_events.queue.clear()
        self.cache_data_events = {}
        self.banned_events_ids = []

    def _build_event_params(self, event_type, event_data, player_state, manifest, loco_data):
        """Build data params for an event request"""
        videoid = common.VideoId.from_dict(event_data['videoid'])
        # Get previous elaborated data of the same video id
        # Some tags must remain unchanged between events
        previous_data, previous_player_state = self.cache_data_events.get(videoid.value, ({}, None))
        timestamp = int(time.time() * 1000)

        # Context location values can be easily viewed from tag data-ui-tracking-context
        # of a preview box in website html
        # play_ctx_location = 'WATCHNOW'
        play_ctx_location = 'MyListAsGallery' if event_data['is_in_mylist'] else 'browseTitles'

        # To now it is not mandatory, we leave support for future changes
        # if event_data['is_played_by_library']:
        #     list_id = 'unknown'
        # else:
        #     list_id = G.LOCAL_DB.get_value('last_menu_id', 'unknown')

        position = player_state['elapsed_seconds']
        if position != 1:
            position *= 1000

        if msl_utils.is_media_changed(previous_player_state, player_state):
            play_times, video_track_id, audio_track_id, sub_track_id = msl_utils.build_media_tag(player_state, manifest,
                                                                                                 position)
        else:
            play_times = previous_data['playTimes']
            msl_utils.update_play_times_duration(play_times, player_state)
            video_track_id = previous_data['videoTrackId']
            audio_track_id = previous_data['audioTrackId']
            sub_track_id = previous_data['timedTextTrackId']

        params = {
            'event': event_type,
            'xid': previous_data.get('xid', G.LOCAL_DB.get_value('xid', table=TABLE_SESSION)),
            'position': position,  # Video time elapsed
            'clientTime': timestamp,
            'sessionStartTime': previous_data.get('sessionStartTime', timestamp),
            'videoTrackId': video_track_id,
            'audioTrackId': audio_track_id,
            'timedTextTrackId': sub_track_id,
            'trackId': str(event_data['track_id']),
            'sessionId': str(self.session_id),
            'appId': str(self.app_id or self.session_id),
            'playTimes': play_times,
            'sessionParams': previous_data.get('sessionParams', {
                'isUIAutoPlay': False,  # Should be set equal to the manifest request
                'supportsPreReleasePin': True,  # Should be set equal to the manifest request
                'supportsWatermark': True,  # Should be set equal to the manifest request
                'preferUnletterboxed': False,  # Should be set equal to the manifest request
                'uiplaycontext': {
                    # 'list_id': list_id,  # not mandatory
                    # lolomo_id: use loco root id value
                    'lolomo_id': loco_data['root_id'],
                    'location': play_ctx_location,
                    'rank': 0,  # Perhaps this is a reference of cdn rank used in the manifest? (we use always 0)
                    'request_id': event_data['request_id'],
                    'row': 0,  # Purpose not known
                    'track_id': event_data['track_id'],
                    'video_id': videoid.value
                }
            })
        }

        if event_type == EVENT_ENGAGE:
            params['action'] = 'User_Interaction'

        self.cache_data_events[videoid.value] = (params, player_state)
        return params
