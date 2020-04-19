# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Stateful Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json
import requests

import resources.lib.common as common
import resources.lib.api.paths as apipaths
import resources.lib.api.website as website
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from resources.lib.services.directorybuilder.dir_builder import DirectoryBuilder
from resources.lib.services.nfsession.nfsession_access import NFSessionAccess
from resources.lib.services.nfsession.nfsession_base import needs_login
from resources.lib.api.exceptions import MissingCredentialsError


class NetflixSession(NFSessionAccess, DirectoryBuilder):
    """Stateful netflix session management"""

    def __init__(self):
        NFSessionAccess.__init__(self)
        DirectoryBuilder.__init__(self, self)
        self.slots = [
            self.login,
            self.logout,
            self.activate_profile,
            self.parental_control_data,
            self.path_request,
            self.perpetual_path_request,
            self.callpath_request,
            self.get,
            self.post,
            self.startup_requests_module
        ]
        for slot in self.slots:
            common.register_slot(slot)
        self.prefetch_login()

    @common.addonsignals_return_call
    @needs_login
    def parental_control_data(self, password):
        # Ask to the service if password is right and get the PIN status
        try:
            pin_response = self._post('pin_reset',
                                      data={'task': 'auth',
                                            'authURL': self.auth_url,
                                            'password': password})
            if pin_response.get('status') != 'ok':
                common.warn('Parental control status issue: {}', pin_response)
                raise MissingCredentialsError
            pin = pin_response.get('pin')
        except requests.exceptions.HTTPError as exc:
            if exc.response.status_code == 401:
                # Unauthorized for url ...
                raise MissingCredentialsError
            raise
        # Warning - parental control levels vary by country or region, no fixed values can be used
        # I have not found how to get it through the API, so parse web page to get all info
        # Note: The language of descriptions change in base of the language of selected profile
        response_content = self._get('pin', data={'password': password})
        extracted_content = website.extract_parental_control_data(response_content)
        extracted_content['pin'] = pin
        return extracted_content

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    @needs_login
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.debug('Switching to profile {}', guid)
        response = self._get('switch_profile', params={'tkn': guid})
        react_context = website.extract_json(response, 'reactContext')
        self.auth_url = website.extract_api_data(react_context)['auth_url']

        # if guid != g.LOCAL_DB.get_active_profile_guid():
        #     common.info('Activating profile {}', guid)
        #     self._get(component='activate_profile',
        #               req_type='api',
        #               params={'switchProfileGuid': guid,
        #                       '_': int(time.time()),
        #                       'authURL': self.auth_url})

        g.LOCAL_DB.switch_active_profile(guid)
        g.CACHE_MANAGEMENT.identifier_prefix = guid
        self.update_session_data()

    @needs_login
    def _perpetual_path_request_switch_profiles(self, paths, length_params,
                                                perpetual_range_start=None, no_limit_req=False):
        """
        Perform a perpetual path request,
        Used exclusively to get My List of a profile other than the current one
        """
        # Profile chosen by the user for the synchronization from which to get My List videos
        mylist_profile_guid = g.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                    g.LOCAL_DB.get_guid_owner_profile())
        # Current profile active
        current_profile_guid = g.LOCAL_DB.get_active_profile_guid()
        # Switch profile (only if necessary) in order to get My List videos
        self.activate_profile(mylist_profile_guid)
        # Get the My List data
        path_response = self._perpetual_path_request(paths, length_params, perpetual_range_start,
                                                     no_limit_req)
        if mylist_profile_guid != current_profile_guid:
            # Reactive again the previous profile
            self.activate_profile(current_profile_guid)
        return path_response

    @common.addonsignals_return_call
    def path_request(self, paths):
        """Perform a path request against the Shakti API"""
        return self._path_request(paths)

    @common.addonsignals_return_call
    def perpetual_path_request(self, paths, length_params, perpetual_range_start=None,
                               no_limit_req=False):
        return self._perpetual_path_request(paths, length_params, perpetual_range_start,
                                            no_limit_req)

    @common.time_execution(immediate=True)
    @needs_login
    def _perpetual_path_request(self, paths, length_params, perpetual_range_start=None,
                                no_limit_req=False):
        """Perform a perpetual path request against the Shakti API to retrieve
        a possibly large video list. If the requested video list's size is
        larger than MAX_PATH_REQUEST_SIZE, multiple path requests will be
        executed with forward shifting range selectors and the results will
        be combined into one path response."""
        response_type, length_args = length_params
        context_name = length_args[0]
        response_length = apipaths.LENGTH_ATTRIBUTES[response_type]

        request_size = apipaths.MAX_PATH_REQUEST_SIZE
        response_size = request_size + 1
        # Note: when the request is made with 'genres' or 'seasons' context,
        # the response strangely does not respect the number of objects
        # requested, returning 1 more item, i couldn't understand why
        if context_name in ['genres', 'seasons']:
            response_size += 1

        number_of_requests = 100 if no_limit_req else 2
        perpetual_range_start = int(perpetual_range_start) if perpetual_range_start else 0
        range_start = perpetual_range_start
        range_end = range_start + request_size
        merged_response = {}

        for n_req in range(number_of_requests):
            path_response = self._path_request(
                _set_range_selector(paths, range_start, range_end))
            if not path_response:
                break
            if not common.check_path_exists(length_args, path_response):
                # It may happen that the number of items to be received
                # is equal to the number of the response_size
                # so a second round will be performed, which will return an empty list
                break
            common.merge_dicts(path_response, merged_response)
            response_count = response_length(path_response, *length_args)
            if response_count < response_size:
                # There are no other elements to request
                break

            range_start += response_size
            if n_req == (number_of_requests - 1):
                merged_response['_perpetual_range_selector'] = {'next_start': range_start}
                common.debug('{} has other elements, added _perpetual_range_selector item', response_type)
            else:
                range_end = range_start + request_size

        if perpetual_range_start > 0:
            previous_start = perpetual_range_start - (response_size * number_of_requests)
            if '_perpetual_range_selector' in merged_response:
                merged_response['_perpetual_range_selector']['previous_start'] = previous_start
            else:
                merged_response['_perpetual_range_selector'] = {'previous_start': previous_start}
        return merged_response

    @common.time_execution(immediate=True)
    @needs_login
    def _path_request(self, paths):
        """Execute a path request with static paths"""
        common.debug('Executing path request: {}', json.dumps(paths))
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/javascript, */*'}

        # params:
        # drmSystem       drm used
        # falcor_server   json responses like browser
        # withSize        puts the 'size' field inside each dictionary
        # materialize     if true, when a path that no longer exists is requested (like 'storyarts')
        #                    it is still added in an 'empty' form in the response
        params = {
            'drmSystem': 'widevine',
            # 'falcor_server': '0.1.0',
            'withSize': 'false',
            'materialize': 'false',
            'routeAPIRequestsThroughFTL': 'false',
            'isVolatileBillboardsEnabled': 'true',
            'isWatchlistEnabled': 'false',
            'original_path': '/shakti/{}/pathEvaluator'.format(
                g.LOCAL_DB.get_value('build_identifier', '', TABLE_SESSION))
        }
        data = 'path=' + '&path='.join(json.dumps(path) for path in paths)
        data += '&authURL=' + self.auth_url
        return self._post(
            component='shakti',
            req_type='api',
            params=params,
            headers=headers,
            data=data)['value']

    @common.addonsignals_return_call
    @needs_login
    def callpath_request(self, callpaths, params=None, path_suffixs=None):
        """Perform a callPath request against the Shakti API"""
        return self._callpath_request(callpaths, params, path_suffixs)

    @common.time_execution(immediate=True)
    def _callpath_request(self, callpaths, params=None, path_suffixs=None):
        """Execute a callPath request with static paths"""
        # Warning: The data to pass on 'params' must not be formatted with json.dumps because it is not full compatible
        #          if the request have wrong data give error 401
        #          if the parameters are not formatted correctly will give error 401
        common.debug('Executing callPath request: {} params: {} path_suffixs: {}',
                     json.dumps(callpaths),
                     params,
                     json.dumps(path_suffixs))
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/javascript, */*'}

        req_params = {
            'drmSystem': 'widevine',
            'falcor_server': '0.1.0',
            'method': 'call',
            'withSize': 'true',
            'materialize': 'true',
            'routeAPIRequestsThroughFTL': 'false',
            'isVolatileBillboardsEnabled': 'true',
            'isWatchlistEnabled': 'false',
            'original_path': '/shakti/{}/pathEvaluator'.format(
                g.LOCAL_DB.get_value('build_identifier', '', TABLE_SESSION))
        }
        data = 'callPath=' + '&callPath='.join(json.dumps(callpath) for callpath in callpaths)
        if params:
            data += '&param=' + '&param='.join(params)
        if path_suffixs:
            data += '&pathSuffix=' + '&pathSuffix='.join(json.dumps(path_suffix) for path_suffix in path_suffixs)
        data += '&authURL=' + self.auth_url
        data = data.replace(' ', '')
        # common.debug('callPath request data: {}', data)
        response_data = self._post(
            component='shakti',
            req_type='api',
            params=req_params,
            headers=headers,
            data=data)
        if 'falcor_server' in req_params:
            return response_data['jsonGraph']
        return response_data['value']


def _set_range_selector(paths, range_start, range_end):
    """Replace the RANGE_SELECTOR placeholder with an actual dict:
    {'from': range_start, 'to': range_end}"""
    import copy
    # Make a deepcopy because we don't want to lose the original paths
    # with the placeholder
    ranged_paths = copy.deepcopy(paths)
    for path in ranged_paths:
        try:
            path[path.index(apipaths.RANGE_SELECTOR)] = (
                {'from': range_start, 'to': range_end})
        except ValueError:
            pass
    return ranged_paths
