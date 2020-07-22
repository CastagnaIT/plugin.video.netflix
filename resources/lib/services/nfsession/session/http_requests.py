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

import resources.lib.api.website as website
import resources.lib.common as common
from resources.lib.api.exceptions import (APIError, WebsiteParsingError,
                                          InvalidMembershipStatusError, InvalidMembershipStatusAnonymous,
                                          LoginValidateErrorIncorrectPassword, HttpError401)
from resources.lib.common import cookies
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from resources.lib.services.nfsession.session.base import SessionBase
from resources.lib.services.nfsession.session.endpoints import ENDPOINTS, BASE_URL


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

    @common.time_execution(immediate=True)
    def _request_call(self, method, endpoint, **kwargs):
        return self._request(method, endpoint, None, **kwargs)

    def _request(self, method, endpoint, session_refreshed, **kwargs):
        endpoint_conf = ENDPOINTS[endpoint]
        url = (_api_url(endpoint_conf['address'])
               if endpoint_conf['is_api_call']
               else _document_url(endpoint_conf['address'], kwargs))
        common.debug('Executing {verb} request to {url}',
                     verb='GET' if method == self.session.get else 'POST', url=url)
        data, headers, params = self._prepare_request_properties(endpoint_conf, kwargs)
        start = common.perf_clock()
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=params,
            data=data)
        common.debug('Request took {}s', common.perf_clock() - start)
        common.debug('Request returned status code {}', response.status_code)
        if response.status_code in [404, 401] and not session_refreshed:
            # 404 - It may happen when Netflix update the build_identifier version and causes the api address to change
            # 401 - It may happen when authURL is not more valid (Unauthorized for url)
            # So let's try refreshing the session data (just once)
            common.warn('Try refresh session data due to {} http error', response.status_code)
            if self.try_refresh_session_data():
                return self._request(method, endpoint, True, **kwargs)
        if response.status_code == 401:
            common.error('Raise error due to too many http error 401')
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
            cookies.save(self.account_hash, self.session.cookies)
            common.debug('Successfully refreshed session data')
            return True
        except InvalidMembershipStatusError:
            raise
        except (WebsiteParsingError, InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword) as exc:
            import traceback
            common.warn('Failed to refresh session data, login can be expired or the password has been changed ({})',
                        type(exc).__name__)
            common.debug(g.py2_decode(traceback.format_exc(), 'latin-1'))
            self.session.cookies.clear()
            if isinstance(exc, (InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword)):
                # This prevent the MSL error: No entity association record found for the user
                common.send_signal(signal=common.Signals.CLEAR_USER_ID_TOKENS)
            return self.external_func_login(modal_error_message=False)  # pylint: disable=not-callable
        except exceptions.RequestException:
            import traceback
            common.warn('Failed to refresh session data, request error (RequestException)')
            common.warn(g.py2_decode(traceback.format_exc(), 'latin-1'))
            if raise_exception:
                raise
        except Exception:  # pylint: disable=broad-except
            import traceback
            common.warn('Failed to refresh session data, login expired (Exception)')
            common.debug(g.py2_decode(traceback.format_exc(), 'latin-1'))
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
        if endpoint_conf['address'] not in ['/login', '/browse', '/SignOut']:
            headers['x-netflix.nq.stack'] = 'prod'
            headers['x-netflix.request.client.user.guid'] = g.LOCAL_DB.get_active_profile_guid()
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
                    g.LOCAL_DB.get_value('build_identifier', '', TABLE_SESSION))
            }
        if endpoint_conf['add_auth_url'] == 'to_params':
            params['authURL'] = self.auth_url
        params.update(custom_params)  # If needed override parameters

        # The 'data' can be passed in two way:
        # - As string (needs to be correctly formatted)
        # - As dict (will be converted as string here)
        if isinstance(data, dict):
            if endpoint_conf['add_auth_url'] == 'to_data':
                data['authURL'] = self.auth_url
            data_converted = json.dumps(data, separators=(',', ':'))  # Netflix rejects spaces
        else:
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
        baseurl=g.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        endpoint_adr=endpoint_address)


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response
