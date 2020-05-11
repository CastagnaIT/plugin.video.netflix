# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Parsing of Netflix Website

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json
from re import compile as recompile, DOTALL, sub

from future.utils import iteritems

import xbmc

import resources.lib.common as common
from resources.lib.database.db_exceptions import ProfilesMissing
from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.globals import g
from .exceptions import (InvalidProfilesError, InvalidAuthURLError, InvalidMembershipStatusError,
                         WebsiteParsingError, LoginValidateError, InvalidMembershipStatusAnonymous,
                         LoginValidateErrorIncorrectPassword)
from .paths import jgraph_get, jgraph_get_list, jgraph_get_path

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

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

PROFILE_DEBUG_INFO = ['profileName', 'isAccountOwner', 'isActive', 'isKids', 'maturityLevel']


@common.time_execution(immediate=True)
def extract_session_data(content, validate=False, update_profiles=False):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    common.debug('Extracting session data...')
    react_context = extract_json(content, 'reactContext')
    if validate:
        validate_login(react_context)

    user_data = extract_userdata(react_context)
    if user_data.get('membershipStatus') == 'ANONYMOUS':
        # Possible known causes:
        # -Login password has been changed
        # -In the login request, 'Content-Type' specified is not compliant with data passed or no more supported
        # -Expired profiles cookies!? (not verified)
        # In these cases it is mandatory to login again
        raise InvalidMembershipStatusAnonymous
    if user_data.get('membershipStatus') != 'CURRENT_MEMBER':
        # When NEVER_MEMBER it is possible that the account has not been confirmed or renewed
        common.error('Can not login, the Membership status is {}',
                     user_data.get('membershipStatus'))
        raise InvalidMembershipStatusError(user_data.get('membershipStatus'))

    api_data = extract_api_data(react_context)
    # Note: Falcor cache does not exist if membershipStatus is not CURRENT_MEMBER
    falcor_cache = extract_json(content, 'falcorCache')

    if update_profiles:
        parse_profiles(falcor_cache)

    # Extract lolomo root id
    lolomo_root = falcor_cache['lolomo']['value'][1]
    g.LOCAL_DB.set_value('lolomo_root_id', lolomo_root, TABLE_SESSION)

    # Check if current 'profile session' is still active
    # What means 'profile session':
    # In web browser, after you select a profile and then you close the browse page,
    #   when you reopen it you will not be asked to select a profile again, this means that the same profile session
    #   still active, and the lolomo root id (and child contexts id's) are still the same.
    #   Here one way to understand this, is checking if there is an 'summary' entry in the lolomos dictionary.
    is_profile_session_active = 'summary' in falcor_cache['lolomos'][lolomo_root]

    # Extract lolomo continueWatching id and index
    cw_list_data = jgraph_get('continueWatching', falcor_cache['lolomos'][lolomo_root], falcor_cache)
    if cw_list_data:
        context_index = falcor_cache['lolomos'][lolomo_root]['continueWatching']['value'][2]
        g.LOCAL_DB.set_value('lolomo_continuewatching_index', context_index, TABLE_SESSION)
        g.LOCAL_DB.set_value('lolomo_continuewatching_id', jgraph_get('id', cw_list_data), TABLE_SESSION)
    elif is_profile_session_active:
        # Todo: In the new profiles, there is no 'continueWatching' context
        #  How get or generate the continueWatching context?
        #  (needed to update lolomo list for watched state sync, see update_lolomo_context in api_requests.py)
        cur_profile = jgraph_get_path(['profilesList', 'current'], falcor_cache)
        common.warn('Context continueWatching not found in lolomos for profile guid {}.',
                    jgraph_get('summary', cur_profile)['guid'])
        g.LOCAL_DB.set_value('lolomo_continuewatching_index', '', TABLE_SESSION)
        g.LOCAL_DB.set_value('lolomo_continuewatching_id', '', TABLE_SESSION)
    else:
        common.warn('Is not possible to find the context continueWatching, the profile session is no more active')

    # Save only some info of the current profile from user data
    g.LOCAL_DB.set_value('build_identifier', user_data.get('BUILD_IDENTIFIER'), TABLE_SESSION)
    if not g.LOCAL_DB.get_value('esn', table=TABLE_SESSION):
        g.LOCAL_DB.set_value('esn', generate_esn(user_data), TABLE_SESSION)
    g.LOCAL_DB.set_value('locale_id', user_data.get('preferredLocale').get('id', 'en-US'))
    # Save api urls
    for key, path in list(api_data.items()):
        g.LOCAL_DB.set_value(key, path, TABLE_SESSION)

    api_data['is_profile_session_active'] = is_profile_session_active
    return api_data


