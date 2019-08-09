# -*- coding: utf-8 -*-
"""Parsing of Netflix Website"""
from __future__ import unicode_literals

import json
import traceback
from re import compile as recompile, DOTALL, sub
from collections import OrderedDict

import resources.lib.common as common

from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.globals import g
from .paths import resolve_refs
from .exceptions import (InvalidProfilesError, InvalidAuthURLError, InvalidMembershipStatusError,
                         WebsiteParsingError, LoginValidateError)

PAGE_ITEMS_INFO = [
    'models/userInfo/data/name',
    'models/userInfo/data/guid',
    'models/userInfo/data/countryOfSignup',
    'models/userInfo/data/membershipStatus',
    'models/userInfo/data/isTestAccount',
    'models/userInfo/data/deviceTypeId',
    'models/userInfo/data/isAdultVerified',
    'models/userInfo/data/pinEnabled',
    'models/serverDefs/data/BUILD_IDENTIFIER',
    'models/esnGeneratorModel/data/esn',
    'models/memberContext/data/geo/preferredLocale'
]

PAGE_ITEMS_API_URL = {
    'auth_url': 'models/userInfo/data/authURL',
    # 'ichnaea_log': 'models/serverDefs/data/ICHNAEA_ROOT',  can be for XSS attacks?
    'api_endpoint_root_url': 'models/serverDefs/data/API_ROOT',
    'api_endpoint_url': 'models/playerModel/data/config/ui/initParams/apiUrl'
}

PAGE_ITEM_ERROR_CODE = 'models/flow/data/fields/errorCode/value'
PAGE_ITEM_ERROR_CODE_LIST = 'models\\i18nStrings\\data\\login/login'

JSON_REGEX = r'netflix\.%s\s*=\s*(.*?);\s*</script>'
AVATAR_SUBPATH = ['images', 'byWidth', '320', 'value']


@common.time_execution(immediate=True)
def extract_session_data(content):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    common.debug('Extracting session data...')
    falcor_cache = extract_json(content, 'falcorCache')
    react_context = extract_json(content, 'reactContext')
    extract_profiles(falcor_cache)
    user_data = extract_userdata(react_context)
    api_data = extract_api_data(react_context)
    # Save only some info of the current profile from user data
    g.LOCAL_DB.set_value('build_identifier', user_data.get('BUILD_IDENTIFIER'), TABLE_SESSION)
    esn_generated = generate_esn(user_data)
    if not g.ADDON.getSetting('esn'):
        g.LOCAL_DB.set_value('esn', esn_generated, TABLE_SESSION)
    g.LOCAL_DB.set_value('esn_generated', esn_generated, TABLE_SESSION)
    g.LOCAL_DB.set_value('locale_id', user_data.get('preferredLocale').get('id', 'en-US'))
    # Save api urls
    for key, path in api_data.items():
        g.LOCAL_DB.set_value(key, path, TABLE_SESSION)
    if user_data.get('membershipStatus') != 'CURRENT_MEMBER':
        common.debug(user_data)
        # Ignore this for now
        # raise InvalidMembershipStatusError(user_data.get('membershipStatus'))


@common.time_execution(immediate=True)
def extract_profiles(falkor_cache):
    """Extract profile information from Netflix website"""
    try:
        profiles_list = OrderedDict(resolve_refs(falkor_cache['profilesList'], falkor_cache))
        _delete_non_existing_profiles(profiles_list)
        sort_order = 0
        for guid, profile in profiles_list.items():
            common.debug('Parsing profile {}'.format(guid))
            avatar_url = _get_avatar(falkor_cache, profile)
            profile = profile['summary']['value']
            is_active = profile.pop('isActive')
            g.LOCAL_DB.set_profile(guid, is_active, sort_order)
            g.SHARED_DB.set_profile(guid, None, sort_order)
            for key, value in profile.items():
                g.LOCAL_DB.set_profile_config(key, value, guid)
            g.LOCAL_DB.set_profile_config('avatar', avatar_url, guid)
            sort_order += 1
    except Exception:
        common.error(traceback.format_exc())
        common.error('Falkor cache: {}'.format(falkor_cache))
        raise InvalidProfilesError


def _delete_non_existing_profiles(profiles_list):
    list_guid = g.LOCAL_DB.get_guid_profiles()
    for guid in list_guid:
        if guid not in profiles_list.keys():
            common.debug('Deleting non-existing profile {}'.format(guid))
            g.LOCAL_DB.delete_profile(guid)
            g.SHARED_DB.delete_profile(guid)


def _get_avatar(falkor_cache, profile):
    try:
        profile['avatar']['value'].extend(AVATAR_SUBPATH)
        return common.get_path(profile['avatar']['value'], falkor_cache)
    except KeyError:
        common.warn('Cannot find avatar for profile {guid}'
                    .format(guid=profile['summary']['value']['guid']))
    return ''


