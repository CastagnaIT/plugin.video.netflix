# -*- coding: utf-8 -*-
"""Stateful Netflix session management"""
from __future__ import unicode_literals

import traceback
from time import time
from base64 import urlsafe_b64encode
from functools import wraps
import json
import requests

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.website as website
import resources.lib.api.paths as apipaths
import resources.lib.services.cookies as cookies
import resources.lib.kodi.ui as ui

BASE_URL = 'https://www.netflix.com'
"""str: Secure Netflix url"""

URLS = {
    'login': {'endpoint': '/login', 'is_api_call': False},
    'shakti': {'endpoint': '/pathEvaluator', 'is_api_call': True},
    'browse': {'endpoint': '/browse', 'is_api_call': False},
    'profiles':  {'endpoint': '/profiles/manage', 'is_api_call': False},
    'activate_profile': {'endpoint': '/profiles/switch', 'is_api_call': True},
    'adult_pin': {'endpoint': '/pin/service', 'is_api_call': True},
    'metadata': {'endpoint': '/metadata', 'is_api_call': True},
    'set_video_rating': {'endpoint': '/setVideoRating', 'is_api_call': True},
    'update_my_list': {'endpoint': '/playlistop', 'is_api_call': True},
    # Don't know what these could be used for. Keeping for reference
    # 'video_list_ids': {'endpoint': '/preflight', 'is_api_call': True},
    # 'kids': {'endpoint': '/Kids', 'is_api_call': False}
}
"""List of all static endpoints for HTML/JSON POST/GET requests"""

