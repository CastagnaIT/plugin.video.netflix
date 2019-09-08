# -*- coding: utf-8 -*-
"""Common exception types for database operations"""
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