@common.time_execution(immediate=True)
def extract_userdata(react_context):
    """Extract essential userdata from the reactContext of the webpage"""
    common.debug('Extracting userdata from webpage')
    user_data = {}
    for path in ([path_item for path_item in path.split('/')]
                 for path in PAGE_ITEMS_INFO):
        try:
            extracted_value = {path[-1]: common.get_path(path, react_context)}
            user_data.update(extracted_value)
            common.debug('Extracted {}'.format(extracted_value))
        except (AttributeError, KeyError):
            common.debug('Could not extract {}'.format(path))
    return user_data


def extract_api_data(react_context):
    """Extract api urls from the reactContext of the webpage"""
    common.debug('Extracting api urls from webpage')
    api_data = {}
    for key, value in PAGE_ITEMS_API_URL.items():
        path = [path_item for path_item in value.split('/')]
        try:
            extracted_value = {key: common.get_path(path, react_context)}
            api_data.update(extracted_value)
            common.debug('Extracted {}'.format(extracted_value))
        except (AttributeError, KeyError):
            common.debug('Could not extract {}'.format(path))
    return assert_valid_auth_url(api_data)


def assert_valid_auth_url(user_data):
    """Raise an exception if user_data does not contain a valid authURL"""
    if len(user_data.get('auth_url', '')) != 42:
        raise InvalidAuthURLError('authURL is invalid')
    return user_data


def validate_login(content):
    react_context = extract_json(content, 'reactContext')
    path_code_list = [path_item for path_item in PAGE_ITEM_ERROR_CODE_LIST.split('\\')]
    path_error_code = [path_item for path_item in PAGE_ITEM_ERROR_CODE.split('/')]
    if common.check_path_exists(path_error_code, react_context):
        # If the path exists, a login error occurs
        try:
            error_code_list = common.get_path(path_code_list, react_context)
            error_code = common.get_path(path_error_code, react_context)
            common.debug('Login not valid, error code {}'.format(error_code))
            error_description = common.get_local_string(30102) + error_code
            if error_code in error_code_list:
                error_description = error_code_list[error_code]
            if 'email_' + error_code in error_code_list:
                error_description = error_code_list['email_' + error_code]
            if 'login_' + error_code in error_code_list:
                error_description = error_code_list['login_' + error_code]
            return common.remove_html_tags(error_description)
        except (AttributeError, KeyError):
            common.error(
                'Something is wrong in PAGE_ITEM_ERROR_CODE or PAGE_ITEM_ERROR_CODE_LIST paths.'
                'react_context data may have changed.')
            raise LoginValidateError
    return None


def generate_esn(user_data):
    """Generate an ESN if on android or return the one from user_data"""
    import subprocess
    try:
        manufacturer = subprocess.check_output(
            ['/system/bin/getprop', 'ro.product.manufacturer'])
        if manufacturer:
            esn = ('NFANDROID1-PRV-'
                   if subprocess.check_output(
                       ['/system/bin/getprop', 'ro.build.characteristics']
                   ).strip(' \t\n\r') != 'tv'
                   else 'NFANDROID2-PRV-')
            inp = subprocess.check_output(
                ['/system/bin/getprop', 'ro.nrdp.modelgroup']).strip(' \t\n\r')
            if not inp:
                esn += 'T-L3-'
            else:
                esn += inp + '-'
            esn += '{:=<5}'.format(manufacturer.strip(' \t\n\r').upper())
            inp = subprocess.check_output(
                ['/system/bin/getprop', 'ro.product.model'])
            esn += inp.strip(' \t\n\r').replace(' ', '=').upper()
            esn = sub(r'[^A-Za-z0-9=-]', '=', esn)
            common.debug('Android generated ESN:' + esn)
            return esn
    except OSError:
        pass

    return user_data.get('esn', '')


@common.time_execution(immediate=True)
def extract_json(content, name):
    """Extract json from netflix content page"""
    common.debug('Extracting {} JSON'.format(name))
    json_str = None
    try:
        json_array = recompile(JSON_REGEX % name, DOTALL).findall(content)
        json_str = json_array[0]
        json_str = json_str.replace('\"', '\\"')  # Escape double-quotes
        json_str = json_str.replace('\\s', '\\\\s')  # Escape \s
        json_str = json_str.replace('\\n', '\\\\n')  # Escape line feed
        json_str = json_str.replace('\\t', '\\\\t')  # Escape tab
        json_str = json_str.decode('unicode_escape')  # finally decoding...
        return json.loads(json_str)
    except Exception:
        if json_str:
            common.error('JSON string trying to load: {}'.format(json_str))
        common.error(traceback.format_exc())
        raise WebsiteParsingError('Unable to extract {}'.format(name))
