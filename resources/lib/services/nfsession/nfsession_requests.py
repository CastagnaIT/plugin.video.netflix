# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Stateful Netflix session management: handle the http requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time
import json
import requests

import resources.lib.common as common
import resources.lib.api.website as website
from resources.lib.globals import g
from resources.lib.services.nfsession.nfsession_base import NFSessionBase, needs_login
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.api.exceptions import (APIError, WebsiteParsingError,
                                          InvalidMembershipStatusError)

BASE_URL = 'https://www.netflix.com'
"""str: Secure Netflix url"""

URLS = {
    'login': {'endpoint': '/login', 'is_api_call': False},
    'logout': {'endpoint': '/SignOut', 'is_api_call': False},
    'shakti': {'endpoint': '/pathEvaluator', 'is_api_call': True},
    'browse': {'endpoint': '/browse', 'is_api_call': False},
    'profiles': {'endpoint': '/profiles/manage', 'is_api_call': False},
    'activate_profile': {'endpoint': '/profiles/switch', 'is_api_call': True},
    'pin': {'endpoint': '/pin', 'is_api_call': False},
    'pin_reset': {'endpoint': '/pin/reset', 'is_api_call': True},
    'pin_service': {'endpoint': '/pin/service', 'is_api_call': True},
    'metadata': {'endpoint': '/metadata', 'is_api_call': True},
    'set_video_rating': {'endpoint': '/setVideoRating', 'is_api_call': True},  # Old rating system
    'set_thumb_rating': {'endpoint': '/setThumbRating', 'is_api_call': True},
    'update_my_list': {'endpoint': '/playlistop', 'is_api_call': True},
    # Don't know what these could be used for. Keeping for reference
    # 'video_list_ids': {'endpoint': '/preflight', 'is_api_call': True},
    # 'kids': {'endpoint': '/Kids', 'is_api_call': False}
}
# List of all static endpoints for HTML/JSON POST/GET requests
# How many entries of a list will be fetched with one path request


class NFSessionRequests(NFSessionBase):
    """Handle the http requests"""

    @common.addonsignals_return_call
    @needs_login
    def get(self, component, **kwargs):
        """Execute a GET request to the designated component's URL."""
        return self._get(component, **kwargs)

    @common.addonsignals_return_call
    @needs_login
    def post(self, component, **kwargs):
        """Execute a POST request to the designated component's URL."""
        return self._post(component, **kwargs)

    def _get(self, component, **kwargs):
        return self._request_call(
            method=self.session.get,
            component=component,
            **kwargs)

    def _post(self, component, **kwargs):
        return self._request_call(
            method=self.session.post,
            component=component,
            **kwargs)

    @common.time_execution(immediate=True)
    def _request_call(self, method, component, **kwargs):
        return self._request(method, component, None, **kwargs)

    def _request(self, method, component, session_refreshed, **kwargs):
        url = (_api_url(component)
               if URLS[component]['is_api_call']
               else _document_url(component))
        common.debug('Executing {verb} request to {url}',
                     verb='GET' if method == self.session.get else 'POST', url=url)
        data, headers, params = self._prepare_request_properties(component,
                                                                 kwargs)
        start = time.clock()
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=params,
            data=data)
        common.debug('Request took {}s', time.clock() - start)
        common.debug('Request returned statuscode {}', response.status_code)
        if response.status_code == 404 and not session_refreshed:
            # It may happen that netflix updates the build_identifier version
            # when you are watching a video or browsing the menu,
            # this causes the api address to change, and return 'url not found' error
            # So let's try updating the session data (just once)
            common.warn('Try refresh session data to update build_identifier version')
            if self.try_refresh_session_data():
                return self._request(method, component, True, **kwargs)
        response.raise_for_status()
        return (_raise_api_error(response.json() if response.content else {})
                if URLS[component]['is_api_call']
                else response.content)

    def try_refresh_session_data(self, raise_exception=False):
        """Refresh session_data from the Netflix website"""
        # pylint: disable=broad-except
        try:
            website.extract_session_data(self._get('profiles'))
            self.update_session_data()
            common.debug('Successfully refreshed session data')
            return True
        except InvalidMembershipStatusError:
            raise
        except WebsiteParsingError:
            # it is possible that cookies may not work anymore,
            # it should be due to updates in the website,
            # this can happen when opening the addon while executing update_profiles_data
            import traceback
            common.warn('Failed to refresh session data, login expired (WebsiteParsingError)')
            common.debug(traceback.format_exc())
            self.session.cookies.clear()
            return self._login()
        except requests.exceptions.RequestException:
            import traceback
            common.warn('Failed to refresh session data, request error (RequestException)')
            common.warn(traceback.format_exc())
            if raise_exception:
                raise
        except Exception:
            import traceback
            common.warn('Failed to refresh session data, login expired (Exception)')
            common.debug(traceback.format_exc())
            self.session.cookies.clear()
            if raise_exception:
                raise
        return False

    def _login(self, modal_error_message=False):
        raise NotImplementedError

    def _prepare_request_properties(self, component, kwargs):
        data = kwargs.get('data', {})
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', {})
        if component in ['set_video_rating', 'set_thumb_rating', 'update_my_list', 'pin_service']:
            headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/javascript, */*'})
            data['authURL'] = self.auth_url
            data = json.dumps(data)
        return data, headers, params


def _document_url(component):
    return BASE_URL + URLS[component]['endpoint']


def _api_url(component):
    return '{baseurl}{componenturl}'.format(
        baseurl=g.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        componenturl=URLS[component]['endpoint'])


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response
