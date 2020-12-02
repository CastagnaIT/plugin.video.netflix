# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Handle the authentication access

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import re

from future.utils import raise_from

import resources.lib.utils.website as website
import resources.lib.common as common
import resources.lib.utils.cookies as cookies
import resources.lib.kodi.ui as ui
from resources.lib.utils.esn import get_esn
from resources.lib.common.exceptions import (LoginValidateError, NotConnected, NotLoggedInError,
                                             MbrStatusNeverMemberError, MbrStatusFormerMemberError, LoginError,
                                             MissingCredentialsError, MbrStatusAnonymousError, WebsiteParsingError)
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.services.nfsession.session.cookie import SessionCookie
from resources.lib.services.nfsession.session.http_requests import SessionHTTPRequests
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class SessionAccess(SessionCookie, SessionHTTPRequests):
    """Handle the authentication access"""

    @measure_exec_time_decorator(is_immediate=True)
    def prefetch_login(self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it"""
        from requests import exceptions
        try:
            common.get_credentials()
            if not self.is_logged_in():
                self.login()
            return True
        except MissingCredentialsError:
            pass
        except exceptions.RequestException as exc:
            # It was not possible to connect to the web service, no connection, network problem, etc
            import traceback
            LOG.error('Login prefetch: request exception {}', exc)
            LOG.debug(G.py2_decode(traceback.format_exc(), 'latin-1'))
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warn('Login prefetch: failed {}', exc)
        return False

    def assert_logged_in(self):
        """Raise an exception when login cannot be established or maintained"""
        if not common.is_internet_connected():
            raise NotConnected('Internet connection not available')
        if not self.is_logged_in():
            raise NotLoggedInError

    def is_logged_in(self):
        """Check if there are valid login data"""
        valid_login = self._load_cookies() and self._verify_session_cookies() and self._verify_esn_existence()
        return valid_login

    @staticmethod
    def _verify_esn_existence():
        return bool(get_esn())

    def get_safe(self, endpoint, **kwargs):
        """
        Before execute a GET request to the designated endpoint,
        check the connection and the validity of the login
        """
        self.assert_logged_in()
        return self.get(endpoint, **kwargs)

    def post_safe(self, endpoint, **kwargs):
        """
        Before execute a POST request to the designated endpoint,
        check the connection and the validity of the login
        """
        self.assert_logged_in()
        return self.post(endpoint, **kwargs)

    @measure_exec_time_decorator(is_immediate=True)
    def login_auth_data(self, data=None, password=None):
        """Perform account login with authentication data"""
        from requests import exceptions
        LOG.debug('Logging in with authentication data')
        # Add the cookies to the session
        self.session.cookies.clear()
        for cookie in data['cookies']:
            self.session.cookies.set(cookie[0], cookie[1], **cookie[2])
        cookies.log_cookie(self.session.cookies)
        # Try access to website
        try:
            website.extract_session_data(self.get('browse'), validate=True, update_profiles=True)
        except MbrStatusAnonymousError:
            # Access not valid
            return False
        # Get the account e-mail
        page_response = self.get('your_account').decode('utf-8')
        email_match = re.search(r'account-email[^<]+>([^<]+@[^</]+)</', page_response)
        email = email_match.group(1).strip() if email_match else None
        if not email:
            raise WebsiteParsingError('E-mail field not found')
        # Verify the password (with parental control api)
        try:
            response = self.post_safe('profile_hub',
                                      data={'destination': 'contentRestrictions',
                                            'guid': G.LOCAL_DB.get_active_profile_guid(),
                                            'password': password,
                                            'task': 'auth'})
            if response.get('status') != 'ok':
                raise LoginError(common.get_local_string(12344))  # 12344=Passwords entered did not match.
        except exceptions.HTTPError as exc:
            if exc.response.status_code == 500:
                # This endpoint raise HTTP error 500 when the password is wrong
                raise_from(LoginError(common.get_local_string(12344)), exc)
            raise
        common.set_credentials({'email': email, 'password': password})
        LOG.info('Login successful')
        ui.show_notification(common.get_local_string(30109))
        cookies.save(self.session.cookies)
        return True

    @measure_exec_time_decorator(is_immediate=True)
    def login(self, credentials=None):
        """Perform account login with credentials"""
        try:
            # First we get the authentication url without logging in, required for login API call
            self.session.cookies.clear()
            react_context = website.extract_json(self.get('login'), 'reactContext')
            auth_url = website.extract_api_data(react_context)['auth_url']
            LOG.debug('Logging in with credentials')
            login_response = self.post(
                'login',
                headers={'Accept-Language': _get_accept_language_string(react_context)},
                data=_login_payload(credentials or common.get_credentials(), auth_url, react_context))

            website.extract_session_data(login_response, validate=True, update_profiles=True)
            if credentials:
                # Save credentials only when login has succeeded
                common.set_credentials(credentials)
            LOG.info('Login successful')
            ui.show_notification(common.get_local_string(30109))
            cookies.save(self.session.cookies)
            return True
        except LoginValidateError as exc:
            self.session.cookies.clear()
            common.purge_credentials()
            raise_from(LoginError(unicode(exc)), exc)
        except (MbrStatusNeverMemberError, MbrStatusFormerMemberError) as exc:
            self.session.cookies.clear()
            LOG.warn('Membership status {} not valid for login', exc)
            raise_from(LoginError(common.get_local_string(30180)), exc)
        except Exception:  # pylint: disable=broad-except
            self.session.cookies.clear()
            import traceback
            LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
            raise

    @measure_exec_time_decorator(is_immediate=True)
    def logout(self):
        """Logout of the current account and reset the session"""
        LOG.debug('Logging out of current account')

        # Perform the website logout
        self.get('logout')

        G.settings_monitor_suspend(True)

        # Disable and reset auto-update / auto-sync features
        G.ADDON.setSettingInt('lib_auto_upd_mode', 1)
        G.ADDON.setSettingBool('lib_sync_mylist', False)
        G.SHARED_DB.delete_key('sync_mylist_profile_guid')

        # Disable and reset the profile guid of profile auto-selection
        G.LOCAL_DB.set_value('autoselect_profile_guid', '')

        # Disable and reset the selected profile guid for library playback
        G.LOCAL_DB.set_value('library_playback_profile_guid', '')

        G.settings_monitor_suspend(False)

        # Delete cookie and credentials
        self.session.cookies.clear()
        cookies.delete()
        common.purge_credentials()

        # Reset the ESN obtained from website/generated
        G.LOCAL_DB.set_value('esn', '', TABLE_SESSION)

        # Reinitialize the MSL handler (delete msl data file, then reset everything)
        common.send_signal(signal=common.Signals.REINITIALIZE_MSL_HANDLER, data=True)

        G.CACHE.clear(clear_database=True)

        LOG.info('Logout successful')
        ui.show_notification(common.get_local_string(30113))
        self._init_session()
        common.container_update('path', True)  # Go to a fake page to clear screen
        # Open root page
        common.container_update(G.BASE_URL, True)


def _login_payload(credentials, auth_url, react_context):
    country_id = react_context['models']['loginContext']['data']['geo']['requestCountry']['id']
    country_codes = react_context['models']['countryCodes']['data']['codes']
    try:
        country_code = '+' + next(dict_item for dict_item in country_codes if dict_item["id"] == country_id)['code']
    except StopIteration:
        country_code = ''
    # 25/08/2020 since a few days there are login problems, by returning the "incorrect password" error even
    #   when it is correct, it seems that setting 'rememberMe' to 'false' increases a bit the probabilities of success
    return {
        'userLoginId': credentials.get('email'),
        'password': credentials.get('password'),
        'rememberMe': 'false',
        'flow': 'websiteSignUp',
        'mode': 'login',
        'action': 'loginAction',
        'withFields': 'rememberMe,nextPage,userLoginId,password,countryCode,countryIsoCode',
        'authURL': auth_url,
        'nextPage': '',
        'showPassword': '',
        'countryCode': country_code,
        'countryIsoCode': country_id
    }


def _get_accept_language_string(react_context):
    # Set the HTTP header 'Accept-Language' allow to get http strings in the right language,
    # and also influence the reactContext data (locale data and messages strings).
    # Locale is usually automatically determined by the browser,
    # we try get the locale code by reading the locale set as default in the reactContext.
    supported_locales = react_context['models']['loginContext']['data']['geo']['supportedLocales']
    try:
        locale = next(dict_item for dict_item in supported_locales if dict_item["default"] is True)['locale']
    except StopIteration:
        locale = ''
    locale_fallback = 'en-US'
    if locale and locale != locale_fallback:
        return '{loc},{loc_l};q=0.9,{loc_fb};q=0.8,{loc_fb_l};q=0.7'.format(
            loc=locale, loc_l=locale[:2],
            loc_fb=locale_fallback, loc_fb_l=locale_fallback[:2])
    return '{loc},{loc_l};q=0.9'.format(
        loc=locale_fallback, loc_l=locale_fallback[:2])
