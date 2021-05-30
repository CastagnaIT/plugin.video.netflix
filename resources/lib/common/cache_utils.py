# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for cache

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import pickle
from functools import wraps

from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .exceptions import CacheMiss

# Cache buckets (the default_ttl is the variable name in 'global' class)
CACHE_COMMON = {'name': 'cache_common', 'is_persistent': False, 'default_ttl': 'CACHE_TTL'}
CACHE_GENRES = {'name': 'cache_genres', 'is_persistent': False, 'default_ttl': 'CACHE_TTL'}
CACHE_SUPPLEMENTAL = {'name': 'cache_supplemental', 'is_persistent': False, 'default_ttl': 'CACHE_TTL'}
CACHE_METADATA = {'name': 'cache_metadata', 'is_persistent': True, 'default_ttl': 'CACHE_METADATA_TTL'}
CACHE_INFOLABELS = {'name': 'cache_infolabels', 'is_persistent': True, 'default_ttl': 'CACHE_METADATA_TTL'}
CACHE_ARTINFO = {'name': 'cache_artinfo', 'is_persistent': True, 'default_ttl': 'CACHE_METADATA_TTL'}
CACHE_MANIFESTS = {'name': 'cache_manifests', 'is_persistent': False, 'default_ttl': 'CACHE_TTL'}
CACHE_BOOKMARKS = {'name': 'cache_bookmarks', 'is_persistent': False, 'default_ttl': 'CACHE_TTL'}
CACHE_MYLIST = {'name': 'cache_mylist', 'is_persistent': False, 'default_ttl': 'CACHE_MYLIST_TTL'}
CACHE_SEARCH = {'name': 'cache_search', 'is_persistent': False, 'default_ttl': ''}  # Only customized ttl

# The complete list of buckets (to obtain the list quickly)
BUCKET_NAMES = ['cache_common', 'cache_genres', 'cache_supplemental', 'cache_metadata', 'cache_infolabels',
                'cache_artinfo', 'cache_manifests', 'cache_bookmarks', 'cache_mylist', 'cache_search']

BUCKETS = [CACHE_COMMON, CACHE_GENRES, CACHE_SUPPLEMENTAL, CACHE_METADATA, CACHE_INFOLABELS,
           CACHE_ARTINFO, CACHE_MANIFESTS, CACHE_BOOKMARKS, CACHE_MYLIST, CACHE_SEARCH]


# Logic to get the identifier
# cache_output: called without params, use the first argument value of the function as identifier
# cache_output: with identify_from_kwarg_name, get value identifier from kwarg name specified,
#               if None value fallback to first function argument value

# identify_append_from_kwarg_name - if specified append the value after the kwarg identify_from
#                                  _kwarg_name, to creates a more specific identifier
# identify_fallback_arg_index - to change the default fallback arg index (0), where the identifier
#                               get the value from the func arguments
# fixed_identifier - note if specified all other params are ignored

def cache_output(bucket, fixed_identifier=None,
                 identify_from_kwarg_name='videoid',
                 identify_append_from_kwarg_name=None,
                 identify_fallback_arg_index=0,
                 ttl=None,
                 ignore_self_class=False):
    """Decorator that ensures caching the output of a function"""
    def caching_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # To avoid use cache add to the kwargs the value: 'no_use_cache'=True
            arg_value, identifier = _get_identifier(fixed_identifier,
                                                    identify_from_kwarg_name,
                                                    identify_append_from_kwarg_name,
                                                    identify_fallback_arg_index,
                                                    args[1:] if ignore_self_class else args,
                                                    kwargs)
            if not identifier:
                # Do not cache if identifier couldn't be determined
                return func(*args, **kwargs)
            _bucket = CACHE_MYLIST if arg_value == 'mylist' else bucket
            try:
                return G.CACHE.get(_bucket, identifier)
            except CacheMiss:
                output = func(*args, **kwargs)
                G.CACHE.add(_bucket, identifier, output, ttl=ttl)
                return output
        return wrapper
    return caching_decorator


def _get_identifier(fixed_identifier, identify_from_kwarg_name,
                    identify_append_from_kwarg_name, identify_fallback_arg_index, args, kwargs):
    """Return the identifier to use with the caching_decorator"""
    # LOG.debug('Get_identifier args: {}', args)
    # LOG.debug('Get_identifier kwargs: {}', kwargs)
    if kwargs.pop('no_use_cache', False):
        return None, None
    arg_value = None
    if fixed_identifier:
        identifier = fixed_identifier
        if identify_append_from_kwarg_name and kwargs.get(identify_append_from_kwarg_name):
            identifier += f'_{kwargs.get(identify_append_from_kwarg_name)}'
    else:
        identifier = str(kwargs.get(identify_from_kwarg_name) or '')
        if not identifier and args:
            arg_value = str(args[identify_fallback_arg_index] or '')
            identifier = arg_value
        if identifier and identify_append_from_kwarg_name and kwargs.get(identify_append_from_kwarg_name):
            identifier += f'_{kwargs.get(identify_append_from_kwarg_name)}'
    # LOG.debug('Get_identifier identifier value: {}', identifier if identifier else 'None')
    return arg_value, identifier


def serialize_data(value):
    return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)


def deserialize_data(value):
    try:
        return pickle.loads(value)
    except pickle.UnpicklingError as exc:
        LOG.error('It was not possible to deserialize the cache data, try purge cache from expert settings menu')
        raise CacheMiss from exc
