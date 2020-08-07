# Copyright (c) 2014, 2018, Oracle and/or its affiliates. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2.0, as
# published by the Free Software Foundation.
#
# This program is also distributed with certain software (including
# but not limited to OpenSSL) that is licensed under separate terms,
# as designated in a particular file or component or in included license
# documentation.  The authors of MySQL hereby grant you an
# additional permission to link the program and your derivative works
# with the separately licensed software that they have included with
# MySQL.
#
# Without limiting anything contained in the foregoing, this file,
# which is part of MySQL Connector/Python, is also subject to the
# Universal FOSS Exception, version 1.0, a copy of which can be found at
# http://oss.oracle.com/licenses/universal-foss-exception.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License, version 2.0, for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA

"""Python v2 to v3 migration module"""

from decimal import Decimal
import struct
import sys

from .custom_types import HexLiteral

# pylint: disable=E0602,E1103

PY2 = sys.version_info[0] == 2

if PY2:
    NUMERIC_TYPES = (int, float, Decimal, HexLiteral, long)
    INT_TYPES = (int, long)
    UNICODE_TYPES = (unicode,)
    STRING_TYPES = (str, unicode)
    BYTE_TYPES = (bytearray,)
else:
    NUMERIC_TYPES = (int, float, Decimal, HexLiteral)
    INT_TYPES = (int,)
    UNICODE_TYPES = (str,)
    STRING_TYPES = (str,)
    BYTE_TYPES = (bytearray, bytes)


def init_bytearray(payload=b'', encoding='utf-8'):
    """Initializes a bytearray from the payload"""
    if isinstance(payload, bytearray):
        return payload

    if PY2:
        return bytearray(payload)

    if isinstance(payload, int):
        return bytearray(payload)
    elif not isinstance(payload, bytes):
        try:
            return bytearray(payload.encode(encoding=encoding))
        except AttributeError:
            raise ValueError("payload must be a str or bytes")

    return bytearray(payload)


def isstr(obj):
    """Returns whether a variable is a string"""
    if PY2:
        return isinstance(obj, basestring)
    return isinstance(obj, str)

def isunicode(obj):
    """Returns whether a variable is a of unicode type"""
    if PY2:
        return isinstance(obj, unicode)
    return isinstance(obj, str)


if PY2:
    def struct_unpack(fmt, buf):
        """Wrapper around struct.unpack handling buffer as bytes and strings"""
        if isinstance(buf, (bytearray, bytes)):
            return struct.unpack_from(fmt, buffer(buf))
        return struct.unpack_from(fmt, buf)
else:
    struct_unpack = struct.unpack  # pylint: disable=C0103


def make_abc(base_class):
    """Decorator used to create a abstract base class

    We use this decorator to create abstract base classes instead of
    using the abc-module. The decorator makes it possible to do the
    same in both Python v2 and v3 code.
    """
    def wrapper(class_):
        """Wrapper"""
        attrs = class_.__dict__.copy()
        for attr in '__dict__', '__weakref__':
            attrs.pop(attr, None)  # ignore missing attributes

        bases = class_.__bases__
        if PY2:
            attrs['__metaclass__'] = class_
        else:
            bases = (class_,) + bases
        return base_class(class_.__name__, bases, attrs)
    return wrapper