@common.time_execution(immediate=True)
def parse_profiles(data):
    """Parse profile information from Netflix response"""
    profiles_list = jgraph_get_list('profilesList', data)
    try:
        if not profiles_list:
            raise InvalidProfilesError('It has not been possible to obtain the list of profiles.')
        sort_order = 0
        current_guids = []
        for index, profile_data in iteritems(profiles_list):  # pylint: disable=unused-variable
            summary = jgraph_get('summary', profile_data)
            guid = summary['guid']
            current_guids.append(guid)
            common.debug('Parsing profile {}', summary['guid'])
            avatar_url = _get_avatar(profile_data, data, guid)
            is_active = summary.pop('isActive')
            g.LOCAL_DB.set_profile(guid, is_active, sort_order)
            g.SHARED_DB.set_profile(guid, sort_order)
            # Add profile language description translated from locale
            summary['language_desc'] = xbmc.convertLanguage(summary['language'][:2], xbmc.ENGLISH_NAME)
            for key, value in iteritems(summary):
                if key in PROFILE_DEBUG_INFO:
                    common.debug('Profile info {}', {key: value})
                if key == 'profileName':  # The profile name is coded as HTML
                    value = parse_html(value)
                g.LOCAL_DB.set_profile_config(key, value, guid)
            g.LOCAL_DB.set_profile_config('avatar', avatar_url, guid)
            sort_order += 1
        _delete_non_existing_profiles(current_guids)
    except Exception:
        import traceback
        common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        common.error('Profile list data: {}', profiles_list)
        raise InvalidProfilesError


def _delete_non_existing_profiles(current_guids):
    list_guid = g.LOCAL_DB.get_guid_profiles()
    for guid in list_guid:
        if guid not in current_guids:
            common.debug('Deleting non-existing profile {}', guid)
            g.LOCAL_DB.delete_profile(guid)
            g.SHARED_DB.delete_profile(guid)
    # Ensures at least one active profile
    try:
        g.LOCAL_DB.get_active_profile_guid()
    except ProfilesMissing:
        g.LOCAL_DB.switch_active_profile(g.LOCAL_DB.get_guid_owner_profile())
    # Verify if auto select profile exists
    autoselect_profile_guid = g.LOCAL_DB.get_value('autoselect_profile_guid', '')
    if autoselect_profile_guid and autoselect_profile_guid not in current_guids:
        common.warn('Auto-selection disabled, the GUID {} not more exists', autoselect_profile_guid)
        g.LOCAL_DB.set_value('autoselect_profile_guid', '')
        g.settings_monitor_suspend(True)
        g.ADDON.setSetting('autoselect_profile_name', '')
        g.ADDON.setSettingBool('autoselect_profile_enabled', False)
        g.settings_monitor_suspend(False)


def _get_avatar(profile_data, data, guid):
    try:
        avatar = jgraph_get('avatar', profile_data, data)
        return jgraph_get_path(AVATAR_SUBPATH, avatar)
    except (KeyError, TypeError):
        common.warn('Cannot find avatar for profile {}', guid)
        common.debug('Profile list data: {}', profile_data)
        return g.ICON


@common.time_execution(immediate=True)
def extract_userdata(react_context, debug_log=True):
    """Extract essential userdata from the reactContext of the webpage"""
    common.debug('Extracting userdata from webpage')
    user_data = {}

    for path in (path.split('/') for path in PAGE_ITEMS_INFO):
        try:
            extracted_value = {path[-1]: common.get_path(path, react_context)}
            user_data.update(extracted_value)
            if 'esn' not in path and debug_log:
                common.debug('Extracted {}', extracted_value)
        except (AttributeError, KeyError):
            common.error('Could not extract {}', path)
    return user_data


def extract_api_data(react_context, debug_log=True):
    """Extract api urls from the reactContext of the webpage"""
    common.debug('Extracting api urls from webpage')
    api_data = {}
    for key, value in list(PAGE_ITEMS_API_URL.items()):
        path = value.split('/')
        try:
            extracted_value = {key: common.get_path(path, react_context)}
            api_data.update(extracted_value)
            if debug_log:
                common.debug('Extracted {}', extracted_value)
        except (AttributeError, KeyError):
            common.error('Could not extract {}', path)
    return assert_valid_auth_url(api_data)


def assert_valid_auth_url(user_data):
    """Raise an exception if user_data does not contain a valid authURL"""
    if len(user_data.get('auth_url', '')) != 42:
        raise InvalidAuthURLError('authURL is invalid')
    return user_data


