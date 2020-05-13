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

import resources.lib.common as common
import resources.lib.api.paths as apipaths
import resources.lib.api.website as website
from resources.lib.globals import g
from resources.lib.services.directorybuilder.dir_builder import DirectoryBuilder
from resources.lib.services.nfsession.nfsession_access import NFSessionAccess
from resources.lib.services.nfsession.nfsession_base import needs_login
from resources.lib.api.exceptions import (NotLoggedInError, MissingCredentialsError, WebsiteParsingError,
                                          InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword)


class NetflixSession(NFSessionAccess, DirectoryBuilder):
    """Stateful netflix session management"""

    def __init__(self):
        NFSessionAccess.__init__(self)
        DirectoryBuilder.__init__(self, self)
        self.slots = [
            self.fetch_initial_page,
            self.login,
            self.logout,
            self.activate_profile,
            self.parental_control_data,
            self.path_request,
            self.perpetual_path_request,
            self.callpath_request,
            self.get,
            self.post
        ]
        for slot in self.slots:
            common.register_slot(slot)
        self.prefetch_login()
        self.is_profile_session_active = False

    @common.addonsignals_return_call
    @needs_login
    def parental_control_data(self, password):
        # Ask to the service if password is right and get the PIN status
        from requests import exceptions
        profile_guid = g.LOCAL_DB.get_active_profile_guid()
        try:
            response = self._post('profile_hub',
                                  data={'destination': 'contentRestrictions',
                                        'guid': profile_guid,
                                        'password': password,
                                        'task': 'auth'})
            if response.get('status') != 'ok':
                common.warn('Parental control status issue: {}', response)
                raise MissingCredentialsError
        except exceptions.HTTPError as exc:
            if exc.response.status_code == 500:
                # This endpoint raise HTTP error 500 when the password is wrong
                raise MissingCredentialsError
            raise
        # Warning - parental control levels vary by country or region, no fixed values can be used
        # Note: The language of descriptions change in base of the language of selected profile
        response_content = self._get('restrictions', data={'password': password}, append_to_address=profile_guid)
        extracted_content = website.extract_parental_control_data(response_content, response['maturity'])
        response['profileInfo']['profileName'] = website.parse_html(response['profileInfo']['profileName'])
        extracted_content['data'] = response
        return extracted_content

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    @needs_login
    def fetch_initial_page(self):
        """Fetch initial page"""
        common.debug('Fetch initial page')
        response = self._get('browse')
        # Update the session data, the profiles data to the database, and update the authURL
        api_data = self.website_extract_session_data(response, update_profiles=True)
        self.auth_url = api_data['auth_url']
        # Check if the profile session is still active, used only to activate_profile
        self.is_profile_session_active = api_data['is_profile_session_active']

    @common.time_execution(immediate=True)
    @common.addonsignals_return_call
    @needs_login
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.debug('Switching to profile {}', guid)
        current_active_guid = g.LOCAL_DB.get_active_profile_guid()
        if self.is_profile_session_active and guid == current_active_guid:
            common.info('The profile session of guid {} is still active, activation not needed.', guid)
        if not self.is_profile_session_active or (self.is_profile_session_active and
                                                  guid != current_active_guid):
            common.info('Activating profile {}', guid)
            # INIT Method 1 - HTTP mode
            response = self._get('switch_profile', params={'tkn': guid})
            self.auth_url = self.website_extract_session_data(response)['auth_url']
            # END Method 1
            # INIT Method 2 - API mode
            # import time
            # self._get(endpoint='activate_profile',
            #           params={'switchProfileGuid': guid,
            #                   '_': int(time.time()),
            #                   'authURL': self.auth_url})
            # # Retrieve browse page to update authURL
            # response = self._get('browse')
            # self.auth_url = website.extract_session_data(response)['auth_url']
            # END Method 2
            self.is_profile_session_active = True
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
    def _path_request(self, paths, use_jsongraph=False):
        """Execute a path request with static paths"""
        common.debug('Executing path request: {}', json.dumps(paths))
        custom_params = {'method': 'call'}
        if use_jsongraph:
            custom_params['falcor_server'] = '0.1.0'
        # Use separators with dumps because Netflix rejects spaces
        data = 'path=' + '&path='.join(json.dumps(path, separators=(',', ':')) for path in paths)
        response = self._post(
            endpoint='shakti',
            params=custom_params,
            data=data)
        return response['jsonGraph'] if use_jsongraph else response['value']

    @common.addonsignals_return_call
    @needs_login
    def callpath_request(self, callpaths, params=None, path_suffixs=None):
        """Perform a callPath request against the Shakti API"""
        return self._callpath_request(callpaths, params, path_suffixs)

    @common.time_execution(immediate=True)
    def _callpath_request(self, callpaths, params=None, path_suffixs=None):
        """Execute a callPath request with static paths"""
        common.debug('Executing callPath request: {} params: {} path_suffixs: {}',
                     json.dumps(callpaths),
                     params,
                     json.dumps(path_suffixs))
        custom_params = {
            'falcor_server': '0.1.0',
            'method': 'call',
            'withSize': 'true',
            'materialize': 'true',
        }
        # Use separators with dumps because Netflix rejects spaces
        data = 'callPath=' + '&callPath='.join(
            json.dumps(callpath, separators=(',', ':')) for callpath in callpaths)
        if params:
            # The data to pass on 'params' must not be formatted with json.dumps because it is not full compatible
            #          if the request have wrong data will raise error 401
            #          if the parameters are not formatted correctly will raise error 401
            data += '&param=' + '&param='.join(params)
        if path_suffixs:
            data += '&pathSuffix=' + '&pathSuffix='.join(
                json.dumps(path_suffix, separators=(',', ':')) for path_suffix in path_suffixs)
        # common.debug('callPath request data: {}', data)
        response_data = self._post(
            endpoint='shakti',
            params=custom_params,
            data=data)
        return response_data['jsonGraph']

    def website_extract_session_data(self, content, **kwargs):
        """Extract session data and handle errors"""
        try:
            return website.extract_session_data(content, **kwargs)
        except (WebsiteParsingError, InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword) as exc:
            common.warn('Session data not valid, login can be expired or the password has been changed ({})',
                        type(exc).__name__)
            if isinstance(exc, (InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword)):
                common.purge_credentials()
                self.session.cookies.clear()
                common.send_signal(signal=common.Signals.CLEAR_USER_ID_TOKENS)
                raise NotLoggedInError
            raise


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
