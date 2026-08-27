# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Handle the authentication access

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import re
from urllib.parse import quote

import resources.lib.utils.website as website
import resources.lib.common as common
import resources.lib.utils.cookies as cookies
import resources.lib.kodi.ui as ui
import resources.lib.services.nfsession.session.endpoints as ep
from resources.lib.common.exceptions import (LoginValidateError, NotConnected, NotLoggedInError,
                                             MbrStatusNeverMemberError, MbrStatusFormerMemberError, LoginError,
                                             MissingCredentialsError, MbrStatusAnonymousError, WebsiteParsingError)
from resources.lib.database import db_utils
from resources.lib.globals import G
from resources.lib.services.nfsession.session.cookie import SessionCookie
from resources.lib.services.nfsession.session.http_requests import SessionHTTPRequests
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

CLCS_GRAPHQL_URL = ep.BASE_URL + '/graphql'
CLCS_SCREEN_UPDATE_ID = '0ed5cd22-de4e-4883-bf7a-ed255ab88664'
CLCS_QUERY_VERSION = 102
# Time waited by the website for the reCAPTCHA script before submitting the sign in with the error
RECAPTCHA_TIMEOUT_MS = 2730

# The website serves the CLCS login flow only to recent browsers,
# with an outdated user agent it falls back to a static form protected by reCAPTCHA
BROWSER_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0'
BROWSER_HEADERS = {
    'User-Agent': BROWSER_USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Sec-GPC': '1'
}


# Cipher list used by Firefox, the default one of python is recognizable as a non browser client
FIREFOX_CIPHERS = (
    'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:'
    'ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:'
    'ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:'
    'ECDHE-ECDSA-AES256-SHA:ECDHE-ECDSA-AES128-SHA:'
    'ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:'
    'AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA'
)