def validate_login(react_context):
    path_code_list = PAGE_ITEM_ERROR_CODE_LIST.split('\\')
    path_error_code = PAGE_ITEM_ERROR_CODE.split('/')
    if common.check_path_exists(path_error_code, react_context):
        # If the path exists, a login error occurs
        try:
            error_code_list = common.get_path(path_code_list, react_context)
            error_code = common.get_path(path_error_code, react_context)
            common.error('Login not valid, error code {}', error_code)
            error_description = common.get_local_string(30102) + error_code
            if error_code in error_code_list:
                error_description = error_code_list[error_code]
            if 'email_' + error_code in error_code_list:
                error_description = error_code_list['email_' + error_code]
            if 'login_' + error_code in error_code_list:
                error_description = error_code_list['login_' + error_code]
            if 'incorrect_password' in error_code:
                raise LoginValidateErrorIncorrectPassword(common.remove_html_tags(error_description))
            raise LoginValidateError(common.remove_html_tags(error_description))
        except (AttributeError, KeyError):
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            error_msg = (
                'Something is wrong in PAGE_ITEM_ERROR_CODE or PAGE_ITEM_ERROR_CODE_LIST paths.'
                'react_context data may have changed.')
            common.error(error_msg)
            raise LoginValidateError(error_msg)


def generate_esn(user_data):
    """Generate an ESN if on android or return the one from user_data"""
    if common.get_system_platform() == 'android':
        import subprocess
        try:
            manufacturer = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.product.manufacturer']).decode('utf-8').strip(' \t\n\r')
            if manufacturer:
                model = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.product.model']).decode('utf-8').strip(' \t\n\r')

                # This product_characteristics check seem no longer used, some L1 devices not have the 'tv' value
                # like Xiaomi Mi Box 3 or SM-T590 devices and is cause of wrong esn generation
                # product_characteristics = subprocess.check_output(
                #     ['/system/bin/getprop',
                #      'ro.build.characteristics']).decode('utf-8').strip(' \t\n\r')
                # Property ro.build.characteristics may also contain more then one value
                # has_product_characteristics_tv = any(
                #     value.strip(' ') == 'tv' for value in product_characteristics.split(','))

                # Netflix Ready Device Platform (NRDP)
                nrdp_modelgroup = subprocess.check_output(
                    ['/system/bin/getprop',
                     'ro.nrdp.modelgroup']).decode('utf-8').strip(' \t\n\r')

                # if has_product_characteristics_tv and \
                #         g.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1':
                if g.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1':
                    esn = 'NFANDROID2-PRV-'
                    if nrdp_modelgroup:
                        esn += nrdp_modelgroup + '-'
                    else:
                        esn += model.replace(' ', '').upper() + '-'
                else:
                    esn = 'NFANDROID1-PRV-'
                    esn += 'T-L3-'

                esn += '{:=<5.5}'.format(manufacturer.upper())
                esn += model.replace(' ', '=').upper()
                esn = sub(r'[^A-Za-z0-9=-]', '=', esn)
                system_id = g.LOCAL_DB.get_value('drm_system_id', table=TABLE_SESSION)
                if system_id:
                    esn += '-' + str(system_id) + '-'
                common.debug('Android generated ESN: {}', esn)
                return esn
        except OSError:
            pass
    return user_data.get('esn', '')


@common.time_execution(immediate=True)
def extract_json(content, name):
    """Extract json from netflix content page"""
    common.debug('Extracting {} JSON', name)
    json_str = None
    try:
        json_array = recompile(JSON_REGEX.format(name), DOTALL).findall(content.decode('utf-8'))
        json_str = json_array[0]
        json_str_replace = json_str.replace('\\"', '\\\\"')  # Escape double-quotes
        json_str_replace = json_str_replace.replace('\\s', '\\\\s')  # Escape \s
        json_str_replace = json_str_replace.replace('\\n', '\\\\n')  # Escape line feed
        json_str_replace = json_str_replace.replace('\\t', '\\\\t')  # Escape tab
        json_str_replace = json_str_replace.encode().decode('unicode_escape')  # Decode the string as unicode
        json_str_replace = sub(r'\\(?!["])', r'\\\\', json_str_replace)  # Escape backslash (only when is not followed by double quotation marks \")
        return json.loads(json_str_replace)
    except Exception:
        if json_str:
            common.error('JSON string trying to load: {}', json_str)
        import traceback
        common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        raise WebsiteParsingError('Unable to extract {}'.format(name))


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
    except KeyError:
        raise WebsiteParsingError('Unable to get path in to reactContext data')
    if not rating_levels:
        raise WebsiteParsingError('Unable to get maturity rating levels')
    return {'rating_levels': rating_levels, 'current_level_index': current_level_index}


def parse_html(html_value):
    """Parse HTML entities"""
    try:  # Python 2
        from HTMLParser import HTMLParser
    except ImportError:  # Python 3
        from html.parser import HTMLParser
    return HTMLParser().unescape(html_value)
