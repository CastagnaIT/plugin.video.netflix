# -*- coding: utf-8 -*-
"""Stateful Netflix session management"""
from __future__ import unicode_literals

import sys
from time import time
from base64 import urlsafe_b64encode
from functools import wraps
import json
import requests

import resources.lib.common as common
import resources.lib.api.website as website
import resources.lib.services.cookies as cookies
import resources.lib.kodi.ui as ui

BASE_URL = 'https://www.netflix.com'
"""str: Secure Netflix url"""

URLS = {
    'login': {'endpoint': '/login', 'is_api_call': False},
    'shakti': {'endpoint': '/pathEvaluator', 'is_api_call': True},
    'profiles':  {'endpoint': '/profiles/manage', 'is_api_call': False},
    'activate_profile': {'endpoint': '/profiles/switch', 'is_api_call': True},
    'adult_pin': {'endpoint': '/pin/service', 'is_api_call': True},
    'metadata': {'endpoint': '/metadata', 'is_api_call': True},
    'set_video_rating': {'endpoint': '/setVideoRating', 'is_api_call': True},
    'update_my_list': {'endpoint': '/playlistop', 'is_api_call': True},
    # Don't know what these could be used for. Keeping for reference
    # 'browse': {'endpoint': '/browse', 'is_api_call': False},
    # 'video_list_ids': {'endpoint': '/preflight', 'is_api_call': True},
    # 'kids': {'endpoint': '/Kids', 'is_api_call': False}
}
"""List of all static endpoints for HTML/JSON POST/GET requests"""

def needs_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    # pylint: disable=protected-access, missing-docstring
    @wraps(func)
    def ensure_login(*args, **kwargs):
        session = args[0]
        if not session._is_logged_in():
            session._login()
        return func(*args, **kwargs)
    return ensure_login

class LoginFailedError(Exception):
    """The login attempt has failed"""
    pass