MAX_PATH_REQUEST_SIZE = 40
"""How many entries of a list will be fetched with one path request"""


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

    verify_ssl = bool(g.ADDON.getSettingBool('ssl_verification'))
    """Use SSL verification when performing requests"""

    def __init__(self):
        self._session_data = None
        self.slots = [
            self.login,
            self.logout,
            self.list_profiles,
            self.activate_profile,
            self.path_request,
            self.perpetual_path_request,
            self.get,
            self.post
        ]
        for slot in self.slots:
            common.register_slot(slot)
        self._init_session()
        self._prefetch_login()

    @property
    def credentials(self):
        """
        The stored credentials.
        Will ask for credentials if there are none in store
        """
        try:
            return common.get_credentials()
        except common.MissingCredentialsError:
            return ui.ask_credentials()

    @property
    def account_hash(self):
        """The unique hash of the current account"""
        return urlsafe_b64encode(self.credentials.get('email', 'NoMail'))

    @property
    def session_data(self):
        """The session data extracted from the Netflix webpage.
        Contains profiles, active_profile, root_lolomo, user_data, esn
        and api_data"""
        return self._session_data

    @session_data.setter
    def session_data(self, new_session_data):
        self._session_data = new_session_data
        self.session.headers.update(
            {'x-netflix.request.client.user.guid':
                 new_session_data['active_profile']})
        cookies.save(self.account_hash, self.session.cookies)
        _update_esn(self.session_data['esn'])
        common.debug('Set session data: {}'.format(self._session_data))

    @property
    def auth_url(self):
        """Valid authURL. Raises InvalidAuthURLError if it isn't known."""
        try:
            return self.session_data['user_data']['authURL']
        except (AttributeError, KeyError) as exc:
            raise website.InvalidAuthURLError(exc)

    def _init_session(self):
        """Initialize the session to use for all future connections"""
        try:
            self.session.close()
            common.info('Session closed')
        except AttributeError:
            pass
        # Do not use property setter for session_data because self.session may
        # be None at this point
        self._session_data = {}
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
            common.info('Login prefetch: No stored credentials are available')

    def _is_logged_in(self):
        """Check if the user is logged in"""
        if not self.session.cookies:
            common.debug('Active session has no cookies, trying to restore...')
            return self._load_cookies() and self._refresh_session_data()
        return True

    def _refresh_session_data(self):
        """Refresh session_data from the Netflix website"""
        # pylint: disable=broad-except
        try:
            # If we can get session data, cookies are still valid
            self.session_data = website.extract_session_data(
                self._get('browse'))
        except Exception:
            common.debug(traceback.format_exc())
            common.info('Failed to refresh session data, login expired')
            return False
        common.debug('Successfully refreshed session data')
        return True

    def _load_cookies(self):
        """Load stored cookies from disk"""
        try:
            self.session.cookies = cookies.load(self.account_hash)
        except cookies.MissingCookiesError:
            common.info('No stored cookies available')
            return False
        except cookies.CookiesExpiredError:
            # Ignore this for now, because login is sometimes valid anyway
            pass
        return True

    @common.addonsignals_return_call
    def login(self):
        """AddonSignals interface for login function"""
        self._login()

    def _login(self):
        """Perform account login"""
        try:
            auth_url = website.extract_userdata(
                self._get('browse'))['authURL']
            common.debug('Logging in...')
            login_response = self._post(
                'login', data=_login_payload(self.credentials, auth_url))
            session_data = website.extract_session_data(login_response)
        except Exception:
            common.error(traceback.format_exc())
            raise LoginFailedError

        common.info('Login successful')
        ui.show_notification(common.get_local_string(30109))
        self.session_data = session_data

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
        if guid == self.session_data['active_profile']:
            common.debug('Profile {} is already active'.format(guid))
            return False
        self._get(
            component='activate_profile',
            req_type='api',
            params={
                'switchProfileGuid': guid,
                '_': int(time()),
                'authURL': self.auth_url})
        self._refresh_session_data()
        common.debug('Successfully activated profile {}'.format(guid))
        return True

    @common.addonsignals_return_call
    @needs_login
    def path_request(self, paths):
        """Perform a path request against the Shakti API"""
        return self._path_request(
            _inject_root_lolomo(paths, self.session_data['root_lolomo']))

    @common.addonsignals_return_call
    @needs_login
    def perpetual_path_request(self, paths, path_type, length_params=None):
        """Perform a perpetual path request against the Shakti API to retrieve
        a possibly large video list. If the requested video list's size is
        larger than MAX_PATH_REQUEST_SIZE, multiple path requests will be
        executed with forward shifting range selectors and the results will
        be combined into one path response."""
        length_params = length_params or []
        length = apipaths.LENGTH_ATTRIBUTES[path_type]
        range_start = 0
        range_end = MAX_PATH_REQUEST_SIZE
        merged_response = {}
        while range_start < range_end:
            path_response = self._path_request(
                _set_range_selector(paths, range_start, range_end))
            common.merge_dicts(path_response, merged_response)
            range_start = range_end + 1
            if length(path_response, *length_params) > range_end:
                common.debug('{} has more items, doing another path request'
                             .format(path_type))
                range_end += MAX_PATH_REQUEST_SIZE
        return merged_response

    def _path_request(self, paths):
        """Execute a path request with static paths"""
        common.debug('Executing path request: {}'.format(json.dumps(paths)))
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/javascript, */*'}
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
    def post(self, component, **kwargs):
        """Execute a POST request to the designated component's URL."""
        result = self._post(component, **kwargs)
        common.debug(result)
        return result

    def _get(self, component, **kwargs):
        return self._request(
            method=self.session.get,
            component=component,
            **kwargs)

    def _post(self, component, **kwargs):
        return self._request(
            method=self.session.post,
            component=component,
            **kwargs)

    def _request(self, method, component, **kwargs):
        url = (_api_url(component, self.session_data['api_data'])
               if URLS[component]['is_api_call']
               else _document_url(component))
        common.debug(
            'Executing {verb} request to {url}'.format(
                verb='GET' if method == self.session.get else 'POST', url=url))
        start = time()

        data = kwargs.get('data', {})
        headers = kwargs.get('headers', {})
        if component in ['set_video_rating', 'update_my_list', 'adult_pin']:
            headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/javascript, */*'})
            data['authURL'] = self.auth_url
            data = json.dumps(data)

        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=kwargs.get('params'),
            data=data)
        common.debug('Request took {}s'.format(time() - start))
        common.debug(
            'Request returned statuscode {}'.format(response.status_code))
        response.raise_for_status()
        return (response.json()
                if URLS[component]['is_api_call']
                else response.content)


def _inject_root_lolomo(paths, root_lolomo):
    """Apply special handling for path requests that query the root lists
    (displayed on homepage): If first pathitem == 'root_lolomo' (will be
    supplied by shakti api client), we prepend ['lolomos', root_lolomo] to
    all paths, where root_lolomo is the ID of the root LoLoMo as extracted
    from falkorCache.
    If the first pathitem is not the 'root_lolomo' indicator, we just return
    the untouched paths"""
    if paths[0] != 'root_lolomo':
        return paths
    return [['lolomos', root_lolomo] + path
            for path in paths[1:]]


def _set_range_selector(paths, range_start, range_end):
    """Replace the RANGE_SELECTOR placeholder with an actual dict:
    {'from': range_start, 'to': range_end}"""
    import copy
    # Make a deepcopy because we don't want to lose the original paths
    # with the placeholder
    ranged_paths = copy.deepcopy(paths)
    for path in ranged_paths:
        for i in range(0, len(path) - 1):
            if path[i] == apipaths.RANGE_SELECTOR:
                path[i] = {'from': range_start, 'to': range_end}
    return ranged_paths


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


def _update_esn(esn):
    """Return True if the esn has changed on Session initialization"""
    if g.set_esn(esn):
        common.send_signal(signal=common.Signals.ESN_CHANGED, data=esn)