def _mount_browser_tls(session):
    """Use the TLS settings of a browser for the login requests"""
    try:
        import ssl
        from requests.adapters import HTTPAdapter
        from urllib3.poolmanager import PoolManager

        class _BrowserTLSAdapter(HTTPAdapter):
            def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
                context = ssl.create_default_context()
                context.set_ciphers(FIREFOX_CIPHERS)
                context.options |= getattr(ssl, 'OP_NO_COMPRESSION', 0)
                pool_kwargs['ssl_context'] = context
                self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize,
                                               block=block, **pool_kwargs)

        session.mount('https://www.netflix.com', _BrowserTLSAdapter())
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warn('Cannot set the browser TLS settings ({})', exc)


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
            LOG.debug(traceback.format_exc())
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
        return self._load_cookies() and self._verify_session_cookies()

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
        from http.cookiejar import Cookie
        for cookie in data['cookies']:
            # The code below has been adapted from httpx.Cookies.set() method
            kwargs = {
                'version': 0,
                'name': cookie['name'],
                'value': cookie['value'],
                'port': None,
                'port_specified': False,
                'domain': cookie['domain'],
                'domain_specified': bool(cookie['domain']),
                'domain_initial_dot': cookie['domain'].startswith('.'),
                'path': cookie['path'],
                'path_specified': bool(cookie['path']),
                'secure': cookie['secure'],
                'expires': cookie['expires'],
                'discard': True,
                'comment': None,
                'comment_url': None,
                'rest': cookie['rest'],
                'rfc2109': False,
            }
            cookie = Cookie(**kwargs)
            self.session.cookies.set_cookie(cookie)
        cookies.log_cookie(self.session.cookies)
        # Try access to website
        try:
            website.extract_session_data(self.get('browse'), validate=True, update_profiles=True)
        except MbrStatusAnonymousError:
            # Access not valid
            LOG.warn('Login with AuthKey failed due to MbrStatusAnonymousError, '
                     'your account could be not confirmed / renewed / suspended.')
            return False
        except NotLoggedInError as exc:
            # Raised by get('browse') with httpx.RemoteProtocolError 'Server disconnected' exception
            # Cookies may be not more valid
            raise LoginError('The website has refused the connection, you need to generate a new Auth Key. '
                             'If you have just done "Sign out of all devices" from Netflix account settings '
                             'wait about 10 minutes before generating a new AuthKey.') from exc
        # Get the account e-mail
        page_response = self.get('account_security').decode('utf-8')
        email_match = re.search(r'>([^<]+@[^</]+)<', page_response)
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
                raise LoginError(common.get_local_string(12344)) from exc
            if exc.response.status_code not in (404, 410):
                raise
            # The legacy profilehub endpoint has been removed for some accounts.
            # The Auth Key cookies were already validated above, so allow login to
            # continue while retaining the supplied password for MSL compatibility.
            LOG.warn('Password verification endpoint is unavailable (HTTP {}); '
                     'continuing Auth Key login without password verification',
                     exc.response.status_code)
        common.set_credentials({'email': email, 'password': password})
        LOG.info('Login successful')
        ui.show_notification(common.get_local_string(30109))
        cookies.save(self.session.cookies)
        return True

    @measure_exec_time_decorator(is_immediate=True)
    def login(self, credentials=None):
        """Perform account login with credentials by driving the website CLCS login flow"""
        try:
            self.session.cookies.clear()
            credentials = credentials or common.get_credentials()
            LOG.debug('Logging in with credentials')
            _mount_browser_tls(self.session)
            page = self._get_login_page()
            server_state, server_screen_update, country, action_fields, app_version = _extract_clcs_bootstrap(page)
            # Send the same fields of the website, the password is not sent to let the website
            # choose the verification method for the account (e.g. the one-time code by e-mail)
            input_fields = [
                _clcs_field('userLoginId', 'stringValue', credentials['email']),
                _clcs_field('countryCode', 'stringValue', country['code']),
                _clcs_field('countryIsoCode', 'stringValue', country['iso'])
            ]
            input_fields += _clcs_recaptcha_fields(action_fields)
            self._clcs_app_version = app_version
            # The website submits the sign in after having waited the reCAPTCHA script,
            # send it with the same delay that is declared to the website
            import time
            time.sleep(RECAPTCHA_TIMEOUT_MS / 1000)
            result = self._clcs_screen_update(server_state, server_screen_update, input_fields)
            self._clcs_complete_login(result, credentials, country)

            website.extract_session_data(self.get('browse'), validate=True, update_profiles=True)
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
            raise LoginError(str(exc)) from exc
        except (MbrStatusNeverMemberError, MbrStatusFormerMemberError) as exc:
            self.session.cookies.clear()
            LOG.warn('Membership status {} not valid for login', exc)
            raise LoginError(common.get_local_string(30180)) from exc
        except Exception:  # pylint: disable=broad-except
            self.session.cookies.clear()
            import traceback
            LOG.error(traceback.format_exc())
            raise

    def _get_login_page(self):
        """Request the login page with modern browser headers, needed to get the CLCS login flow"""
        response = self.session.get(url=ep.BASE_URL + '/login', headers=BROWSER_HEADERS, timeout=8)
        response.raise_for_status()
        return response.text

    def _clcs_screen_update(self, server_state, server_screen_update, input_fields):
        """Send a single step of the CLCS login flow to the website GraphQL gateway"""
        payload = {
            'operationName': 'CLCSScreenUpdate',
            'variables': {
                'format': 'HTML',
                'imageFormat': 'PNG',
                'locale': 'en-US',
                'serverState': server_state,
                'serverScreenUpdate': server_screen_update,
                'inputFields': input_fields
            },
            'extensions': {'persistedQuery': {'id': CLCS_SCREEN_UPDATE_ID, 'version': CLCS_QUERY_VERSION}}
        }
        # Use separators with dumps because Netflix rejects spaces
        data = json.dumps(payload, separators=(',', ':'))
        response = self.session.post(
            url=CLCS_GRAPHQL_URL,
            data=data.encode('utf-8'),
            headers=_graphql_login_headers(server_state, getattr(self, '_clcs_app_version', '')),
            timeout=8)
        response.raise_for_status()
        decoded = response.json() if response.content else {}
        if decoded.get('errors'):
            raise LoginError(decoded['errors'][0].get('message', 'GraphQL error'))
        return decoded

    def _clcs_complete_login(self, result, credentials, country):
        """Walk the CLCS screens (password / one-time code) until the login succeeds"""
        password_submitted = False
        for _ in range(6):
            data = (result or {}).get('data', {}).get('result', {})
            typename = data.get('__typename')
            if typename == 'CLCSScreenUpdateEffect':
                if data.get('status') == 'SUCCESS':
                    return
                raise LoginError(_find_clcs_message(data) or common.get_local_string(30008))
            if typename != 'CLCSScreenUpdateTransition':
                raise LoginError(_find_clcs_message(data) or common.get_local_string(30008))
            screen = data.get('screen') or {}
            server_state = screen.get('serverState')
            action, kind = _select_clcs_action(screen)
            if not action:
                _log_clcs_screen_diagnostics(screen)
                raise LoginError(_find_clcs_message(screen) or common.get_local_string(30008))
            if kind == 'password':
                if password_submitted:
                    # The password screen is asked again, the credentials have been refused
                    _log_clcs_screen_diagnostics(screen)
                    raise LoginError(_find_clcs_message(screen) or common.get_local_string(30008))
                password_submitted = True
            input_fields = _build_clcs_fields(action['inputFieldRequirements'], credentials, kind, screen, country)
            result = self._clcs_screen_update(server_state, action['serverScreenUpdate'], input_fields)
        raise LoginError(common.get_local_string(30008))

    @measure_exec_time_decorator(is_immediate=True)
    def logout(self):
        """Logout of the current account and reset the session"""
        LOG.debug('Logging out of current account')
        with common.show_busy_dialog():
            # Perform the website logout
            self.get('logout')

            with G.SETTINGS_MONITOR.ignore_events(2):
                # Disable and reset auto-update / auto-sync features
                G.ADDON.setSettingInt('lib_auto_upd_mode', 1)
                G.ADDON.setSettingBool('lib_sync_mylist', False)
            G.SHARED_DB.delete_key('sync_mylist_profile_guid')

            # Disable and reset the profile guid of profile auto-selection
            G.LOCAL_DB.set_value('autoselect_profile_guid', '')

            # Disable and reset the selected profile guid for library playback
            G.LOCAL_DB.set_value('library_playback_profile_guid', '')

            G.LOCAL_DB.set_value('website_esn', '', db_utils.TABLE_SESSION)
            G.LOCAL_DB.set_value('esn', '' , db_utils.TABLE_SESSION)
            G.LOCAL_DB.set_value('esn_timestamp', '')

            G.LOCAL_DB.set_value('auth_url', '', db_utils.TABLE_SESSION)

            # Delete cookie and credentials
            self.session.cookies.clear()
            cookies.delete()
            common.purge_credentials()

            # Reinitialize the MSL handler (delete msl data file, then reset everything)
            self.msl_handler.reinitialize_msl_handler(delete_msl_file=True)

            G.CACHE.clear(clear_database=True)

            LOG.info('Logout successful')
            ui.show_notification(common.get_local_string(30113))
            self._init_session()
        common.container_update('path', True)  # Go to a fake page to clear screen
        # Open root page
        common.container_update(G.BASE_URL, True)