class NetflixSession(object):
    """Stateful netflix session management"""

    slots = None
    """Slots to be registered with AddonSignals. Is set in _register_slots"""

    session = None
    """The requests.session object to handle communication to Netflix"""

    session_data = None
    """The session data extracted from the Netflix webpage.
    Contains profiles, user_data, esn and api_data"""

    verify_ssl = bool(common.ADDON.getSettingBool('ssl_verification'))
    """Use SSL verification when performing requests"""

    def __init__(self):
        self._register_slots()
        self._init_session()
        self._prefetch_login()

    def __del__(self):
        """Unregister AddonSignals slots"""
        for slot in self.slots:
            common.unregister_slot(slot)

    @property
    def credentials(self):
        """
        The stored credentials.
        Will ask for credentials if there are none in store
        """
        try:
            return common.get_credentials()
        except common.MissingCredentialsError:
            return common.ask_credentials()

    @property
    def account_hash(self):
        """The unique hash of the current account"""
        return urlsafe_b64encode(self.credentials.get('email', 'NoMail'))

    @property
    def auth_url(self):
        """Valid authURL. Raises InvalidAuthURLError if it isn't known."""
        try:
            return self.session_data['user_data']['authURL']
        except (AttributeError, KeyError) as exc:
            raise website.InvalidAuthURLError(exc)

    def _register_slots(self):
        self.slots = [
            self.logout,
            self.list_profiles,
            self.activate_profile,
            self.path_request,
            self.get,
            self.post
        ]
        for slot in self.slots:
            common.register_slot(slot)

    def _init_session(self):
        """Initialize the session to use for all future connections"""
        try:
            self.session.close()
            common.info('Session closed')
        except AttributeError:
            pass
        self.session_data = {}
        self.session = requests.session()
        self.session.headers.update({
            'User-Agent': common.get_user_agent(),
            'Accept-Encoding': 'gzip'
        })
        common.info('Initialized new session')

    def _prefetch_login(self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it"""
        try:
            common.get_credentials()
            if not self._is_logged_in():
                self._login()
        except common.MissingCredentialsError:
            common.info(
                'Skipping login prefetch. No stored credentials are available')

    def _is_logged_in(self):
        """Check if the user is logged in"""
        # pylint: disable=broad-except
        if not self.session.cookies:
            common.debug('Active session has no cookies, trying to restore...')
            try:
                self.session.cookies = cookies.load(self.account_hash)
            except cookies.MissingCookiesError:
                common.info('No stored cookies available')
                return False
            except cookies.CookiesExpiredError:
                pass
            try:
                # If we can get session data, cookies are still valid
                self.session_data = website.extract_session_data(
                    self._get('profiles'))
                self._update_esn()
            except Exception:
                common.info('Stored cookies are expired')
                return False
        return True

    def _login(self):
        """Perform account login"""
        try:
            common.debug('Extracting authURL...')
            auth_url = website.extract_userdata(
                self._get('profiles'))['authURL']
            common.debug('Logging in...')
            login_response = self._post(
                'login', _login_payload(self.credentials, auth_url))
            common.debug('Extracting session data...')
            session_data = website.extract_session_data(login_response)
        except Exception as exc:
            raise common.reraise(
                exc, 'Login failed', LoginFailedError, sys.exc_info()[2])

        common.info('Login successful')
        ui.show_notification('Netflix', 'Login successful')
        self.session_data = session_data
        cookies.save(self.account_hash, self.session.cookies)
        self._update_esn()

    def _update_esn(self):
        """Return True if the esn has changed on Session initialization"""
        if common.set_esn(self.session_data['esn']):
            common.send_signal(
                signal=common.Signals.ESN_CHANGED,
                data=self.session_data['esn'])

    @common.addonsignals_return_call
    def logout(self):
        """Logout of the current account and reset the session"""
        common.debug('Logging out of current account')
        self._get('logout')
        cookies.delete(self.account_hash)
        self._init_session()

    @common.addonsignals_return_call
    @needs_login
    def list_profiles(self):
        """Retrieve a list of all profiles in the user's account"""
        try:
            return self.session_data['profiles']
        except (AttributeError, KeyError) as exc:
            raise website.InvalidProfilesError(exc)

    @common.addonsignals_return_call
    @needs_login
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.debug('Activating profile {}'.format(guid))
        self._get(
            component='activate_profile',
            req_type='api',
            params={
                'switchProfileGuid': guid,
                '_': int(time()),
                'authURL': self.auth_url})
        self.session_data['user_data']['guid'] = guid
        common.debug('Successfully activated profile {}'.format(guid))

    @common.addonsignals_return_call
    @needs_login
    def path_request(self, paths):
        """Perform a path request against the Shakti API"""
        common.debug('Executing path request: {}'.format(paths))
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/javascript, */*',}
        params = {
            'model': self.session_data['user_data']['gpsModel']}
        data = json.dumps({
            'paths': paths,
            'authURL': self.auth_url})
        return self._post(
            component='shakti',
            req_type='api',
            params=params,
            headers=headers,
            data=data)['value']

    @common.addonsignals_return_call
    @needs_login
    def get(self, component, **kwargs):
        """Execute a GET request to the designated component's URL."""
        return self._get(component, **kwargs)

    @common.addonsignals_return_call
    @needs_login
    def post(self, component, data, **kwargs):
        """Execute a POST request to the designated component's URL."""
        return self._post(component, data, **kwargs)

    def _get(self, component, **kwargs):
        return self._request(
            method=self.session.get,
            component=component,
            **kwargs)

    def _post(self, component, data, **kwargs):
        return self._request(
            method=self.session.post,
            component=component,
            data=data,
            **kwargs)

    def _request(self, method, component, **kwargs):
        url = (_api_url(component, self.session_data['api_data'])
               if URLS[component]['is_api_call']
               else _document_url(component))
        common.debug(
            'Executing {verb} request to {url}'.format(
                verb='GET' if method == self.session.get else 'POST', url=url))
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=kwargs.get('headers'),
            params=kwargs.get('params'),
            data=kwargs.get('data'))
        common.debug(
            'Request returned statuscode {}'.format(response.status_code))
        response.raise_for_status()
        return (response.json()
                if URLS[component]['is_api_call']
                else response.content)

def _login_payload(credentials, auth_url):
    return {
        'userLoginId': credentials['email'],
        'email': credentials['email'],
        'password': credentials['password'],
        'rememberMe': 'true',
        'flow': 'websiteSignUp',
        'mode': 'login',
        'action': 'loginAction',
        'withFields': 'rememberMe,nextPage,userLoginId,password,email',
        'authURL': auth_url,
        'nextPage': '',
        'showPassword': ''
    }

def _document_url(component):
    return BASE_URL + URLS[component]['endpoint']

def _api_url(component, api_data):
    return '{apiroot}{baseurl}/{buildid}{componenturl}'.format(
        apiroot=api_data['API_ROOT'],
        baseurl=api_data['API_BASE_URL'],
        buildid=api_data['BUILD_IDENTIFIER'],
        componenturl=URLS[component]['endpoint'])
