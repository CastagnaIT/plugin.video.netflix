# -*- coding: utf-8 -*-
"""Common exception types for database operations"""
from __future__ import unicode_literals


class SQLiteConnectionError(Exception):
    """An error occurred in the database connection"""
    pass


class SQLiteError(Exception):
    """An error occurred in the database operations"""
    pass


class MySQLConnectionError(Exception):
    """An error occurred in the database connection"""
    pass


class MySQLError(Exception):
    """An error occurred in the database operations"""
    pass


class ProfilesMissing(Exception):
    """There are no stored profiles in database"""
    pass
