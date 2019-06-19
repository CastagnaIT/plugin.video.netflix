# -*- coding: utf-8 -*-
"""Parsing of Netflix Website"""
from __future__ import unicode_literals

import json
import traceback
from re import compile as recompile, DOTALL, sub
from collections import OrderedDict

import resources.lib.common as common

from resources.lib.globals import g
from .paths import resolve_refs
from .exceptions import (InvalidProfilesError, InvalidAuthURLError,
                         InvalidMembershipStatusError, WebsiteParsingError)

PAGE_ITEMS = [
    'models/userInfo/data/authURL',
    'models/userInfo/data/guid',
    'models/userInfo/data/countryOfSignup',
    'models/userInfo/data/membershipStatus',
    'models/serverDefs/data/BUILD_IDENTIFIER',
    'models/serverDefs/data/ICHNAEA_ROOT',
    'models/serverDefs/data/API_ROOT',
    'models/playerModel/data/config/ui/initParams/apiUrl',
    'models/esnGeneratorModel/data/esn',
    'models/memberContext/data/geo/preferredLocale'
]

JSON_REGEX = r'netflix\.%s\s*=\s*(.*?);\s*</script>'
AVATAR_SUBPATH = ['images', 'byWidth', '320', 'value']


@common.time_execution(immediate=True)
def extract_session_data(content):
    """
    Call all the parsers we need to extract all
    the session relevant data from the HTML page
    """
    common.debug('Extracting session data...')
    profiles, active_profile = extract_profiles(
        extract_json(content, 'falcorCache'))
    user_data = extract_userdata(content)

    if user_data.get('preferredLocale'):
        g.PERSISTENT_STORAGE['locale_id'] = user_data.get('preferredLocale').get('id','en-US')

    if user_data.get('membershipStatus') != 'CURRENT_MEMBER':
        common.debug(user_data)
        # Ignore this for now
        # raise InvalidMembershipStatusError(user_data.get('membershipStatus'))
    return {
        'profiles': profiles,
        'active_profile': active_profile,
        'user_data': user_data,
        'esn': generate_esn(user_data),
        'api_data': _parse_api_data(user_data)
    }


@common.time_execution(immediate=True)
def extract_profiles(falkor_cache):
    """Extract profile information from Netflix website"""
    profiles = {}
    active_profile = None
    try:
        profiles_list = OrderedDict(resolve_refs(falkor_cache['profilesList'], falkor_cache))
        for guid, profile in profiles_list.items():
            common.debug('Parsing profile {}'.format(guid))
            avatar_url = _get_avatar(falkor_cache, profile)
            profile = profile['summary']['value']
            profile['avatar'] = avatar_url
            if profile.get('isActive'):
                active_profile = guid
            profiles[list(profiles_list.keys()).index(guid)] = (guid, profile)
    except Exception:
        common.error(traceback.format_exc())
        common.error('Falkor cache: {}'.format(falkor_cache))
        raise InvalidProfilesError

    return profiles, active_profile


def _get_avatar(falkor_cache, profile):
    try:
        profile['avatar']['value'].extend(AVATAR_SUBPATH)
        return common.get_path(profile['avatar']['value'], falkor_cache)
    except KeyError:
        common.warn('Cannot find avatar for profile {guid}'
                    .format(guid=profile['summary']['value']['guid']))
    return ''


@common.time_execution(immediate=True)
def extract_userdata(content):
    """Extract essential userdata from the reactContext of the webpage"""
    common.debug('Extracting userdata from webpage')
    user_data = {}
    react_context = extract_json(content, 'reactContext')
    for path in ([path_item for path_item in path.split('/')]
                 for path in PAGE_ITEMS):
        try:
            user_data.update({path[-1]: common.get_path(path, react_context)})
            common.debug('Extracted {}'.format(path))
        except (AttributeError, KeyError):
            common.debug('Could not extract {}'.format(path))

    return assert_valid_auth_url(user_data)


def _parse_api_data(user_data):
    return {api_item: user_data[api_item]
            for api_item in (
                item.split('/')[-1]
                for item in PAGE_ITEMS
                if ('serverDefs' in item) or ('initParams/apiUrl' in item))}


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
