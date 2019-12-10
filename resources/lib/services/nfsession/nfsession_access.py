# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Stateful Netflix session management: handle the authentication access

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import requests

import xbmc

import resources.lib.common as common
import resources.lib.common.cookies as cookies
import resources.lib.api.website as website
import resources.lib.kodi.ui as ui
from resources.lib.globals import g
from resources.lib.services.nfsession.nfsession_requests import NFSessionRequests
from resources.lib.services.nfsession.nfsession_cookie import NFSessionCookie
from resources.lib.api.exceptions import (LoginFailedError, LoginValidateError,
                                          MissingCredentialsError, InvalidMembershipStatusError)

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class NFSessionAccess(NFSessionRequests, NFSessionCookie):
    """Handle the authentication access"""

    @common.time_execution(immediate=True)
    def prefetch_login(self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it"""
        try:
            common.get_credentials()
            if not self._is_logged_in():
                self._login()
            self.is_prefetch_login = True
        except requests.exceptions.RequestException as exc:
            # It was not possible to connect to the web service, no connection, network problem, etc
            import traceback
            common.error('Login prefetch: request exception {}', exc)
            common.debug(traceback.format_exc())
        except MissingCredentialsError:
            common.info('Login prefetch: No stored credentials are available')
        except (LoginFailedError, LoginValidateError):
            ui.show_notification(common.get_local_string(30009))
        except InvalidMembershipStatusError:
            ui.show_notification(common.get_local_string(30180), time=10000)

    @common.time_execution(immediate=True)
    def _is_logged_in(self):
        """Check if the user is logged in and if so refresh session data"""
        valid_login = self._load_cookies() and \
            self._verify_session_cookies() and \
            self._verify_esn_existence()
        if valid_login and not self.is_prefetch_login:
            self.set_session_header_data()
        return valid_login

    def _verify_esn_existence(self):
        # if for any reason esn is no longer exist get one
        if not g.get_esn():
            return self.try_refresh_session_data()
        return True

    @common.addonsignals_return_call
    def login(self):
        """AddonSignals interface for login function"""
        return self._login(modal_error_message=True)

    @common.time_execution(immediate=True)
    def _login(self, modal_error_message=False):
        """Perform account login"""
        # If exists get the current esn value before extract a new session data
        current_esn = g.get_esn()
        try:
            # First we get the authentication url without logging in, required for login API call
            react_context = website.extract_json(self._get('profiles'), 'reactContext')
            auth_url = website.extract_api_data(react_context)['auth_url']
            common.debug('Logging in...')
            login_response = self._post(
                'login',
                data=_login_payload(common.get_credentials(), auth_url))
            try:
                website.validate_login(login_response)
                website.extract_session_data(login_response)
                common.info('Login successful')
                ui.show_notification(common.get_local_string(30109))
                self.update_session_data(current_esn)
                return True
            except LoginValidateError as exc:
                self.session.cookies.clear()
                common.purge_credentials()
                if not modal_error_message:
                    raise
                ui.show_ok_dialog(common.get_local_string(30008), unicode(exc))
        except InvalidMembershipStatusError:
            ui.show_error_info(common.get_local_string(30008),
                               common.get_local_string(30180),
                               False, True)
        except Exception:  # pylint: disable=broad-except
            import traceback
            common.error(traceback.format_exc())
            self.session.cookies.clear()
            raise
        return False

    @common.addonsignals_return_call
    @common.time_execution(immediate=True)
    def logout(self, url):
        """Logout of the current account and reset the session"""
        common.debug('Logging out of current account')

        # Disable and reset auto-update / auto-sync features
        g.settings_monitor_suspend(True)
        g.ADDON.setSettingInt('lib_auto_upd_mode', 0)
        g.ADDON.setSettingBool('lib_sync_mylist', False)
        g.settings_monitor_suspend(False)
        g.SHARED_DB.delete_key('sync_mylist_profile_guid')

        cookies.delete(self.account_hash)
        self._get('logout')
        common.purge_credentials()

        common.info('Logout successful')
        ui.show_notification(common.get_local_string(30113))
        self._init_session()
        xbmc.executebuiltin('Container.Update(path,replace)')  # Go to a fake page to clear screen
        # Open root page
        xbmc.executebuiltin('Container.Update({},replace)'.format(url))  # replace=reset history


def _login_payload(credentials, auth_url):
    return {
        'userLoginId': credentials.get('email'),
        'email': credentials.get('email'),
        'password': credentials.get('password'),
        'rememberMe': 'true',
        'flow': 'websiteSignUp',
        'mode': 'login',
        'action': 'loginAction',
        'withFields': 'rememberMe,nextPage,userLoginId,password,email',
        'authURL': auth_url,
        'nextPage': '',
        'showPassword': ''
    }
