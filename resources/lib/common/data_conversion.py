# -*- coding: utf-8 -*-
"""Data type conversion"""
from __future__ import absolute_import, division, unicode_literals
import json
import datetime
from ast import literal_eval
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
        return literal_eval(value)
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
    return json.dumps(value, ensure_ascii=False)


def _conv_string_to_json(value):
    return json.loads(value)


def _conv_string_to_datetime(value):
    return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
