# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Common exception types for database operations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals


class SQLiteConnectionError(Exception):
    """An error occurred in the database connection"""


class SQLiteError(Exception):
    """An error occurred in the database operations"""


class MySQLConnectionError(Exception):
    """An error occurred in the database connection"""


class MySQLError(Exception):
    """An error occurred in the database operations"""


class ProfilesMissing(Exception):
    """There are no stored profiles in database"""
