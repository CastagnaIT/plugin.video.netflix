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

import resources.lib.api.api_requests as api
from resources.lib import common
from resources.lib.common.cache_utils import CACHE_MANIFESTS
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from resources.lib.services.msl import msl_utils
from resources.lib.services.msl.msl_utils import EVENT_START, EVENT_STOP, EVENT_ENGAGE, ENDPOINTS

try:  # Python 2
    from urllib import urlencode
except ImportError:  # Python 3
    from urllib.parse import urlencode

try:
    import Queue as queue
except ImportError:  # Python 3
    import queue


class Event(object):
    """Object representing an event request to be processed"""

    STATUS_REQUESTED = 'REQUESTED'
    STATUS_INQUEUE = 'IN_QUEUE'
    STATUS_ERROR = 'ERROR'
    STATUS_SUCCESS = 'SUCCESS'

    def __init__(self, request_data, event_data):
        self.event_type = request_data['params']['event']
        self.status = self.STATUS_INQUEUE
        self.event_data = event_data
        self.request_data = request_data
        self.response_data = None
        self.req_attempt = 0
        common.debug('EVENT [{}] - Added to queue', self.event_type)

    def get_event_id(self):
        return self.request_data['xid']

    def set_response(self, response):
        self.response_data = response
        common.debug('EVENT [{}] - Request response: {}', self.event_type, response)
        # Seem that malformed requests are ignored without returning errors
        # self.status = self.STATUS_ERROR
        self.status = self.STATUS_SUCCESS

    def is_response_success(self):
        return self.status == self.STATUS_SUCCESS and self.req_attempt <= 3

    def is_attempts_granted(self):
        """Returns True if you can make new request attempts"""
        self.req_attempt += 1
        return bool(self.req_attempt <= 3)

    def get_video_id(self):
        return self.request_data['params']['sessionParams']['uiplaycontext']['video_id']

    def __str__(self):
        return self.event_type


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

    def run(self):
        """Monitor and process the event queue"""
        common.debug('[Event queue monitor] Thread started')
        monitor = xbmc.Monitor()

        while not monitor.abortRequested() and not self._stop_requested:
            try:
                # Take the first queued item
                event = self.queue_events.get_nowait()
                # Process the request
                continue_queue = self._process_event_request(event)
                if not continue_queue:
                    # Ban future requests from this event id
                    self.banned_events_ids += [event.get_event_id()]
            except queue.Empty:
                pass
            except Exception as exc:  # pylint: disable=broad-except
                common.error('[Event queue monitor] An error has occurred: {}', exc)
                import traceback
                common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
                self.clear_queue()
            monitor.waitForAbort(1)

    def _process_event_request(self, event):
        """Do the event post request"""
        event.status = Event.STATUS_REQUESTED
        # Request attempts can be made up to a maximum of 3 times per event
        while event.is_attempts_granted():
            common.info('EVENT [{}] - Executing request (attempt {})', event, event.req_attempt)
            params = {'reqAttempt': event.req_attempt,
                      'reqPriority': 20 if event.event_type == EVENT_START else 0,
                      'reqName': 'events/{}'.format(event)}
            url = ENDPOINTS['events'] + '?' + urlencode(params).replace('%2F', '/')
            try:
                response = self.chunked_request(url, event.request_data, g.get_esn(), disable_msl_switch=False)
                event.set_response(response)
                break
            except Exception as exc:  # pylint: disable=broad-except
                common.error('EVENT [{}] - The request has failed: {}', event, exc)
        if event.event_type == EVENT_STOP:
            self.clear_queue()
            if event.event_data['allow_request_update_lolomo']:
                if event.event_data['is_in_mylist']:
                    # If video is in my list, invalidate the continueWatching list (update lolomo context data)
                    api.update_lolomo_context('continueWatching')
                api.update_videoid_bookmark(event.get_video_id())
        # Below commented lines: let future requests continue to be sent, unstable connections like wi-fi cause problems
        # if not event.is_response_success():
            # The event request is unsuccessful then there is some problem,
            # no longer make any future requests from this event id
        #     return False
        return True

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
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            show_addon_error_info(exc)

    def add_event_to_queue(self, event_type, event_data, player_state):
        """Adds an event in the queue of events to be processed"""
        videoid = common.VideoId.from_dict(event_data['videoid'])
        # pylint: disable=unused-variable
        previous_data, previous_player_state = self.cache_data_events.get(videoid.value, ({}, None))
        manifest = get_manifest(videoid)
        url = manifest['links']['events']['href']

        if previous_data.get('xid') in self.banned_events_ids:
            common.warn('EVENT [{}] - Not added to the queue. The xid {} is banned due to a previous failed request',
                        event_type, previous_data.get('xid'))
            return

        from resources.lib.services.msl.msl_request_builder import MSLRequestBuilder
        request_data = MSLRequestBuilder.build_request_data(url,
                                                            self._build_event_params(event_type,
                                                                                     event_data,
                                                                                     player_state,
                                                                                     manifest))
        try:
            self.queue_events.put_nowait(Event(request_data, event_data))
        except queue.Full:
            common.warn('EVENT [{}] - Not added to the queue. The event queue is full.', event_type)

    def clear_queue(self):
        """Clear all queued events"""
        with self.queue_events.mutex:
            self.queue_events.queue.clear()
        self.cache_data_events = {}
        self.banned_events_ids = []

    def _build_event_params(self, event_type, event_data, player_state, manifest):
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
        #     list_id = g.LOCAL_DB.get_value('last_menu_id', 'unknown')

        if msl_utils.is_media_changed(previous_player_state, player_state):
            play_times, media_id = msl_utils.build_media_tag(player_state, manifest)
        else:
            play_times = previous_data['playTimes']
            msl_utils.update_play_times_duration(play_times, player_state)
            media_id = previous_data['mediaId']

        params = {
            'event': event_type,
            'xid': previous_data.get('xid', g.LOCAL_DB.get_value('xid', table=TABLE_SESSION)),
            'position': player_state['elapsed_seconds'] * 1000,  # Video time elapsed
            'clientTime': timestamp,
            'sessionStartTime': previous_data.get('sessionStartTime', timestamp),
            'mediaId': media_id,
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
                    # Add 'lolomo_id' seems to prevent failure of the 'refreshListByContext' request
                    'lolomo_id': g.LOCAL_DB.get_value('lolomo_root_id', '', TABLE_SESSION),  # not mandatory
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


def get_manifest(videoid):
    """Get the manifest from cache"""
    cache_identifier = g.get_esn() + '_' + videoid.value
    return g.CACHE.get(CACHE_MANIFESTS, cache_identifier)
