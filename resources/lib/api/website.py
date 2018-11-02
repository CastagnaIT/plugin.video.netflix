# -*- coding: utf-8 -*-
"""Parsing of Netflix Website"""
from __future__ import unicode_literals

import json
from re import compile as recompile, DOTALL

import resources.lib.common as common

PAGE_ITEMS = [
    'gpsModel',
    'models/userInfo/data/authURL',
    'models/userInfo/data/guid',
    'models/userInfo/data/countryOfSignup',
    'models/userInfo/data/membershipStatus',
    'models/serverDefs/data/BUILD_IDENTIFIER',
    'models/serverDefs/data/ICHNAEA_ROOT',
    'models/serverDefs/data/API_ROOT',
    'models/serverDefs/data/API_BASE_URL',
    'models/esnGeneratorModel/data/esn'
]

JSON_REGEX = r'netflix\.%s\s*=\s*(.*?);\s*</script>'
AVATAR_SUBPATH = ['images', 'byWidth', '320', 'value']


class InvalidAuthURLError(Exception):
    """The authURL is invalid"""
    pass


class InvalidProfilesError(Exception):
    """Cannot extract profiles from Netflix webpage"""
    pass


class InvalidMembershipStatusError(Exception):
    """The user logging in does not have a valid subscription"""
    pass


def extract_session_data(content):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    profiles = extract_profiles(content)
    user_data = extract_userdata(content)
    esn = generate_esn(user_data)
    api_data = {
        api_item: user_data[api_item]
        for api_item in (
            item.split('/')[-1]
            for item in PAGE_ITEMS
            if 'serverDefs' in item)}
    if user_data.get('membershipStatus') != 'CURRENT_MEMBER':
        raise InvalidMembershipStatusError(user_data.get('membershipStatus'))
    return {
        'profiles': profiles,
        'user_data': user_data,
        'esn': esn,
        'api_data': api_data
    }


def extract_profiles(content):
    """Extract profile information from Netflix website"""
    profiles = {}

    try:
        falkor_cache = extract_json(content, 'falcorCache')
        for guid, profile in falkor_cache.get('profiles', {}).iteritems():
            common.debug('Parsing profile {}'.format(guid))
            _profile = profile['summary']['value']
            _profile['avatar'] = _get_avatar(falkor_cache, profile)
            profiles.update({guid: _profile})
    except Exception as exc:
        common.error('Cannot parse profiles from webpage: {exc}', exc)
        raise InvalidProfilesError()

    return profiles


def _get_avatar(falkor_cache, profile):
    try:
        profile['avatar']['value'].extend(AVATAR_SUBPATH)
        return common.get_path(profile['avatar']['value'], falkor_cache)
    except KeyError:
        common.warn('Cannot find avatar for profile {guid}'
                    .format(guid=profile['summary']['value']['guid']))
    return ''


def extract_userdata(content):
    """Extract essential userdata from the reactContext of the webpage"""
    common.debug('Extracting userdata from webpage')
    user_data = {'gpsModel': 'harris'}
    react_context = extract_json(content, 'reactContext')
    for path in ([path_item for path_item in path.split('/')]
                 for path in PAGE_ITEMS):
        try:
            user_data.update({path[-1]: common.get_path(path, react_context)})
            common.debug('Extracted {}'.format(path))
        except (AttributeError, KeyError):
            common.debug('Could not extract {}'.format(path))

    return assert_valid_auth_url(user_data)


def assert_valid_auth_url(user_data):
    """Raise an exception if user_data does not contain a valid authURL"""
    if len(user_data.get('authURL', '')) != 42:
        raise InvalidAuthURLError('authURL is invalid')
    return user_data


def generate_esn(user_data):
    """Generate an ESN if on android or return the one from user_data"""
    import subprocess
    try:
        manufacturer = subprocess.check_output(
            ['/system/bin/getprop', 'ro.product.manufacturer'])
        if manufacturer:
            esn = ['NFANDROID1-PRV-']
            inp = subprocess.check_output(
                ['/system/bin/getprop', 'ro.nrdp.modelgroup'])
            if inp:
                esn.append(inp.strip(' \t\n\r'))
                esn.append('-')
            else:
                esn.append('T-L3-')
            esn.append('{:5}'.format(manufacturer.strip(' \t\n\r').upper()))
            inp = subprocess.check_output(
                ['/system/bin/getprop', 'ro.product.model'])
            esn.append(inp.strip(' \t\n\r').replace(' ', '=').upper())
            esn = ''.join(esn)
            common.log('Android generated ESN:' + esn)
            return esn
    except OSError:
        pass

    return user_data.get('esn', '')


def extract_json(content, name):
    """Extract json from netflix content page"""
    common.debug('Extracting {} JSON'.format(name))
    json_array = recompile(JSON_REGEX % name, DOTALL).findall(content)
    if not json_array:
        return {}  # Return an empty dict if json not found !
    json_str = json_array[0]
    json_str = json_str.replace('\"', '\\"')  # Escape double-quotes
    json_str = json_str.replace('\\s', '\\\\s')  # Escape \s
    json_str = json_str.decode('unicode_escape')  # finally decoding...
    return json.loads(json_str)
