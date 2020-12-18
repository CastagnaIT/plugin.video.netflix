# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Common interface for all types of databases

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""


class BaseDatabase:
    """
    Base class to handle various types of databases
    """
    def __init__(self):
        self.conn = None
        self._initialize_connection()

    def _initialize_connection(self):
        """
        Checks database existence and performs first connection tests
        """
        raise NotImplementedError

    def _execute_non_query(self, query, params=None, cursor=None, **kwargs):
        """
        Execute a query without returning a value
        :param query: sql query
        :param params: tuple of values
        :param cursor: a cursor, if None get a instance of standard cursor
        """
        raise NotImplementedError

    def _execute_query(self, query, params=None, cursor=None):
        """
        Execute a query returning a value
        :param query: sql query
        :param params: tuple of values
        :param cursor: a cursor, if None get a instance of standard cursor
        :return: query result
        """
        raise NotImplementedError

    def get_cursor(self):
        """
        Get an instance of standard cursor
        :return: cursor
        """
        raise NotImplementedError

    def get_cursor_for_dict_results(self):
        """
        Get an instance of cursor to obtain results as a dictionary
        :return: cursor
        """
        raise NotImplementedError

    def get_cursor_for_list_results(self):
        """
        Get an instance of cursor to obtain results as a list,
        to use in conjunction with: return_rows_as_list
        :return: cursor
        """
        raise NotImplementedError

    def return_rows_as_list(self, conn_cursor):
        """
        Convert rows to a list when necessary (MySql)
        :return: list
        """
        raise NotImplementedError
