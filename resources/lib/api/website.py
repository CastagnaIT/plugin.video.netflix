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
from re import compile as recompile, DOTALL, sub, findall
from collections import OrderedDict

import resources.lib.common as common

from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.globals import g
from .paths import resolve_refs
from .exceptions import (InvalidProfilesError, InvalidAuthURLError, InvalidMembershipStatusError,
                         WebsiteParsingError, LoginValidateError)

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
    'api_endpoint_url': 'models/playerModel/data/config/ui/initParams/apiUrl'
}

PAGE_ITEM_ERROR_CODE = 'models/flow/data/fields/errorCode/value'
PAGE_ITEM_ERROR_CODE_LIST = 'models\\i18nStrings\\data\\login/login'

JSON_REGEX = r'netflix\.{}\s*=\s*(.*?);\s*</script>'
AVATAR_SUBPATH = ['images', 'byWidth', '320']


@common.time_execution(immediate=True)
def extract_session_data(content, validate=False):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    common.debug('Extracting session data...')
    react_context = extract_json(content, 'reactContext')
    if validate:
        validate_login(react_context)

    user_data = extract_userdata(react_context)
    if user_data.get('membershipStatus') != 'CURRENT_MEMBER':
        # When NEVER_MEMBER it is possible that the account has not been confirmed or renewed
        common.error('Can not login, the Membership status is {}',
                     user_data.get('membershipStatus'))
        raise InvalidMembershipStatusError(user_data.get('membershipStatus'))

    api_data = extract_api_data(react_context)
    # Note: falcor cache does not exist if membershipStatus is not CURRENT_MEMBER
    # falcor cache is not more used to extract profiles data
    # falcor_cache = extract_json(content, 'falcorCache')

    # Save only some info of the current profile from user data
    g.LOCAL_DB.set_value('build_identifier', user_data.get('BUILD_IDENTIFIER'), TABLE_SESSION)
    if not g.LOCAL_DB.get_value('esn', table=TABLE_SESSION):
        g.LOCAL_DB.set_value('esn', generate_esn(user_data), TABLE_SESSION)
    g.LOCAL_DB.set_value('locale_id', user_data.get('preferredLocale').get('id', 'en-US'))
    # Save api urls
    for key, path in list(api_data.items()):
        g.LOCAL_DB.set_value(key, path, TABLE_SESSION)


@common.time_execution(immediate=True)
def parse_profiles(profiles_list_data):
    """Parse profile information from Netflix response"""
    try:
        profiles_list = OrderedDict(resolve_refs(profiles_list_data['profilesList'],
                                                 profiles_list_data))
        if not profiles_list:
            raise InvalidProfilesError('It has not been possible to obtain the list of profiles.')
        _delete_non_existing_profiles(profiles_list)
        sort_order = 0
        debug_info = ['profileName', 'isAccountOwner', 'isActive', 'isKids', 'maturityLevel']
        for guid, profile in list(profiles_list.items()):
            common.debug('Parsing profile {}', guid)
            avatar_url = _get_avatar(profiles_list_data, profile)
            profile = profile['summary']
            for k_info in debug_info:
                common.debug('Profile info {}', {k_info: profile[k_info]})
            is_active = profile.pop('isActive')
            g.LOCAL_DB.set_profile(guid, is_active, sort_order)
            g.SHARED_DB.set_profile(guid, sort_order)
            for key, value in list(profile.items()):
                g.LOCAL_DB.set_profile_config(key, value, guid)
            g.LOCAL_DB.set_profile_config('avatar', avatar_url, guid)
            sort_order += 1
    except Exception:
        import traceback
        common.error(traceback.format_exc())
        common.error('Profile list data: {}', profiles_list_data)
        raise InvalidProfilesError


