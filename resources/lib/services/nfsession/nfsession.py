# -*- coding: utf-8 -*-
"""Stateful Netflix session management"""
from __future__ import unicode_literals

import traceback
import time
from base64 import urlsafe_b64encode
from functools import wraps
import json
import requests

import xbmc

from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.common.cookies as cookies
import resources.lib.api.website as website
import resources.lib.api.paths as apipaths
import resources.lib.kodi.ui as ui

from resources.lib.api.exceptions import (NotLoggedInError, LoginFailedError,
                                          APIError, MissingCredentialsError)

BASE_URL = 'https://www.netflix.com'
"""str: Secure Netflix url"""

URLS = {
    'login': {'endpoint': '/login', 'is_api_call': False},
    'logout': {'endpoint': '/SignOut', 'is_api_call': False},
    'shakti': {'endpoint': '/pathEvaluator', 'is_api_call': True},
    'browse': {'endpoint': '/browse', 'is_api_call': False},
    'profiles': {'endpoint': '/profiles/manage', 'is_api_call': False},
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
            raise NotLoggedInError
        return func(*args, **kwargs)
    return ensure_login


class NetflixSession(object):
    """Stateful netflix session management"""

    slots = None
    """Slots to be registered with AddonSignals. Is set in _register_slots"""

    session = None
    """The requests.session object to handle communication to Netflix"""

    verify_ssl = bool(g.ADDON.getSettingBool('ssl_verification'))
    """Use SSL verification when performing requests"""

    def __init__(self):
        self.slots = [
            self.login,
            self.logout,
            self.activate_profile,
            self.path_request,
            self.perpetual_path_request,
            self.get,
            self.post,
        ]
        for slot in self.slots:
            common.register_slot(slot)
        common.register_slot(play_callback, signal=g.ADDON_ID + '_play_action',
                             source_id='upnextprovider')
        self._init_session()
        self._prefetch_login()

    @property
    def account_hash(self):
        """The unique hash of the current account"""
        return urlsafe_b64encode(
            common.get_credentials().get('email', 'NoMail'))

    def update_session_data(self):
        self.session.headers.update(
            {'x-netflix.request.client.user.guid': g.LOCAL_DB.get_active_profile_guid()})
        cookies.save(self.account_hash, self.session.cookies)
        _update_esn(g.LOCAL_DB.get_value('esn', table=TABLE_SESSION))

    @property
    def auth_url(self):
        """Return authentication url"""
        return g.LOCAL_DB.get_value('auth_url', table=TABLE_SESSION)

    @common.time_execution(immediate=True)
    def _init_session(self):
        """Initialize the session to use for all future connections"""
        try:
            self.session.close()
            common.info('Session closed')
        except AttributeError:
            pass
        self.session = requests.session()
        self.session.headers.update({
            'User-Agent': common.get_user_agent(),
            'Accept-Encoding': 'gzip'
        })
        common.info('Initialized new session')

    @common.time_execution(immediate=True)
    def _prefetch_login(self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it"""
        try:
            common.get_credentials()
            if not self._is_logged_in():
                self._login()
        except MissingCredentialsError:
            common.info('Login prefetch: No stored credentials are available')
        except LoginFailedError:
            ui.show_notification(common.get_local_string(30009))

    @common.time_execution(immediate=True)
    def _is_logged_in(self):
        """Check if the user is logged in and if so refresh session data"""
        return (self.session.cookies or
                (self._load_cookies() and self._refresh_session_data()))

    @common.time_execution(immediate=True)
    def _refresh_session_data(self):
        """Refresh session_data from the Netflix website"""
        # pylint: disable=broad-except
        try:
            # If we can get session data, cookies are still valid
            website.extract_session_data(self._get('profiles'))
            self.update_session_data()
        except Exception:
            common.debug(traceback.format_exc())
            common.info('Failed to refresh session data, login expired')
            self.session.cookies.clear()
            return False
        common.debug('Successfully refreshed session data')
        return True

    @common.time_execution(immediate=True)
    def _load_cookies(self):
        """Load stored cookies from disk"""
        # pylint: disable=broad-except
        try:
            self.session.cookies = cookies.load(self.account_hash)
        except Exception as exc:
            common.debug(
                'Failed to load stored cookies: {}'.format(type(exc).__name__))
            common.debug(traceback.format_exc())
            return False
        common.debug('Successfully loaded stored cookies')
        return True

    @common.addonsignals_return_call
    def login(self):
        """AddonSignals interface for login function"""
        self._login()

    @common.time_execution(immediate=True)
    def _login(self):
        """Perform account login"""
        try:
            # First we get the authentication url without logging in, required for login API call
            react_context = website.extract_json(self._get('profiles'), 'reactContext')
            auth_url = website.extract_api_data(react_context)['auth_url']
            common.debug('Logging in...')
            login_response = self._post(
                'login',
                data=_login_payload(common.get_credentials(), auth_url))
            website.extract_session_data(login_response)
        except Exception:
            common.debug(traceback.format_exc())
            self.session.cookies.clear()
            raise LoginFailedError

        common.info('Login successful')
        ui.show_notification(common.get_local_string(30109))
        self.update_session_data()

    @common.addonsignals_return_call
    @common.time_execution(immediate=True)
    def logout(self):
        """Logout of the current account and reset the session"""
        common.debug('Logging out of current account')
        cookies.delete(self.account_hash)
        self._get('logout')
        common.purge_credentials()
        common.info('Logout successful')
        ui.show_notification(common.get_local_string(30113))
        self._init_session()
        xbmc.executebuiltin('XBMC.Container.Update(path,replace)')  # Clean path history
        xbmc.executebuiltin('XBMC.ActivateWindow(Home)')

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.debug('Activating profile {}'.format(guid))
        if guid == g.LOCAL_DB.get_active_profile_guid():
            common.debug('Profile {} is already active'.format(guid))
            return False
        self._get(
            component='activate_profile',
            req_type='api',
            params={
                'switchProfileGuid': guid,
                '_': int(time.time()),
                'authURL': self.auth_url})
        g.LOCAL_DB.switch_active_profile(guid)
        self.update_session_data()
        # self._refresh_session_data()
        common.debug('Successfully activated profile {}'.format(guid))
        return True

    @common.addonsignals_return_call
    @needs_login
    def path_request(self, paths):
        """Perform a path request against the Shakti API"""
        return self._path_request(paths)

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def perpetual_path_request(self, paths, length_params, perpetual_range_start=None):
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
        # Note: when the request is made with 'genres' context,
        # the response strangely does not respect the number of objects
        # requested, returning 1 more item, i couldn't understand why
        if context_name == 'genres':
            response_size += 1

        number_of_requests = 2
        perpetual_range_start = int(perpetual_range_start) if perpetual_range_start else 0
        range_start = perpetual_range_start
        range_end = range_start + request_size
        merged_response = {}

        for n_req in range(number_of_requests):
            path_response = self._path_request(_set_range_selector(paths, range_start, range_end))
            if len(path_response) == 0:
                break
            if not common.check_path_exists(length_args, path_response):
                # It may happen that the number of items to be received
                # is equal to the number of the response_size
                # so a second round will be performed, which will return an empty list
                break
            common.merge_dicts(path_response, merged_response)
            response_count = response_length(path_response, *length_args)
            if response_count >= response_size:
                range_start += response_size
                if n_req == (number_of_requests - 1):
                    merged_response['_perpetual_range_selector'] = {'next_start': range_start}
                    common.debug('{} has other elements, added _perpetual_range_selector item'
                                 .format(response_type))
                else:
                    range_end = range_start + request_size
            else:
                # There are no other elements to request
                break

        if perpetual_range_start > 0:
            previous_start = perpetual_range_start - (response_size * number_of_requests)
            if '_perpetual_range_selector' in merged_response:
                merged_response['_perpetual_range_selector']['previous_start'] = previous_start
            else:
                merged_response['_perpetual_range_selector'] = {'previous_start': previous_start}
        return merged_response

    @common.time_execution(immediate=True)
    def _path_request(self, paths):
        """Execute a path request with static paths"""
        common.debug('Executing path request: {}'.format(json.dumps(paths, ensure_ascii=False)))
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/javascript, */*'}

        '''
        params:
        drmSystem       drm used
        falcor_server   json responses like browser
        withSize        puts the 'size' field inside each dictionary
        materialize     if true, when a path that no longer exists is requested (like 'storyarts'),
                           it is still added in an 'empty' form in the response
        '''
        params = {
            'drmSystem': 'widevine',
            # 'falcor_server': '0.1.0',
            'withSize': 'false',
            'materialize': 'false'
        }
        data = 'path=' + '&path='.join(json.dumps(path, ensure_ascii=False) for path in paths)
        data += '&authURL=' + self.auth_url
        return self._post(
            component='shakti',
            req_type='api',
            params=params,
            headers=headers,
            data=data.encode('utf-8'))['value']

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
        url = (_api_url(component)
               if URLS[component]['is_api_call']
               else _document_url(component))
        common.debug(
            'Executing {verb} request to {url}'.format(
                verb='GET' if method == self.session.get else 'POST', url=url))
        data, headers, params = self._prepare_request_properties(component,
                                                                 kwargs)
        start = time.clock()
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=params,
            data=data)
        common.debug('Request took {}s'.format(time.clock() - start))
        common.debug('Request returned statuscode {}'
                     .format(response.status_code))
        if response.status_code == 404 and not session_refreshed:
            # It may happen that netflix updates the build_identifier version
            # when you are watching a video or browsing the menu,
            # this causes the api address to change, and return 'url not found' error
            # So let's try updating the session data (just once)
            common.debug('Try refresh session data to update build_identifier version')
            if self._refresh_session_data():
                return self._request(method, component, True, **kwargs)
        response.raise_for_status()
        return (_raise_api_error(response.json() if response.content else {})
                if URLS[component]['is_api_call']
                else response.content)

    def _prepare_request_properties(self, component, kwargs):
        data = kwargs.get('data', {})
        headers = kwargs.get('headers', {})
        params = kwargs.get('params', {})
        if component in ['set_video_rating', 'update_my_list', 'adult_pin']:
            headers.update({
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/javascript, */*'})
            data['authURL'] = self.auth_url
            data = json.dumps(data)
        return data, headers, params


@common.time_execution(immediate=True)
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


def _api_url(component):
    return '{baseurl}{componenturl}'.format(
        baseurl=g.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        componenturl=URLS[component]['endpoint'])


def _update_esn(esn):
    """Return True if the esn has changed on Session initialization"""
    if _set_esn(esn):
        common.send_signal(signal=common.Signals.ESN_CHANGED, data=esn)


def _set_esn(esn):
    """
    Set the ESN in settings if it hasn't been set yet.
    Return True if the new ESN has been set, False otherwise
    """
    if not g.LOCAL_DB.get_value('esn', table=TABLE_SESSION) and esn:
        g.LOCAL_DB.set_value('esn', esn, table=TABLE_SESSION)
        return True
    return False


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response


def play_callback(data):
    """Callback function used for upnext integration"""
    common.debug('Received signal from Up Next. Playing next episode...')
    common.stop_playback()
    common.play_media(data['play_path'])
