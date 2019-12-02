# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Stateful Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time
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

from resources.lib.api.exceptions import (NotLoggedInError, LoginFailedError, LoginValidateError,
                                          APIError, MissingCredentialsError, WebsiteParsingError,
                                          InvalidMembershipStatusError, NotConnected)

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

BASE_URL = 'https://www.netflix.com'
"""str: Secure Netflix url"""

URLS = {
    'login': {'endpoint': '/login', 'is_api_call': False},
    'logout': {'endpoint': '/SignOut', 'is_api_call': False},
    'shakti': {'endpoint': '/pathEvaluator', 'is_api_call': True},
    'browse': {'endpoint': '/browse', 'is_api_call': False},
    'profiles': {'endpoint': '/profiles/manage', 'is_api_call': False},
    'activate_profile': {'endpoint': '/profiles/switch', 'is_api_call': True},
    'pin': {'endpoint': '/pin', 'is_api_call': False},
    'pin_reset': {'endpoint': '/pin/reset', 'is_api_call': True},
    'pin_service': {'endpoint': '/pin/service', 'is_api_call': True},
    'metadata': {'endpoint': '/metadata', 'is_api_call': True},
    'set_video_rating': {'endpoint': '/setVideoRating', 'is_api_call': True},  # Old rating system
    'set_thumb_rating': {'endpoint': '/setThumbRating', 'is_api_call': True},
    'update_my_list': {'endpoint': '/playlistop', 'is_api_call': True},
    # Don't know what these could be used for. Keeping for reference
    # 'video_list_ids': {'endpoint': '/preflight', 'is_api_call': True},
    # 'kids': {'endpoint': '/Kids', 'is_api_call': False}
}
# List of all static endpoints for HTML/JSON POST/GET requests
# How many entries of a list will be fetched with one path request

LOGIN_COOKIES = ['nfvdid', 'SecureNetflixId', 'NetflixId']


