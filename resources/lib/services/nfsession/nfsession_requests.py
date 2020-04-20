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

import json
import requests

import resources.lib.common as common
import resources.lib.api.website as website
from resources.lib.globals import g
from resources.lib.services.nfsession.nfsession_base import NFSessionBase, needs_login
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.api.exceptions import (APIError, WebsiteParsingError,
                                          InvalidMembershipStatusError, InvalidMembershipStatusAnonymous,
                                          LoginValidateErrorIncorrectPassword)
from resources.lib.services.nfsession.nfsession_endpoints import ENDPOINTS, BASE_URL


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
        endpoint_conf = ENDPOINTS[component]
        url = (_api_url(endpoint_conf['address'])
               if endpoint_conf['is_api_call']
               else _document_url(endpoint_conf['address']))
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
        common.debug('Request returned statuscode {}', response.status_code)
        if response.status_code in [404, 401] and not session_refreshed:
            # 404 - It may happen when Netflix update the build_identifier version and causes the api address to change
            # 401 - It may happen when authURL is not more valid (Unauthorized for url)
            # So let's try refreshing the session data (just once)
            common.warn('Try refresh session data due to {} http error', response.status_code)
            if self.try_refresh_session_data():
                return self._request(method, component, True, **kwargs)
        response.raise_for_status()
        return (_raise_api_error(response.json() if response.content else {})
                if endpoint_conf['is_api_call']
                else response.content)

    def try_refresh_session_data(self, raise_exception=False):
        """Refresh session_data from the Netflix website"""
        # pylint: disable=broad-except
        try:
            self.auth_url = website.extract_session_data(self._get('profiles'))['auth_url']
            self.update_session_data()
            common.debug('Successfully refreshed session data')
            return True
        except InvalidMembershipStatusError:
            raise
        except (WebsiteParsingError, InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword) as exc:
            # Possible known causes:
            # -Cookies may not work anymore most likely due to updates in the website
            # -Login password has been changed
            # -Expired cookie profiles? might cause InvalidMembershipStatusAnonymous (i am not really sure)
            import traceback
            common.warn('Failed to refresh session data, login can be expired or the password has been changed ({})',
                        type(exc).__name__)
            common.debug(g.py2_decode(traceback.format_exc(), 'latin-1'))
            self.session.cookies.clear()
            if isinstance(exc, (InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword)):
                # This prevent the MSL error: No entity association record found for the user
                common.send_signal(signal=common.Signals.CLEAR_USER_ID_TOKENS)
            return self._login()
        except requests.exceptions.RequestException:
            import traceback
            common.warn('Failed to refresh session data, request error (RequestException)')
            common.warn(g.py2_decode(traceback.format_exc(), 'latin-1'))
            if raise_exception:
                raise
        except Exception:
            import traceback
            common.warn('Failed to refresh session data, login expired (Exception)')
            common.debug(g.py2_decode(traceback.format_exc(), 'latin-1'))
            self.session.cookies.clear()
            if raise_exception:
                raise
        return False

    def _login(self, modal_error_message=False):
        raise NotImplementedError

    def _prepare_request_properties(self, endpoint_conf, kwargs):
        data = kwargs.get('data', {})
        custom_headers = kwargs.get('headers', {})
        custom_params = kwargs.get('params', {})
        params = {}

        headers = {'Accept': '*/*'}
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
                'isLocoSupported': 'false',
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


def _document_url(endpoint_address):
    return BASE_URL + endpoint_address


def _api_url(endpoint_address):
    return '{baseurl}{endpoint_adr}'.format(
        baseurl=g.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        endpoint_adr=endpoint_address)


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response