def _extract_clcs_bootstrap(content):
    """Read the initial CLCS screen state embedded in the login page"""
    html = content.decode('utf-8') if isinstance(content, bytes) else content
    server_state = _find_page_value(html, 'serverState')
    # Get the sign in action, that provides the screen update value and the fields to be sent
    actions = re.findall(r'"inputFieldRequirements":\[(.*?)\],"preload":[^,]*,"serverScreenUpdate":"([^"]+)"',
                         html, re.DOTALL)
    screen_updates = [website.decode_javascript_string(value) for _, value in actions]
    if not screen_updates:
        screen_updates = [website.decode_javascript_string(value)
                          for value in re.findall(r'"serverScreenUpdate":"([^"]+)"', html)]
    if not server_state or not screen_updates:
        _log_login_page_diagnostics(html)
        raise WebsiteParsingError('CLCS login state not found in the login page')
    action_fields = re.findall(r'"id":"(\w+)"', actions[-1][0]) if actions else []
    build_match = re.search(r'"BUILD_IDENTIFIER":"([^"]+)"', html)
    app_version = build_match.group(1) if build_match else ''
    LOG.debug('CLCS login, sign in action fields {}', action_fields)
    iso_match = re.search(r'"requestCountry":\{[^{}]*?"id":"([A-Z]{2})"', html)
    country = {'iso': iso_match.group(1) if iso_match else 'US', 'code': '1'}
    return server_state, screen_updates[-1], country, action_fields, app_version


