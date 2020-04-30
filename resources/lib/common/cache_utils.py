# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Miscellaneous utility functions for cache

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps

import resources.lib.common as common
from resources.lib.api.exceptions import CacheMiss
from resources.lib.globals import g

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

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
                return g.CACHE.get(_bucket, identifier)
            except CacheMiss:
                output = func(*args, **kwargs)
                g.CACHE.add(_bucket, identifier, output, ttl=ttl)
                return output
        return wrapper
    return caching_decorator


def _get_identifier(fixed_identifier, identify_from_kwarg_name,
                    identify_append_from_kwarg_name, identify_fallback_arg_index, args, kwargs):
    """Return the identifier to use with the caching_decorator"""
    # common.debug('Get_identifier args: {}', args)
    # common.debug('Get_identifier kwargs: {}', kwargs)
    arg_value = None
    if fixed_identifier:
        identifier = fixed_identifier
    else:
        identifier = unicode(kwargs.get(identify_from_kwarg_name) or '')
        if not identifier and args:
            arg_value = unicode(args[identify_fallback_arg_index] or '')
            identifier = arg_value
        if identifier and identify_append_from_kwarg_name and kwargs.get(identify_append_from_kwarg_name):
            identifier += '_' + unicode(kwargs.get(identify_append_from_kwarg_name))
    # common.debug('Get_identifier identifier value: {}', identifier if identifier else 'None')
    return arg_value, identifier


def serialize_data(value):
    if g.PY_IS_VER2:
        # On python 2 pickle.dumps produces str
        # Pickle on python 2 use non-standard byte-string seem not possible convert it in to byte in a easy way
        # then serialize it with base64
        from base64 import standard_b64encode
        return standard_b64encode(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
    # On python 3 pickle.dumps produces byte
    return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)


def deserialize_data(value):
    try:
        if g.PY_IS_VER2:
            # On python 2 pickle.loads wants str
            from base64 import standard_b64decode
            return pickle.loads(standard_b64decode(value))
        # On python 3 pickle.loads wants byte
        return pickle.loads(value)
    except (pickle.UnpicklingError, TypeError, EOFError):
        # TypeError/EOFError happen when standard_b64decode fails
        # This should happen only if manually mixing the database data
        common.error('It was not possible to deserialize the cache data, try purge cache from expert settings menu')
        raise CacheMiss()
