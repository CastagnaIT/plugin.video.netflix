# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Parsing of Netflix Website

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
from re import search, compile as recompile, DOTALL, sub

import xbmc

import resources.lib.common as common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.common.exceptions import (InvalidProfilesError, InvalidAuthURLError, MbrStatusError,
                                             WebsiteParsingError, LoginValidateError, MbrStatusAnonymousError,
                                             MbrStatusNeverMemberError, MbrStatusFormerMemberError, DBProfilesMissing)
from .api_paths import jgraph_get, jgraph_get_list, jgraph_get_path
from .esn import get_website_esn, set_website_esn
from .logging import LOG, measure_exec_time_decorator


PAGE_ITEMS_INFO = [
    'models/userInfo/data/name',
    'models/userInfo/data/guid',            # Main profile guid
    'models/userInfo/data/userGuid',        # Current profile guid
    'models/userInfo/data/countryOfSignup',
    'models/userInfo/data/membershipStatus',
    'models/userInfo/data/isTestAccount',
    'models/userInfo/data/deviceTypeId',
    'models/userInfo/data/isAdultVerified',
    'models/userInfo/data/isKids',
    'models/userInfo/data/pinEnabled',
    'models/serverDefs/data/BUILD_IDENTIFIER',
    'models/esnGeneratorModel/data/esn',
    'models/memberContext/data/geo/preferredLocale'
]

PAGE_ITEMS_API_URL = {
    'auth_url': 'models/userInfo/data/authURL',
    # 'ichnaea_log': 'models/serverDefs/data/ICHNAEA_ROOT',  can be for XSS attacks?
    'api_endpoint_root_url': 'models/serverDefs/data/API_ROOT',
    'api_endpoint_url': 'models/playerModel/data/config/ui/initParams/apiUrl',
    'request_id': 'models/serverDefs/data/requestId',
    'asset_core': 'models/playerModel/data/config/core/assets/core',
    'ui_version': 'models/playerModel/data/config/ui/initParams/uiVersion',
    'browser_info_version': 'models/browserInfo/data/version',
    'browser_info_os_name': 'models/browserInfo/data/os/name',
    'browser_info_os_version': 'models/browserInfo/data/os/version',
}

PAGE_ITEM_ERROR_CODE = 'models/flow/data/fields/errorCode/value'
PAGE_ITEM_ERROR_CODE_LIST = 'models\\i18nStrings\\data\\login/login'

JSON_REGEX = r'netflix\.{}\s*=\s*(.*?);\s*</script>'
AVATAR_SUBPATH = ['images', 'byWidth', '320']

PROFILE_DEBUG_INFO = ['isAccountOwner', 'isActive', 'isKids', 'maturityLevel', 'language']


@measure_exec_time_decorator(is_immediate=True)
def extract_session_data(content, validate=False, update_profiles=False):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    LOG.debug('Extracting session data...')
    react_context = extract_json(content, 'reactContext')
    if validate:
        validate_login(react_context)

    user_data = extract_userdata(react_context)
    _check_membership_status(user_data.get('membershipStatus'))

    api_data = extract_api_data(react_context)
    # Note: Falcor cache does not exist if membershipStatus is not CURRENT_MEMBER
    falcor_cache = extract_json(content, 'falcorCache')
    if update_profiles:
        parse_profiles(falcor_cache)
    # Save only some info of the current profile from user data
    G.LOCAL_DB.set_value('build_identifier', user_data.get('BUILD_IDENTIFIER'), TABLE_SESSION)
    if not get_website_esn():
        set_website_esn(user_data['esn'])
    G.LOCAL_DB.set_value('locale_id', user_data.get('preferredLocale').get('id', 'en-US'))
    # Extract the client version from assets core
    result = search(r'-([0-9\.]+)\.js$', api_data.pop('asset_core'))
    if not result:
        LOG.error('It was not possible to extract the client version!')
        api_data['client_version'] = '6.0023.976.011'
    else:
        api_data['client_version'] = result.groups()[0]
    # Save api urls
    G.LOCAL_DB.set_values(api_data, TABLE_SESSION)
    return api_data


def _check_membership_status(status):
    if status == 'CURRENT_MEMBER':
        return
    if status == 'ANONYMOUS':
        # Possible known causes:
        # -Login password has been changed
        # -In the login request, 'Content-Type' specified is not compliant with data passed or no more supported
        # -Expired profiles cookies!? (not verified)
        # In these cases it is mandatory to login again
        raise MbrStatusAnonymousError('ANONYMOUS')
    if status == 'NEVER_MEMBER':
        # The account has not been confirmed
        raise MbrStatusNeverMemberError('NEVER_MEMBER')
    if status == 'FORMER_MEMBER':
        # The account has not been reactivated
        raise MbrStatusFormerMemberError('FORMER_MEMBER')
    LOG.error('Can not login, the Membership status is {}', status)
    raise MbrStatusError(status)


