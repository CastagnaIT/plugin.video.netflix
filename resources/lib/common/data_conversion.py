# -*- coding: utf-8 -*-
"""Data type conversion"""
from __future__ import absolute_import, division, unicode_literals
from .logging import error

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin

try:  # Python 2
    basestring
except NameError:  # Python 3
    basestring = str  # pylint: disable=redefined-builtin


class DataTypeNotMapped(Exception):
    """Data type not mapped"""


def convert_to_string(value):
    if value is None:
        return None
    data_type = type(value)
    if data_type in (str, unicode):
        return value
    import datetime
    converter = None
    if data_type in (int, float, bool, tuple, datetime.datetime):
        converter = _conv_standard_to_string
    if data_type in (list, dict):
        converter = _conv_json_to_string
    if not converter:
        error('convert_to_string: Data type {} not mapped'.format(data_type))
        raise DataTypeNotMapped
    return converter(value)


def convert_from_string(value, to_data_type):
    if value is None:
        return None
    if to_data_type in (str, unicode, int, float):
        return to_data_type(value)
    if to_data_type in (bool, list, tuple):
        from ast import literal_eval
        return literal_eval(value)
    import datetime
    converter = None
    if to_data_type == dict:
        converter = _conv_string_to_json
    if to_data_type == datetime.datetime:
        converter = _conv_string_to_datetime
    if not converter:
        error('convert_from_string: Data type {} not mapped'.format(to_data_type))
        raise DataTypeNotMapped
    return converter(value)


def _conv_standard_to_string(value):
    return str(value)


def _conv_json_to_string(value):
    from json import dumps
    return dumps(value, ensure_ascii=False)


def _conv_string_to_json(value):
    from json import loads
    return loads(value)


def _conv_string_to_datetime(value):
    import datetime
    import time
    # Workaround for http://bugs.python.org/issue8098 only to py2 caused by _conv_string_to_datetime()
    # Error: ImportError: Failed to import _strptime because the import lockis held by another thread.
    import _strptime  # pylint: disable=unused-import
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
    except TypeError:
        # Python bug https://bugs.python.org/issue27400
        return datetime.datetime(*(time.strptime(value, '%Y-%m-%d %H:%M:%S.%f')[0:6]))
