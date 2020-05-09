# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo - @CastagnaIT (original implementation module)
    Netflix API endpoints

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""

# Secure Netflix url
BASE_URL = 'https://www.netflix.com'

# List of all static endpoints for HTML/JSON POST/GET requests

# is_api_call:
#   specify which address to use for the endpoint
#   True  -> The https address used is composed with 'apiUrl' value from reactContext data
#   False -> The https address used is composed with the BASE_URL

# use_default_params:
#   Add to the request the default parameters (see _prepare_request_properties)

# add_auth_url:
#   Specifies if and where to put the 'authURL' value
#   None        -> Will not be added
#   'to_data'   -> It will be added with the data to send
#   'to_params' -> It will be added to the request parameters

# content_type:
#   If required add the Content-Type attribute to request header

# accept:
#   If required add the Accept attribute to request header (if not specified use '*/*')

ENDPOINTS = {
    'login':
        {'address': '/login',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         # By default to login Netflix use 'application/x-www-form-urlencoded' Content-Type,
         # instead we use 'application/json' for simplicity of data conversion
         # if in the future login raise InvalidMembershipStatusAnonymous can means that json is no more accepted
         'content_type': 'application/json',
         'accept': '*/*'},
    'logout':
        {'address': '/SignOut',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         'accept': '*/*'},
    'shakti':
        {'address': '/pathEvaluator',
         'is_api_call': True,
         'use_default_params': True,
         'add_auth_url': 'to_data',
         'content_type': 'application/x-www-form-urlencoded'},
    'browse':
        {'address': '/browse',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         'accept': '*/*'},
    'profiles_gate':
    # This endpoint is used after ending editing profiles page, i think to force close an active profile session
        {'address': '/ProfilesGate',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'accept': '*/*'},
    'profiles':
        {'address': '/profiles/manage',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         'accept': '*/*'},
    'switch_profile':
        {'address': '/SwitchProfile',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         'accept': '*/*'},
    'activate_profile':
        {'address': '/profiles/switch',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': None},
    'profile_lock':
        {'address': '/profileLock',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'profile_hub':
        {'address': '/profilehub',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'content_restrictions':
        {'address': '/contentRestrictions',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': None,
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'restrictions':
    # Page of content restrictions (former parental control)
        {'address': '/settings/restrictions/{}',  # At the end of the address will be appended the profile guid
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         'accept': '*/*'},
    'pin_reset':
        {'address': '/pin/reset',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': None},
    'pin_service':
        {'address': '/pin/service',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'metadata':
        {'address': '/metadata',
         'is_api_call': True,
         'use_default_params': True,
         'add_auth_url': 'to_params'},
    'set_video_rating':  # Old rating system
        {'address': '/setVideoRating',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'set_thumb_rating':
        {'address': '/setThumbRating',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'},
    'update_my_list':
        {'address': '/playlistop',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json',
         'accept': 'application/json, text/javascript, */*'}
    # Don't know what these could be used for. Keeping for reference
    # 'video_list_ids': {'address': '/preflight', 'is_api_call': True},
    # 'kids': {'address': '/Kids', 'is_api_call': False}
}
