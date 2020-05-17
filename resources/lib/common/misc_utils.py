# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Miscellaneous utility functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
from future.utils import iteritems

try:  # Python 2
    from itertools import imap as map  # pylint: disable=redefined-builtin
except ImportError:
    pass

# try:  # Python 3
#     from io import StringIO
# except ImportError:  # Python 2
#     from StringIO import StringIO

try:  # Python 3
    from urllib.parse import quote, urlencode
except ImportError:  # Python 2
    from urllib import urlencode
    from urllib2 import quote

from resources.lib.globals import g


def find(value_to_find, attribute, search_space):
    """Find a video with matching id in a dict or list"""
    for video in search_space:
        if video[attribute] == value_to_find:
            return video
    raise KeyError('Metadata for {} does not exist'.format(value_to_find))


def find_episode_metadata(videoid, metadata):
    """Find metadata for a specific episode within a show metadata dict"""
    season = find(int(videoid.seasonid), 'id', metadata['seasons'])
    return (find(int(videoid.episodeid), 'id', season.get('episodes', {})),
            season)


def get_class_methods(class_item=None):
    """
    Returns the class methods of agiven class object

    :param class_item: Class item to introspect
    :type class_item: object
    :returns: list -- Class methods
    """
    from types import FunctionType
    _type = FunctionType
    return [x for x, y in iteritems(class_item.__dict__)
            if isinstance(y, _type)]


def build_url(pathitems=None, videoid=None, params=None, mode=None):
    """Build a plugin URL from pathitems and query parameters. Add videoid to the path if it's present."""
    if not (pathitems or videoid):
        raise ValueError('Either pathitems or videoid must be set.')
    path = '{netloc}/{path}/{qs}'.format(
        netloc=g.BASE_URL,
        path=_encode_path(mode, pathitems, videoid),
        qs=_encode_params(params))
    return path


def _expand_mode(mode):
    return [mode] if mode else []


def _expand_videoid(videoid):
    return videoid.to_path() if videoid else []


def _encode_path(mode, pathitems, videoid):
    return quote(
        '/'.join(_expand_mode(mode) +
                 (pathitems or []) +
                 _expand_videoid(videoid)).encode('utf-8'))


def _encode_params(params):
    return ('?' + urlencode(params)) if params else ''


def is_numeric(string):
    """Return true if string represents an integer, else false"""
    try:
        int(string)
    except ValueError:
        return False
    return True


def strp(value, form):
    """
    Helper function to safely create datetime objects from strings

    :return: datetime - parsed datetime object
    """
    # pylint: disable=broad-except
    from datetime import datetime
    def_value = datetime.utcfromtimestamp(0)
    try:
        return datetime.strptime(value, form)
    except TypeError:
        # Python bug https://bugs.python.org/issue27400
        try:
            from time import strptime
            return datetime(*(strptime(value, form)[0:6]))
        except ValueError:
            return def_value
    except Exception:
        return def_value


def strf_timestamp(timestamp, form):
    """
    Helper function to safely create string date time from a timestamp value

    :return: string - date time in the specified form
    """
    from datetime import datetime
    try:
        return datetime.utcfromtimestamp(timestamp).strftime(form)
    except Exception:  # pylint: disable=broad-except
        return ''


# def compress_data(data):
#    """GZIP and b64 encode data"""
#    out = StringIO()
#    with gzip.GzipFile(fileobj=out, mode='w') as outh:
#        outh.write(data)
#    return base64.standard_b64encode(out.getvalue())


def merge_dicts(dict_to_merge, merged_dict):
    """Recursively merge the contents of dict_to_merge into merged_dict.
    Values that are already present in merged_dict will be overwritten if they are also present in dict_to_merge"""
    for key, value in iteritems(dict_to_merge):
        if isinstance(merged_dict.get(key), dict):
            merge_dicts(value, merged_dict[key])
        else:
            merged_dict[key] = value
    return merged_dict


def compare_dicts(dict_a, dict_b, excluded_keys=None):
    """Compare two dict with same keys, with optional keys to exclude from compare"""
    if excluded_keys is None:
        excluded_keys = []
    return all(dict_a[k] == dict_b[k] for k in dict_a if k not in excluded_keys)


def chunked_list(seq, chunk_len):
    for start in range(0, len(seq), chunk_len):
        yield seq[start:start + chunk_len]


def any_value_except(mapping, excluded_keys):
    """Return a random value from a dict that is not associated with excluded_key.
    Raises StopIteration if there are no other keys than excluded_key"""
    return next(mapping[key] for key in mapping if key not in excluded_keys)


def enclose_quotes(content):
    return '"' + content + '"'


def is_edge_esn(esn):
    """Return True if the esn is an EDGE esn"""
    return esn.startswith('NFCDIE-02-')


def is_minimum_version(version, min_version):
    """Return True if version is equal or greater to min_version"""
    return list(map(int, version.split('.'))) >= list(map(int, min_version.split('.')))


def is_less_version(version, max_version):
    """Return True if version is less to max_version"""
    return list(map(int, version.split('.'))) < list(map(int, max_version.split('.')))


def make_list(arg):
    """Return a list with arg as its member or arg if arg is already a list. Returns an empty list if arg is None"""
    return (arg
            if isinstance(arg, list)
            else ([arg]
                  if arg is not None
                  else []))


def convert_seconds_to_hms_str(time):
    h = int(time // 3600)
    time %= 3600
    m = int(time // 60)
    s = int(time % 60)
    return '{:02d}:{:02d}:{:02d}'.format(h, m, s)


def remove_html_tags(raw_html):
    import re
    pattern = re.compile('<.*?>')
    return re.sub(pattern, '', raw_html)


def censure(value, length=3):
    """Censor part of the string with asterisks"""
    if not value:
        return value
    return value[:-length] + '*' * length


def run_threaded(non_blocking, target_func, *args, **kwargs):
    """Call a function in a thread, when specified"""
    if not non_blocking:
        return target_func(*args, **kwargs)
    from threading import Thread
    Thread(target=target_func, args=args, kwargs=kwargs).start()
    return None
