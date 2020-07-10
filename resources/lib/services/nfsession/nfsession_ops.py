# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Provides methods to perform operations within the Netflix session

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.api.website as website
import resources.lib.common as common
from resources.lib.api.exceptions import (NotLoggedInError, MissingCredentialsError, WebsiteParsingError,
                                          InvalidMembershipStatusAnonymous, LoginValidateErrorIncorrectPassword)
from resources.lib.common import cookies
from resources.lib.globals import g
from resources.lib.services.nfsession.session.path_requests import SessionPathRequests


class NFSessionOperations(SessionPathRequests):
    """Provides methods to perform operations within the Netflix session"""

    def __init__(self):
        super(NFSessionOperations, self).__init__()
        # Slot allocation for IPC
        self.slots = [
            self.get_safe,
            self.post_safe,
            self.login,
            self.logout,
            self.path_request,
            self.perpetual_path_request,
            self.callpath_request,
            self.fetch_initial_page,
            self.activate_profile,
            self.parental_control_data
        ]
        self.is_profile_session_active = False
        # Share the activate profile function to SessionBase class
        self.external_func_activate_profile = self.activate_profile

    @common.time_execution(immediate=True)
    def fetch_initial_page(self):
        """Fetch initial page"""
        common.debug('Fetch initial page')
        response = self.get_safe('browse')
        # Update the session data, the profiles data to the database, and update the authURL
        api_data = self.website_extract_session_data(response, update_profiles=True)
        self.auth_url = api_data['auth_url']
        # Check if the profile session is still active, used only to activate_profile
        self.is_profile_session_active = api_data['is_profile_session_active']

    @common.time_execution(immediate=True)
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.debug('Switching to profile {}', guid)
        current_active_guid = g.LOCAL_DB.get_active_profile_guid()
        if self.is_profile_session_active and guid == current_active_guid:
            common.info('The profile session of guid {} is still active, activation not needed.', guid)
            return
        import time
        timestamp = time.time()
        common.info('Activating profile {}', guid)
        # 20/05/2020 - The method 1 not more working for switching PIN locked profiles
        # INIT Method 1 - HTTP mode
        # response = self._get('switch_profile', params={'tkn': guid})
        # self.nfsession.auth_url = self.website_extract_session_data(response)['auth_url']
        # END Method 1
        # INIT Method 2 - API mode
        self.get_safe(endpoint='activate_profile',
                      params={'switchProfileGuid': guid,
                              '_': int(timestamp * 1000),
                              'authURL': self.auth_url})
        # Retrieve browse page to update authURL
        response = self.get_safe('browse')
        self.auth_url = website.extract_session_data(response)['auth_url']
        # END Method 2

        self.is_profile_session_active = True
        g.LOCAL_DB.switch_active_profile(guid)
        g.CACHE_MANAGEMENT.identifier_prefix = guid
        cookies.save(self.account_hash, self.session.cookies)

    def parental_control_data(self, password):
        # Ask to the service if password is right and get the PIN status
        from requests import exceptions
        profile_guid = g.LOCAL_DB.get_active_profile_guid()
        try:
            response = self.post_safe('profile_hub',
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
        response_content = self.get_safe('restrictions',
                                         data={'password': password},
                                         append_to_address=profile_guid)
        extracted_content = website.extract_parental_control_data(response_content, response['maturity'])
        response['profileInfo']['profileName'] = website.parse_html(response['profileInfo']['profileName'])
        extracted_content['data'] = response
        return extracted_content

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
