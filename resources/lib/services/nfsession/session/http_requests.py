# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Manages the HTTP requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json

from future.utils import raise_from

import resources.lib.utils.website as website
import resources.lib.common as common
from resources.lib.common.exceptions import (APIError, WebsiteParsingError, MbrStatusError, MbrStatusAnonymousError,
                                             HttpError401, NotLoggedInError)
from resources.lib.kodi import ui
from resources.lib.utils import cookies
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.services.nfsession.session.base import SessionBase
from resources.lib.services.nfsession.session.endpoints import ENDPOINTS, BASE_URL
from resources.lib.utils.logging import LOG, measure_exec_time_decorator, perf_clock


class SessionHTTPRequests(SessionBase):
    """Manages the HTTP requests"""

    def get(self, endpoint, **kwargs):
        """Execute a GET request to the designated endpoint."""
        return self._request_call(
            method=self.session.get,
            endpoint=endpoint,
            **kwargs)

    def post(self, endpoint, **kwargs):
        """Execute a POST request to the designated endpoint."""
        return self._request_call(
            method=self.session.post,
            endpoint=endpoint,
            **kwargs)

    @measure_exec_time_decorator(is_immediate=True)
    def _request_call(self, method, endpoint, **kwargs):
        return self._request(method, endpoint, None, **kwargs)

    def _request(self, method, endpoint, session_refreshed, **kwargs):
        endpoint_conf = ENDPOINTS[endpoint]
        url = (_api_url(endpoint_conf['address'])
               if endpoint_conf['is_api_call']
               else _document_url(endpoint_conf['address'], kwargs))
        LOG.debug('Executing {verb} request to {url}',
                  verb='GET' if method == self.session.get else 'POST', url=url)
        data, headers, params = self._prepare_request_properties(endpoint_conf, kwargs)
        start = perf_clock()
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=params,
            data=data)
        LOG.debug('Request took {}s', perf_clock() - start)
        LOG.debug('Request returned status code {}', response.status_code)
        # for redirect in response.history:
        #     LOG.warn('Redirected to: [{}] {}', redirect.status_code, redirect.url)
        if not session_refreshed:
            # We refresh the session when happen:
            # Error 404: It happen when Netflix update the build_identifier version and causes the api address to change
            # Error 401: This is a generic error, can happen when the http request for some reason has failed,
            #   we allow the refresh only for shakti endpoint, sometimes for unknown reasons it is necessary to update
            #   the session for the request to be successful
            if response.status_code == 404 or (response.status_code == 401 and endpoint == 'shakti'):
                LOG.warn('Attempt to refresh the session due to HTTP error {}', response.status_code)
                if self.try_refresh_session_data():
                    return self._request(method, endpoint, True, **kwargs)
        if response.status_code == 401:
            raise HttpError401
        response.raise_for_status()
        return (_raise_api_error(response.json() if response.content else {})
                if endpoint_conf['is_api_call']
                else response.content)

    def try_refresh_session_data(self, raise_exception=False):
        """Refresh session data from the Netflix website"""
        from requests import exceptions
        try:
            self.auth_url = website.extract_session_data(self.get('browse'))['auth_url']
            cookies.save(self.session.cookies)
            LOG.debug('Successfully refreshed session data')
            return True
        except MbrStatusError:
            raise
        except (WebsiteParsingError, MbrStatusAnonymousError) as exc:
            import traceback
            LOG.warn('Failed to refresh session data, login can be expired or the password has been changed ({})',
                     type(exc).__name__)
            LOG.debug(G.py2_decode(traceback.format_exc(), 'latin-1'))
            self.session.cookies.clear()
            if isinstance(exc, MbrStatusAnonymousError):
                # This prevent the MSL error: No entity association record found for the user
                common.send_signal(signal=common.Signals.CLEAR_USER_ID_TOKENS)
            # Needed to do a new login
            common.purge_credentials()
            ui.show_notification(common.get_local_string(30008))
            raise_from(NotLoggedInError, exc)
        except exceptions.RequestException:
            import traceback
            LOG.warn('Failed to refresh session data, request error (RequestException)')
            LOG.warn(G.py2_decode(traceback.format_exc(), 'latin-1'))
            if raise_exception:
                raise
        except Exception:  # pylint: disable=broad-except
            import traceback
            LOG.warn('Failed to refresh session data, login expired (Exception)')
            LOG.debug(G.py2_decode(traceback.format_exc(), 'latin-1'))
            self.session.cookies.clear()
            if raise_exception:
                raise
        return False

    def _prepare_request_properties(self, endpoint_conf, kwargs):
        data = kwargs.get('data', {})
        custom_headers = kwargs.get('headers', {})
        custom_params = kwargs.get('params', {})
        params = {}

        headers = {'Accept': endpoint_conf.get('accept', '*/*')}
        if endpoint_conf['address'] not in ['/login', '/browse', '/SignOut', '/YourAccount']:
            headers['x-netflix.nq.stack'] = 'prod'
            headers['x-netflix.request.client.user.guid'] = G.LOCAL_DB.get_active_profile_guid()
        if endpoint_conf.get('content_type'):
            headers['Content-Type'] = endpoint_conf['content_type']
        headers.update(custom_headers)  # If needed override headers
        # Meanings parameters known:
        # drmSystem       DRM used
        # falcor_server   Use JSON Graph (responses like browser)
        # withSize        Puts the 'size' field inside each dictionary
        # materialize     If True, when a path that no longer exists is requested (like 'storyarts')
        #                   it is still added in an 'empty' form in the response
        if endpoint_conf['use_default_params']:
            params = {
                'drmSystem': 'widevine',
                'withSize': 'false',
                'materialize': 'false',
                'routeAPIRequestsThroughFTL': 'false',
                'isVolatileBillboardsEnabled': 'true',
                'isTop10Supported': 'true',
                'categoryCraversEnabled': 'false',
                'original_path': '/shakti/{}/pathEvaluator'.format(
                    G.LOCAL_DB.get_value('build_identifier', '', TABLE_SESSION))
            }
        if endpoint_conf['add_auth_url'] == 'to_params':
            params['authURL'] = self.auth_url
        params.update(custom_params)  # If needed override parameters

        # The 'data' can be passed in two types: as string, as dict
        if isinstance(data, dict):
            if endpoint_conf['add_auth_url'] == 'to_data':
                data['authURL'] = self.auth_url
            if endpoint_conf.get('content_type') == 'application/x-www-form-urlencoded':
                data_converted = data  # In this case Requests module convert the data automatically
            else:
                data_converted = json.dumps(data, separators=(',', ':'))  # Netflix rejects spaces
        else:
            # Special case used by path_request/callpath_request in path_requests.py
            data_converted = data
            if endpoint_conf['add_auth_url'] == 'to_data':
                auth_data = 'authURL=' + self.auth_url
                data_converted += '&' + auth_data if data_converted else auth_data
        return data_converted, headers, params


def _document_url(endpoint_address, kwargs):
    if 'append_to_address' in kwargs:
        endpoint_address = endpoint_address.format(kwargs['append_to_address'])
    return BASE_URL + endpoint_address


def _api_url(endpoint_address):
    return '{baseurl}{endpoint_adr}'.format(
        baseurl=G.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        endpoint_adr=endpoint_address)


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response