def needs_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    # pylint: disable=protected-access, missing-docstring
    @wraps(func)
    def ensure_login(*args, **kwargs):
        session = args[0]
        # I make sure that the connection is present..
        if not common.is_internet_connected():
            raise NotConnected('Internet connection not available')
        # ..this check verifies only if locally there are the data to correctly perform the login
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

    verify_ssl = True
    """Use SSL verification when performing requests"""

    def __init__(self):
        self.slots = [
            self.login,
            self.logout,
            self.update_profiles_data,
            self.activate_profile,
            self.parental_control_data,
            self.path_request,
            self.perpetual_path_request,
            self.perpetual_path_request_switch_profiles,
            self.get,
            self.post,
        ]
        for slot in self.slots:
            common.register_slot(slot)
        common.register_slot(play_callback, signal=g.ADDON_ID + '_play_action',
                             source_id='upnextprovider')
        self.verify_ssl = bool(g.ADDON.getSettingBool('ssl_verification'))
        self._init_session()
        self.is_prefetch_login = False
        self._prefetch_login()

    @property
    def account_hash(self):
        """The unique hash of the current account"""
        from base64 import urlsafe_b64encode
        return urlsafe_b64encode(
            common.get_credentials().get('email', 'NoMail').encode('utf-8')).decode('utf-8')

    def update_session_data(self, old_esn=None):
        old_esn = old_esn or g.get_esn()
        self.set_session_header_data()
        cookies.save(self.account_hash, self.session.cookies)
        _update_esn(old_esn)

    def set_session_header_data(self):
        self.session.headers.update(
            {'x-netflix.request.client.user.guid': g.LOCAL_DB.get_active_profile_guid()})

    @property
    def auth_url(self):
        """Return authentication url"""
        return g.LOCAL_DB.get_value('auth_url', table=TABLE_SESSION)

    @auth_url.setter
    def auth_url(self, value):
        g.LOCAL_DB.set_value('auth_url', value, TABLE_SESSION)

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

    @common.time_execution(immediate=True)
    def _verify_session_cookies(self):
        """Verify that the session cookies have not expired"""
        # pylint: disable=broad-except
        fallback_to_validate = False
        if not self.session.cookies:
            return False
        for cookie_name in LOGIN_COOKIES:
            if cookie_name not in list(self.session.cookies.keys()):
                common.error(
                    'The cookie "{}" do not exist. It is not possible to check expiration. '
                    'Fallback to old validate method.',
                    cookie_name)
                fallback_to_validate = True
                break
            for cookie in list(self.session.cookies):
                if cookie.name != cookie_name:
                    continue
                if cookie.expires <= int(time.time()):
                    common.info('Login is expired')
                    return False
        if fallback_to_validate:
            # Old method, makes a request at every time an user change page on Kodi
            # and try to re-extract all, working but slows down navigation.
            # If we can get session data, cookies are still valid
            try:
                website.validate_session_data(self._get('profiles'))
                self.update_session_data()
            except Exception:
                import traceback
                common.warn('Failed to validate session data, login is expired')
                common.debug(traceback.format_exc())
                self.session.cookies.clear()
                return False
        return True

    def _verify_esn_existence(self):
        # if for any reason esn is no longer exist get one
        if not g.get_esn():
            return self._refresh_session_data()
        return True

    @common.time_execution(immediate=True)
    def _refresh_session_data(self, raise_exception=False):
        """Refresh session_data from the Netflix website"""
        # pylint: disable=broad-except
        try:
            website.extract_session_data(self._get('profiles'))
            self.update_session_data()
        except InvalidMembershipStatusError:
            raise
        except WebsiteParsingError:
            # it is possible that cookies may not work anymore,
            # it should be due to updates in the website,
            # this can happen when opening the addon while executing update_profiles_data
            import traceback
            common.warn('Failed to refresh session data, login expired (WebsiteParsingError)')
            common.debug(traceback.format_exc())
            self.session.cookies.clear()
            return self._login()
        except requests.exceptions.RequestException:
            import traceback
            common.warn('Failed to refresh session data, request error (RequestException)')
            common.warn(traceback.format_exc())
            if raise_exception:
                raise
            return False
        except Exception:
            import traceback
            common.warn('Failed to refresh session data, login expired (Exception)')
            common.debug(traceback.format_exc())
            self.session.cookies.clear()
            if raise_exception:
                raise
            return False
        common.debug('Successfully refreshed session data')
        return True

    @common.time_execution(immediate=True)
    def _load_cookies(self):
        """Load stored cookies from disk"""
        # pylint: disable=broad-except
        if not self.session.cookies:
            try:
                self.session.cookies = cookies.load(self.account_hash)
            except cookies.MissingCookiesError:
                return False
            except Exception as exc:
                import traceback
                common.error('Failed to load stored cookies: {}', type(exc).__name__)
                common.error(traceback.format_exc())
                return False
            common.info('Successfully loaded stored cookies')
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
            except LoginValidateError as exc:
                self.session.cookies.clear()
                common.purge_credentials()
                if modal_error_message:
                    ui.show_ok_dialog(common.get_local_string(30008), unicode(exc))
                    return False
                raise
            website.extract_session_data(login_response)
        except InvalidMembershipStatusError:
            ui.show_error_info(common.get_local_string(30008),
                               common.get_local_string(30180),
                               False, True)
            return False
        except Exception:  # pylint: disable=broad-except
            import traceback
            common.error(traceback.format_exc())
            self.session.cookies.clear()
            raise
        common.info('Login successful')
        ui.show_notification(common.get_local_string(30109))
        self.update_session_data(current_esn)
        return True

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
        pin_response = self._get('pin', data={'password': password})
        from re import findall
        html_ml_points = findall(r'<div class="maturity-input-item\s.*?<\/div>',
                                 pin_response.decode('utf-8'))
        maturity_levels = []
        maturity_names = []
        current_level = -1
        for ml_point in html_ml_points:
            is_included = bool(findall(r'class="maturity-input-item[^"<>]*?included', ml_point))
            value = findall(r'value="(\d+)"', ml_point)
            name = findall(r'<span class="maturity-name">([^"]+?)<\/span>', ml_point)
            rating = findall(r'<li[^<>]+class="pin-rating-item">([^"]+?)<\/li>', ml_point)
            if not value:
                raise WebsiteParsingError('Unable to find maturity level value: {}'.format(ml_point))
            if name:
                maturity_names.append({
                    'name': name[0],
                    'rating': '[CR][' + rating[0] + ']' if rating else ''
                })
            maturity_levels.append({
                'level': len(maturity_levels),
                'value': value[0],
                'is_included': is_included
            })
            if is_included:
                current_level += 1
        if not html_ml_points:
            raise WebsiteParsingError('Unable to find html maturity level points')
        if not maturity_levels:
            raise WebsiteParsingError('Unable to find maturity levels')
        if not maturity_names:
            raise WebsiteParsingError('Unable to find maturity names')
        common.debug('Parsed maturity levels: {}', maturity_levels)
        common.debug('Parsed maturity names: {}', maturity_names)
        return {'pin': pin, 'maturity_levels': maturity_levels, 'maturity_names': maturity_names,
                'current_level': current_level}

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
        xbmc.executebuiltin('XBMC.Container.Update(path,replace)')  # Clean path history
        xbmc.executebuiltin('Container.Update({})'.format(url))  # Open root page

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def update_profiles_data(self):
        return self._refresh_session_data(raise_exception=True)

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def activate_profile(self, guid):
        """Set the profile identified by guid as active"""
        common.info('Activating profile {}', guid)
        if guid == g.LOCAL_DB.get_active_profile_guid():
            common.debug('Profile {} is already active', guid)
            return False
        self._get(component='activate_profile',
                  req_type='api',
                  params={'switchProfileGuid': guid,
                          '_': int(time.time()),
                          'authURL': self.auth_url})
        # When switch profile is performed the authURL change
        react_context = website.extract_json(self._get('browse'), 'reactContext')
        self.auth_url = website.extract_api_data(react_context)['auth_url']
        g.LOCAL_DB.switch_active_profile(guid)
        self.update_session_data()
        common.debug('Successfully activated profile {}', guid)
        return True

    @common.addonsignals_return_call
    @needs_login
    def path_request(self, paths):
        """Perform a path request against the Shakti API"""
        return self._path_request(paths)

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def perpetual_path_request(self, paths, length_params, perpetual_range_start=None,
                               no_limit_req=False):
        return self._perpetual_path_request(paths, length_params, perpetual_range_start,
                                            no_limit_req)

    @common.addonsignals_return_call
    @needs_login
    @common.time_execution(immediate=True)
    def perpetual_path_request_switch_profiles(self, paths, length_params,
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
        is_profile_switched = self.activate_profile(mylist_profile_guid)
        # Get the My List data
        path_response = self._perpetual_path_request(paths, length_params, perpetual_range_start,
                                                     no_limit_req)
        if is_profile_switched:
            # Reactive again the previous profile
            self.activate_profile(current_profile_guid)
        return path_response

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
                common.debug('{} has other elements, added _perpetual_range_selector item',
                             response_type)
            else:
                range_end = range_start + request_size

        if perpetual_range_start > 0:
            previous_start = perpetual_range_start - (response_size * number_of_requests)
            if '_perpetual_range_selector' in merged_response:
                merged_response['_perpetual_range_selector']['previous_start'] = previous_start
            else:
                merged_response['_perpetual_range_selector'] = {
                    'previous_start': previous_start}
        return merged_response

    @common.time_execution(immediate=True)
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
            'materialize': 'false'
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
        common.debug('Executing {verb} request to {url}',
                     verb='GET' if method == self.session.get else 'POST', url=url)
        data, headers, params = self._prepare_request_properties(component,
                                                                 kwargs)
        start = time.clock()
        response = method(
            url=url,
            verify=self.verify_ssl,
            headers=headers,
            params=params,
            data=data)
        common.debug('Request took {}s', time.clock() - start)
        common.debug('Request returned statuscode {}', response.status_code)
        if response.status_code == 404 and not session_refreshed:
            # It may happen that netflix updates the build_identifier version
            # when you are watching a video or browsing the menu,
            # this causes the api address to change, and return 'url not found' error
            # So let's try updating the session data (just once)
            common.warn('Try refresh session data to update build_identifier version')
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
        if component in ['set_video_rating', 'set_thumb_rating', 'update_my_list', 'pin_service']:
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


def _document_url(component):
    return BASE_URL + URLS[component]['endpoint']


def _api_url(component):
    return '{baseurl}{componenturl}'.format(
        baseurl=g.LOCAL_DB.get_value('api_endpoint_url', table=TABLE_SESSION),
        componenturl=URLS[component]['endpoint'])


def _update_esn(old_esn):
    """Perform key handshake if the esn has changed on Session initialization"""
    current_esn = g.get_esn()
    if old_esn != current_esn:
        common.send_signal(signal=common.Signals.ESN_CHANGED, data=current_esn)


def _raise_api_error(decoded_response):
    if decoded_response.get('status', 'success') == 'error':
        raise APIError(decoded_response.get('message'))
    return decoded_response


def play_callback(data):
    """Callback function used for upnext integration"""
    common.info('Received signal from Up Next. Playing next episode...')
    common.stop_playback()
    common.play_media(data['play_path'])