def _graphql_login_headers(server_state=None, app_version=''):
    """Set the same headers of the website, needed to get the request accepted"""
    import uuid
    page_url = ep.BASE_URL + '/login'
    if server_state:
        page_url += '?serverState=' + quote(server_state, safe='')
    headers = {
        'Accept': '*/*',
        'Content-Type': 'application/json',
        'Origin': ep.BASE_URL,
        'Referer': page_url,
        'x-netflix.request.originating.url': page_url,
        'x-netflix.request.id': uuid.uuid4().hex,
        'x-netflix.request.toplevel.uuid': str(uuid.uuid4()),
        'x-netflix.request.attempt': '1',
        'x-netflix.request.clcs.bucket': 'high',
        'x-netflix.request.client.context': '{"appView":"identification","action":"Submitted","appstate":"foreground"}',
        'x-netflix.context.ui-flavor': 'akira',
        'x-netflix.context.operation-name': 'CLCSScreenUpdate',
        'x-netflix.context.locales': 'en-us',
        'x-netflix.context.hawkins-version': '5.26.0',
        'x-netflix.context.app-version': app_version,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin'
    }
    headers.update({key: value for key, value in BROWSER_HEADERS.items()
                    if key in ('User-Agent', 'Accept-Language', 'Sec-GPC')})
    return headers


def _find_page_value(html, key):
    match = re.search(r'"' + key + r'":"([^"]*)"', html)
    return website.decode_javascript_string(match.group(1)) if match else None


def _log_login_page_diagnostics(html):
    """Dump the login form so the form-post login can be rebuilt from real data"""
    LOG.error('LOGIN diagnostics: page length {}', len(html))
    for form in re.findall(r'<form[^>]*>', html):
        LOG.error('LOGIN diagnostics: form {}', form)
    for input_tag in re.findall(r'<input[^>]*>', html):
        LOG.error('LOGIN diagnostics: input {}', input_tag)
    for assignment in re.findall(r"nonmemberStaticFramework[^\n;]{0,120}=\s*[^\n;]{0,500};", html):
        LOG.error('LOGIN diagnostics: data {}', assignment.strip())
    for marker in ['authURL', 'nonmemberStaticFramework.data', 'recaptcha', 'useEnterprise', 'action']:
        index = html.find(marker)
        if index != -1:
            LOG.error('LOGIN diagnostics: context [{}] {}', marker, html[max(0, index - 80):index + 320])


def _clcs_field(name, value_type, value):
    return {'name': name, 'value': {value_type: value}}