# @common.time_execution(immediate=True)
# def extract_profiles(falkor_cache):
#    """Extract profile information from Netflix website"""
#    try:
#        profiles_list = OrderedDict(resolve_refs(falkor_cache['profilesList'], falkor_cache))
#        if not profiles_list:
#            common.error('The profiles list from falkor cache is empty. '
#                         'The profiles were not parsed nor updated!')
#        else:
#            _delete_non_existing_profiles(profiles_list)
#        sort_order = 0
#        for guid, profile in list(profiles_list.items()):
#            common.debug('Parsing profile {}', guid)
#            avatar_url = _get_avatar(falkor_cache, profile)
#            profile = profile['summary']['value']
#            debug_info = ['profileName', 'isAccountOwner', 'isActive', 'isKids', 'maturityLevel']
#            for k_info in debug_info:
#                common.debug('Profile info {}', {k_info: profile[k_info]})
#            is_active = profile.pop('isActive')
#            g.LOCAL_DB.set_profile(guid, is_active, sort_order)
#            g.SHARED_DB.set_profile(guid, sort_order)
#            for key, value in list(profile.items()):
#                g.LOCAL_DB.set_profile_config(key, value, guid)
#            g.LOCAL_DB.set_profile_config('avatar', avatar_url, guid)
#            sort_order += 1
#    except Exception:
#        import traceback
#        common.error(traceback.format_exc())
#        common.error('Falkor cache: {}', falkor_cache)
#        raise


def _delete_non_existing_profiles(profiles_list):
    list_guid = g.LOCAL_DB.get_guid_profiles()
    for guid in list_guid:
        if guid not in list(profiles_list):
            common.debug('Deleting non-existing profile {}', guid)
            g.LOCAL_DB.delete_profile(guid)
            g.SHARED_DB.delete_profile(guid)


def _get_avatar(profiles_list_data, profile):
    try:
        profile['avatar'].extend(AVATAR_SUBPATH)
        return common.get_path(profile['avatar'], profiles_list_data)
    except KeyError:
        common.warn('Cannot find avatar for profile {guid}'
                    .format(guid=profile['summary']['value']['guid']))
    return ''


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
            raise LoginValidateError(common.remove_html_tags(error_description))
        except (AttributeError, KeyError):
            import traceback
            common.error(traceback.format_exc())
            error_msg = (
                'Something is wrong in PAGE_ITEM_ERROR_CODE or PAGE_ITEM_ERROR_CODE_LIST paths.'
                'react_context data may have changed.')
            common.error(error_msg)
            raise LoginValidateError(error_msg)


def generate_esn(user_data):
    """Generate an ESN if on android or return the one from user_data"""
    import subprocess
    try:
        manufacturer = subprocess.check_output(
            ['/system/bin/getprop',
             'ro.product.manufacturer']).decode('utf-8').strip(' \t\n\r')
        if manufacturer:
            model = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.product.model']).decode('utf-8').strip(' \t\n\r')
            product_characteristics = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.build.characteristics']).decode('utf-8').strip(' \t\n\r')
            # Property ro.build.characteristics may also contain more then one value
            has_product_characteristics_tv = any(
                value.strip(' ') == 'tv' for value in product_characteristics.split(','))
            # Netflix Ready Device Platform (NRDP)
            nrdp_modelgroup = subprocess.check_output(
                ['/system/bin/getprop',
                 'ro.nrdp.modelgroup']).decode('utf-8').strip(' \t\n\r')

            esn = ('NFANDROID2-PRV-' if has_product_characteristics_tv else 'NFANDROID1-PRV-')
            if has_product_characteristics_tv:
                if nrdp_modelgroup:
                    esn += nrdp_modelgroup + '-'
                else:
                    esn += model.replace(' ', '').upper() + '-'
            else:
                esn += 'T-L3-'
            esn += '{:=<5.5}'.format(manufacturer.upper())
            esn += model.replace(' ', '=').upper()
            esn = sub(r'[^A-Za-z0-9=-]', '=', esn)
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
        json_str = json_str.replace('\"', '\\"')  # Escape double-quotes
        json_str = json_str.replace('\\s', '\\\\s')  # Escape \s
        json_str = json_str.replace('\\n', '\\\\n')  # Escape line feed
        json_str = json_str.replace('\\t', '\\\\t')  # Escape tab
        json_str = json_str.encode().decode('unicode_escape')  # finally decoding...
        return json.loads(json_str)
    except Exception:
        if json_str:
            common.error('JSON string trying to load: {}', json_str)
        import traceback
        common.error(traceback.format_exc())
        raise WebsiteParsingError('Unable to extract {}'.format(name))


def extract_parental_control_data(content):
    """Extract the content of parental control data"""
    html_ml_points = findall(r'<div class="maturity-input-item\s.*?<\/div>',
                             content.decode('utf-8'))
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
    return {'maturity_levels': maturity_levels, 'maturity_names': maturity_names,
            'current_level': current_level}