@measure_exec_time_decorator(is_immediate=True)
def parse_profiles(data):
    """Parse profile information from Netflix response"""
    profiles_list = jgraph_get_list('profilesList', data)
    try:
        if not profiles_list:
            raise InvalidProfilesError('It has not been possible to obtain the list of profiles.')
        sort_order = 0
        current_guids = []
        for index, profile_data in profiles_list.items():  # pylint: disable=unused-variable
            summary = jgraph_get('summary', profile_data)
            guid = summary['guid']
            current_guids.append(guid)
            LOG.debug('Parsing profile {}', summary['guid'])
            avatar_url = _get_avatar(profile_data, data, guid)
            is_active = summary.pop('isActive')
            G.LOCAL_DB.set_profile(guid, is_active, sort_order)
            G.SHARED_DB.set_profile(guid, sort_order)
            # Add profile language description translated from locale
            summary['language_desc'] = xbmc.convertLanguage(summary['language'][:2], xbmc.ENGLISH_NAME)
            if LOG.is_enabled:
                for key, value in summary.items():
                    if key in PROFILE_DEBUG_INFO:
                        LOG.debug('Profile info {}', {key: value})
            # Translate the profile name, is coded as HTML
            summary['profileName'] = parse_html(summary['profileName'])
            summary['avatar'] = avatar_url
            G.LOCAL_DB.insert_profile_configs(summary, guid)
            sort_order += 1
        _delete_non_existing_profiles(current_guids)
    except Exception as exc:  # pylint: disable=broad-except
        import traceback
        LOG.error(traceback.format_exc())
        LOG.error('Profile list data: {}', profiles_list)
        raise InvalidProfilesError from exc


def _delete_non_existing_profiles(current_guids):
    list_guid = G.LOCAL_DB.get_guid_profiles()
    for guid in list_guid:
        if guid not in current_guids:
            LOG.debug('Deleting non-existing profile {}', guid)
            G.LOCAL_DB.delete_profile(guid)
            G.SHARED_DB.delete_profile(guid)
    # Ensures at least one active profile
    try:
        G.LOCAL_DB.get_active_profile_guid()
    except DBProfilesMissing:
        G.LOCAL_DB.switch_active_profile(G.LOCAL_DB.get_guid_owner_profile())
    # Verify if auto select profile exists
    autoselect_profile_guid = G.LOCAL_DB.get_value('autoselect_profile_guid', '')
    if autoselect_profile_guid and autoselect_profile_guid not in current_guids:
        LOG.warn('Auto-selection disabled, the GUID {} not more exists', autoselect_profile_guid)
        G.LOCAL_DB.set_value('autoselect_profile_guid', '')
    # Verify if profile for library auto-sync exists
    sync_mylist_profile_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid')
    if sync_mylist_profile_guid and sync_mylist_profile_guid not in current_guids:
        LOG.warn('Library auto-sync disabled, the GUID {} not more exists', sync_mylist_profile_guid)
        with G.SETTINGS_MONITOR.ignore_events(1):
            G.ADDON.setSettingBool('lib_sync_mylist', False)
        G.SHARED_DB.delete_key('sync_mylist_profile_guid')
    # Verify if profile for library playback exists
    library_playback_profile_guid = G.LOCAL_DB.get_value('library_playback_profile_guid')
    if library_playback_profile_guid and library_playback_profile_guid not in current_guids:
        LOG.warn('Profile set for playback from library cleared, the GUID {} not more exists',
                 library_playback_profile_guid)
        G.LOCAL_DB.set_value('library_playback_profile_guid', '')


def _get_avatar(profile_data, data, guid):
    try:
        avatar = jgraph_get('avatar', profile_data, data)
        return jgraph_get_path(AVATAR_SUBPATH, avatar)
    except (KeyError, TypeError):
        LOG.warn('Cannot find avatar for profile {}', guid)
        LOG.debug('Profile list data: {}', profile_data)
        return G.ICON


@measure_exec_time_decorator(is_immediate=True)
def extract_userdata(react_context, debug_log=True):
    """Extract essential userdata from the reactContext of the webpage"""
    LOG.debug('Extracting userdata from webpage')
    user_data = {}

    for path in (path.split('/') for path in PAGE_ITEMS_INFO):
        try:
            extracted_value = {path[-1]: common.get_path(path, react_context)}
            user_data.update(extracted_value)
            if 'esn' not in path and debug_log:
                LOG.debug('Extracted {}', extracted_value)
        except (AttributeError, KeyError):
            LOG.error('Could not extract {}', path)
    return user_data


