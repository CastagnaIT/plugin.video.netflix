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
#   If required add the Content-Type property to request header

URLS = {
    'login':
        {'endpoint': '/login',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None,
         # By default to login Netflix use 'application/x-www-form-urlencoded' Content-Type,
         # instead we use 'application/json' for simplicity of data conversion
         # if in the future login raise InvalidMembershipStatusAnonymous can means that json is no more accepted
         'content_type': 'application/json'},
    'logout':
        {'endpoint': '/SignOut',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None},
    'shakti':
        {'endpoint': '/pathEvaluator',
         'is_api_call': True,
         'use_default_params': True,
         'add_auth_url': 'to_data',
         'content_type': 'application/x-www-form-urlencoded'},
    'browse':
        {'endpoint': '/browse',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None},
    'profiles':
        {'endpoint': '/profiles/manage',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None},
    'switch_profile':
        {'endpoint': '/SwitchProfile',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None},
    'activate_profile':
        {'endpoint': '/profiles/switch',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': None},
    'profile_lock':
        {'endpoint': '/profileLock',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json'},
    'pin':
        {'endpoint': '/pin',
         'is_api_call': False,
         'use_default_params': False,
         'add_auth_url': None},
    'pin_reset':
        {'endpoint': '/pin/reset',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': None},
    'pin_service':
        {'endpoint': '/pin/service',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json'},
    'metadata':
        {'endpoint': '/metadata',
         'is_api_call': True,
         'use_default_params': True,
         'add_auth_url': 'to_params'},
    'set_video_rating':  # Old rating system
        {'endpoint': '/setVideoRating',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json'},
    'set_thumb_rating':
        {'endpoint': '/setThumbRating',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json'},
    'update_my_list':
        {'endpoint': '/playlistop',
         'is_api_call': True,
         'use_default_params': False,
         'add_auth_url': 'to_data',
         'content_type': 'application/json'}
    # Don't know what these could be used for. Keeping for reference
    # 'video_list_ids': {'endpoint': '/preflight', 'is_api_call': True},
    # 'kids': {'endpoint': '/Kids', 'is_api_call': False}
}