def _iter_clcs_nodes(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_clcs_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_clcs_nodes(value)


def _select_clcs_action(screen):
    """Pick the screen action that asks for a one-time code or the password"""
    otp_action = None
    password_action = None
    for node in _iter_clcs_nodes(screen):
        if node.get('__typename') != 'CLCSRequestScreenUpdate':
            continue
        requirements = node.get('inputFieldRequirements')
        if not requirements or not node.get('serverScreenUpdate'):
            continue
        field_ids = [(req.get('field') or {}).get('id', '') for req in requirements]
        kind = _classify_clcs_fields(field_ids)
        if kind == 'otp' and not otp_action:
            otp_action = node
        elif kind == 'password' and not password_action:
            password_action = node
    if otp_action:
        return otp_action, 'otp'
    if password_action:
        return password_action, 'password'
    return None, None


def _classify_clcs_fields(field_ids):
    lowered = [field_id.lower() for field_id in field_ids]
    if any('otp' in fid or 'pin' in fid or 'challenge' in fid for fid in lowered):
        return 'otp'
    if any('password' in fid or 'passcode' in fid or fid == 'credential' for fid in lowered):
        return 'password'
    return None


def _build_clcs_fields(requirements, credentials, kind, screen, country):
    input_fields = []
    for requirement in requirements:
        field = requirement.get('field') or {}
        field_id = field.get('id')
        if not field_id:
            continue
        lowered = field_id.lower()
        if 'otp' in lowered or 'pin' in lowered or 'challenge' in lowered:
            code = ui.ask_for_input(_find_clcs_title(screen) or 'Enter the code Netflix sent you')
            if not code:
                raise MissingCredentialsError
            value = code.strip()
        elif 'password' in lowered or 'passcode' in lowered or field_id == 'credential':
            value = credentials['password']
        elif field_id == 'userLoginId':
            value = credentials['email']
        elif field_id == 'countryCode':
            value = country['code']
        elif field_id == 'countryIsoCode':
            value = country['iso']
        elif field_id == 'rememberMe':
            value = True
        else:
            # The reCaptcha fields are optional, the other fields keep their initial value
            if not lowered.startswith('recaptcha'):
                LOG.warn('CLCS login, unhandled required field {} ({})', field_id, field.get('fieldType'))
            value = field.get('initialStringValue') or ''
        input_fields.append(_clcs_typed_field(field, field_id, value))
    if kind == 'password' and not any(fld['name'] == 'password' for fld in input_fields):
        input_fields.append(_clcs_field('password', 'stringValue', credentials['password']))
    return input_fields


def _clcs_recaptcha_fields(field_ids):
    """The reCaptcha token can be produced only by the Google script in a web browser,
    report the same timeout error of the website when the script cannot be executed,
    the token must not be sent otherwise the request is refused"""
    input_fields = []
    if 'recaptchaError' in field_ids:
        input_fields.append(_clcs_field('recaptchaError', 'stringValue', 'RESPONSE_TIMED_OUT'))
    if 'recaptchaResponseTime' in field_ids:
        input_fields.append(_clcs_field('recaptchaResponseTime', 'intValue', RECAPTCHA_TIMEOUT_MS))
    return input_fields


def _clcs_typed_field(field, field_id, value):
    """Build an input field with the value type declared by the screen"""
    field_type = field.get('fieldType') or ''
    if 'Boolean' in field_type:
        return _clcs_field(field_id, 'boolValue', bool(value))
    if 'Integer' in field_type or 'Number' in field_type:
        try:
            return _clcs_field(field_id, 'intValue', int(value))
        except (TypeError, ValueError):
            return _clcs_field(field_id, 'intValue', 0)
    return _clcs_field(field_id, 'stringValue', '' if value is None else str(value))


def _find_clcs_title(screen):
    for node in _iter_clcs_nodes(screen):
        if node.get('__typename') == 'CLCSText' and node.get('testId') == 'title':
            return (node.get('plainContent') or {}).get('value')
    return None


def _find_clcs_message(node):
    """Get the message shown by the screen, the alerts of the actions are a generic fallback text"""
    for item in _iter_clcs_nodes(node):
        if item.get('__typename') != 'CLCSText':
            continue
        test_id = (item.get('testId') or '').lower()
        value = (item.get('plainContent') or {}).get('value')
        if value and ('error' in test_id or 'message' in test_id):
            return value
    return _find_clcs_title(node)


def _log_clcs_screen_diagnostics(screen):
    """Dump the received screen to understand which step the login flow is asking for"""
    LOG.debug('CLCS screen: title {}', _find_clcs_title(screen))
    texts = []
    actions = []
    for node in _iter_clcs_nodes(screen):
        typename = node.get('__typename')
        if typename == 'CLCSText':
            value = (node.get('plainContent') or {}).get('value')
            if value:
                texts.append(f"[{node.get('testId')}] {value}")
        elif typename == 'CLCSRequestScreenUpdate' and node.get('inputFieldRequirements'):
            field_ids = [(req.get('field') or {}).get('id') for req in node['inputFieldRequirements']]
            actions.append(field_ids)
    for text in texts[:25]:
        LOG.debug('CLCS screen text: {}', text)
    # The messages are not always in a text component, get every localized string of the screen
    strings = []
    for node in _iter_clcs_nodes(screen):
        if node.get('__typename') in ('GrowthLocalizedString', 'GrowthLocalizedFormattedString'):
            value = node.get('value')
            if value and value not in strings:
                strings.append(value)
    for value in strings[:30]:
        LOG.debug('CLCS screen string: {}', value)
    for node in _iter_clcs_nodes(screen):
        test_id = node.get('testId') or ''
        if any(key in test_id for key in ('alert', 'error', 'message')):
            LOG.debug('CLCS screen alert node [{}]: {}', test_id, json.dumps(node)[:1200])
    for field_ids in actions:
        LOG.debug('CLCS screen action fields: {}', field_ids)
    components = sorted({node.get('__typename') for node in _iter_clcs_nodes(screen)
                         if isinstance(node.get('__typename'), str)})
    LOG.debug('CLCS screen components: {}', components)