def extract_api_data(react_context, debug_log=True):
    """Extract api urls from the reactContext of the webpage"""
    LOG.debug('Extracting api urls from webpage')
    api_data = {}
    for key, value in list(PAGE_ITEMS_API_URL.items()):
        path = value.split('/')
        try:
            extracted_value = {key: common.get_path(path, react_context)}
            api_data.update(extracted_value)
            if debug_log:
                LOG.debug('Extracted {}', extracted_value)
        except (AttributeError, KeyError):
            LOG.warn('Could not extract {}', path)
    return assert_valid_auth_url(api_data)


def assert_valid_auth_url(user_data):
    """Raise an exception if user_data does not contain a valid authURL"""
    if len(user_data.get('auth_url', '')) != 42:
        raise InvalidAuthURLError('authURL is not valid')
    return user_data


def validate_login(react_context):
    path_code_list = PAGE_ITEM_ERROR_CODE_LIST.split('\\')
    path_error_code = PAGE_ITEM_ERROR_CODE.split('/')
    if common.check_path_exists(path_error_code, react_context):
        # If the path exists, a login error occurs
        try:
            error_code_list = common.get_path(path_code_list, react_context)
            error_code = common.get_path(path_error_code, react_context)
            LOG.error('Login not valid, error code {}', error_code)
            error_description = common.get_local_string(30102) + error_code
            if f'login_{error_code}' in error_code_list:
                error_description = error_code_list[f'login_{error_code}']
            elif f'email_{error_code}' in error_code_list:
                error_description = error_code_list[f'email_{error_code}']
            elif error_code in error_code_list:
                error_description = error_code_list[error_code]
            raise LoginValidateError(common.remove_html_tags(error_description))
        except (AttributeError, KeyError) as exc:
            import traceback
            LOG.error(traceback.format_exc())
            error_msg = (
                'Something is wrong in PAGE_ITEM_ERROR_CODE or PAGE_ITEM_ERROR_CODE_LIST paths.'
                'react_context data may have changed.')
            LOG.error(error_msg)
            raise WebsiteParsingError(error_msg) from exc


@measure_exec_time_decorator(is_immediate=True)
def extract_json(content, name):
    """Extract json from netflix content page"""
    LOG.debug('Extracting {} JSON', name)
    json_str = None
    try:
        json_array = recompile(JSON_REGEX.format(name), DOTALL).findall(content.decode('utf-8'))
        json_str = json_array[0]
        json_str_replace = json_str.replace(r'\"', r'\\"')  # Escape \"
        json_str_replace = json_str_replace.replace(r'\s', r'\\s')  # Escape whitespace
        json_str_replace = json_str_replace.replace(r'\r', r'\\r')  # Escape return
        json_str_replace = json_str_replace.replace(r'\n', r'\\n')  # Escape line feed
        json_str_replace = json_str_replace.replace(r'\t', r'\\t')  # Escape tab
        json_str_replace = json_str_replace.encode().decode('unicode_escape')  # Decode the string as unicode
        json_str_replace = sub(r'\\(?!["])', r'\\\\', json_str_replace)  # Escape backslash (only when is not followed by double quotation marks \")
        return json.loads(json_str_replace)
    except Exception as exc:  # pylint: disable=broad-except
        if json_str:
            # For testing purposes remember to add raw prefix to the string to test: json_str = r'string to test'
            LOG.error('JSON string trying to load: {}', json_str)
        import traceback
        LOG.error(traceback.format_exc())
        raise WebsiteParsingError(f'Unable to extract {name}') from exc


def extract_parental_control_data(content, current_maturity):
    """Extract the content of parental control data"""
    try:
        react_context = extract_json(content, 'reactContext')
        # Extract country max maturity value
        max_maturity = common.get_path(['models', 'parentalControls', 'data', 'accountProps', 'countryMaxMaturity'],
                                       react_context)
        # Extract rating levels
        rc_rating_levels = common.get_path(['models', 'memberContext', 'data', 'userInfo', 'ratingLevels'],
                                           react_context)
        rating_levels = []
        levels_count = len(rc_rating_levels) - 1
        current_level_index = levels_count
        for index, rating_level in enumerate(rc_rating_levels):
            if index == levels_count:
                # Last level must use the country max maturity level
                level_value = max_maturity
            else:
                level_value = int(rating_level['level'])
            rating_levels.append({'level': index,
                                  'value': level_value,
                                  'label': rating_level['labels'][0]['label'],
                                  'description': parse_html(rating_level['labels'][0]['description'])})
            if level_value == current_maturity:
                current_level_index = index
        if not rating_levels:
            raise WebsiteParsingError('Unable to get maturity rating levels')
        return {'rating_levels': rating_levels, 'current_level_index': current_level_index}
    except KeyError as exc:
        raise WebsiteParsingError('Unable to get path in to reactContext data') from exc


def parse_html(html_value):
    """Parse HTML entities"""
    try:  # Python >= 3.4
        from html import unescape
        return unescape(html_value)
    except ImportError:  # Python <= 3.3
        from html.parser import HTMLParser
        return HTMLParser().unescape(html_value)  # pylint: disable=no-member
