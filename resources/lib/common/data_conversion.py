# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Data type conversion

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import datetime
import json
from ast import literal_eval
from collections import OrderedDict

from resources.lib.utils.logging import LOG


class DataTypeNotMapped(Exception):
    """Data type not mapped"""


def convert_to_string(value):
    if value is None:
        return None
    data_type = type(value)
    if data_type == str:
        return value
    if data_type in (int, float, bool, tuple, datetime.datetime):
        converter = _conv_standard_to_string
    elif data_type in (list, dict, OrderedDict):
        converter = _conv_json_to_string
    else:
        LOG.error('convert_to_string: Data type {} not mapped', data_type)
        raise DataTypeNotMapped
    return converter(value)


def convert_from_string(value, to_data_type):
    if value is None:
        return None
    if to_data_type in (str, int, float):
        return to_data_type(value)
    if to_data_type in (bool, list, tuple):
        return literal_eval(value)
    if to_data_type == dict:
        converter = _conv_string_to_json
    elif to_data_type == datetime.datetime:
        converter = _conv_string_to_datetime
    else:
        LOG.error('convert_from_string: Data type {} not mapped', to_data_type)
        raise DataTypeNotMapped
    return converter(value)


def _conv_standard_to_string(value):
    return str(value)


def _conv_json_to_string(value):
    return json.dumps(value, ensure_ascii=False)


def _conv_string_to_json(value):
    return json.loads(value)


def _conv_string_to_datetime(value):
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
    except (TypeError, ImportError):
        # Python bug https://bugs.python.org/issue27400
        import time
        return datetime.datetime(*(time.strptime(value, '%Y-%m-%d %H:%M:%S.%f')[0:6]))
