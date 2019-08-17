# -*- coding: utf-8 -*-
"""SQLite database"""
from __future__ import unicode_literals

import os
import sqlite3 as sql
from functools import wraps

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_create_sqlite as db_create_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.database.db_exceptions import (SQLiteConnectionError, SQLiteError)

CONN_ISOLATION_LEVEL = None  # Autocommit mode

# ---------------------------------------------------------------------------
# Pay attention with the SQLite syntax:
# SQLite is case sensitive
# Also wrong upper/lower case of columns and tables name cause errors
# LIKE comparator use ASCII, the unicode chars are not comparable
# ---------------------------------------------------------------------------


def handle_connection(func):
    """
    A decorator that handle the connection status with the database
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if args[0].is_mysql_database:
            # If database is mysql pass to next decorator
            return func(*args, **kwargs)
        conn = None
        try:
            if not args[0].is_connected:
                args[0].conn = sql.connect(args[0].db_file_path,
                                           isolation_level=CONN_ISOLATION_LEVEL)
                args[0].is_connected = True
                conn = args[0].conn
            return func(*args, **kwargs)
        except sql.Error as e:
            common.error("SQLite error {}:".format(e.args[0]))
            raise SQLiteConnectionError
        finally:
            if conn:
                conn.close()
                args[0].is_connected = False
    return wrapper


class SQLiteDatabase(db_base.BaseDatabase):
    def __init__(self, db_filename):
        self.is_mysql_database = False
        self.db_file_path = db_utils.get_local_db_path(db_filename)
        super(SQLiteDatabase, self).__init__()

    def _initialize_connection(self):
        # If database file do not exist create a new one
        # if not common.file_exists(db_filename, g.DATA_PATH):
        #     db_utils.create_database(self.db_file_path)
        # TODO: Temporary when stabilized it will be possible to implement the db code creation
        # If database file do not exist copy a new one
        db_filename = os.path.basename(self.db_file_path)
        db_create_sqlite.check_database_file(db_filename)
        try:
            common.debug('Trying connection to the database {}'.format(db_filename))
            self.conn = sql.connect(self.db_file_path)
            cur = self.conn.cursor()
            cur.execute('SELECT SQLITE_VERSION()')
            common.debug('Database connection {} was successful (SQLite ver. {})'
                         .format(db_filename, cur.fetchone()[0]))
        except sql.Error as e:
            common.error("SQLite error {}:".format(e.args[0]))
            raise SQLiteConnectionError
        finally:
            if self.conn:
                self.conn.close()

    def _execute_non_query(self, query, params=None, cursor=None):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
        except sql.Error as e:
            common.error("SQLite error {}:".format(e.args[0]))
            raise SQLiteError
        except ValueError as exc_ve:
            common.error('Value {}'.format(str(params)))
            common.error('Value type {}'.format(type(params)))
            raise exc_ve

    def _execute_query(self, query, params=None, cursor=None):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor
        except sql.Error as e:
            common.error("SQLite error {}:".format(e.args[0]))
            raise SQLiteError
        except ValueError as exc_ve:
            common.error('Value {}'.format(str(params)))
            common.error('Value type {}'.format(type(params)))
            raise exc_ve

    def get_cursor(self):
        return self.conn.cursor()

    def get_cursor_for_dict_results(self):
        conn_cursor = self.conn.cursor()
        conn_cursor.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
        return conn_cursor

    def get_cursor_for_list_results(self):
        conn_cursor = self.conn.cursor()
        conn_cursor.row_factory = lambda cursor, row: row[0]
        return conn_cursor

    def return_rows_as_list(self, conn_cursor):
        # See note in the MySqlDatabase class on same method
        return conn_cursor.fetchall()

    @handle_connection
    def get_value(self, key, default_value=None, table=db_utils.TABLE_APP_CONF, data_type=None):
        """
        Get a single value from database
        :param key: The key to get the value
        :param default_value: When key do not exist return this default value
        :param table: Table map
        :param data_type: OPTIONAL Used to set data type conversion only when default_value is None
        :return: The value, with data type of default_value or if none, of data_type specified
        """
        table_name = table[0]
        table_columns = table[1]
        query = 'SELECT {} FROM {} WHERE {} = ?'.format(table_columns[1],
                                                        table_name,
                                                        table_columns[0])
        cur = self._execute_query(query, (key,))
        result = cur.fetchone()
        if default_value is not None:
            data_type = type(default_value)
        elif data_type is None:
            data_type = str
        return common.convert_from_string(result[0], data_type) \
            if result is not None else default_value

    @handle_connection
    def get_values(self, key, default_value=None, table=db_utils.TABLE_APP_CONF):
        """
        Get multiple values from database - WARNING return row objects
        :param key: The key to get the values
        :param default_value: When key do not exist return this default value
        :param table: Table map
        :return: rows
        """
        table_name = table[0]
        table_columns = table[1]
        query = 'SELECT {} FROM {} WHERE {} = ?'.format(table_columns[1],
                                                        table_name,
                                                        table_columns[0])
        cur = self._execute_query(query, (key,))
        result = cur.fetchall()
        return result if result is not None else default_value

    @handle_connection
    def set_value(self, key, value, table=db_utils.TABLE_APP_CONF):
        """
        Store a single value to database
        :param key: The key to store the value
        :param value: Value to save
        :param table: Table map
        """
        table_name = table[0]
        table_columns = table[1]
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        update_query = 'UPDATE {} SET {} = ? WHERE {} = ?'.format(table_name,
                                                                  table_columns[1],
                                                                  table_columns[0])
        value = common.convert_to_string(value)
        cur = self._execute_query(update_query, (value, key))
        if cur.rowcount == 0:
            insert_query = 'INSERT INTO {} ({}, {}) VALUES (?, ?)'\
                .format(table_name, table_columns[0], table_columns[1])
            self._execute_non_query(insert_query, (key, value))

    @handle_connection
    def delete_key(self, key, table=db_utils.TABLE_APP_CONF):
        """
        Delete a key record from database
        :param key: The key to delete
        :param table: Table map
        :return: Number of deleted entries
        """
        table_name = table[0]
        table_columns = table[1]
        query = 'DELETE FROM {} WHERE {} = ?'.format(table_name, table_columns[0])
        cur = self._execute_query(query, (key,))
        return cur.rowcount

    def __del__(self):
        if self.conn:
            self.conn.close()
