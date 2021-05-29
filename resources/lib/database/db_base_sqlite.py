# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Main functions for access to SQLite database

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import sqlite3 as sql
import threading
from functools import wraps

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_create_sqlite as db_create_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.common.exceptions import DBSQLiteConnectionError, DBSQLiteError
from resources.lib.utils.logging import LOG


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
                args[0].mutex.acquire()
                args[0].conn = sql.connect(args[0].db_file_path,
                                           isolation_level=CONN_ISOLATION_LEVEL)
                args[0].is_connected = True
                conn = args[0].conn

            return func(*args, **kwargs)
        except sql.Error as exc:
            LOG.error('SQLite error {}:', exc.args[0])
            raise DBSQLiteConnectionError from exc
        finally:
            if conn:
                args[0].is_connected = False
                conn.close()
                args[0].mutex.release()
    return wrapper


class SQLiteDatabase(db_base.BaseDatabase):
    def __init__(self, db_filename):  # pylint: disable=super-on-old-class
        self.mutex = threading.Lock()
        self.local_storage = threading.local()
        self.is_mysql_database = False
        self.db_filename = db_filename
        self.db_file_path = db_utils.get_local_db_path(db_filename)
        super().__init__()

    @property
    def is_connected(self):
        return getattr(self.local_storage, 'is_connected', False)

    @is_connected.setter
    def is_connected(self, val):
        self.local_storage.is_connected = val

    def _initialize_connection(self):
        try:
            LOG.debug('Trying connection to the database {}', self.db_filename)
            self.conn = sql.connect(self.db_file_path, check_same_thread=False)
            cur = self.conn.cursor()
            cur.execute(str('SELECT SQLITE_VERSION()'))
            LOG.debug('Database connection {} was successful (SQLite ver. {})',
                      self.db_filename, cur.fetchone()[0])
            cur.row_factory = lambda cursor, row: row[0]
            cur.execute(str('SELECT name FROM sqlite_master WHERE type=\'table\' '
                            'AND name NOT LIKE \'sqlite_%\''))
            list_tables = cur.fetchall()
            if not list_tables:
                # If no tables exist create a new one
                self.conn.close()
                db_create_sqlite.create_database(self.db_file_path, self.db_filename)
        except sql.Error as exc:
            LOG.error('SQLite error {}:', exc.args[0])
            raise DBSQLiteConnectionError from exc
        finally:
            if self.conn:
                self.conn.close()

    def _executemany_non_query(self, query, params, cursor=None):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            cursor.executemany(query, params)
        except sql.Error as exc:
            LOG.error('SQLite error {}:', exc.args[0])
            raise DBSQLiteError from exc
        except ValueError:
            LOG.error('Value {}', str(params))
            LOG.error('Value type {}', type(params))
            raise

    def _execute_non_query(self, query, params=None, cursor=None, **kwargs):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
        except sql.Error as exc:
            LOG.error('SQLite error {}:', exc.args[0])
            raise DBSQLiteError from exc
        except ValueError:
            LOG.error('Value {}', str(params))
            LOG.error('Value type {}', type(params))
            raise

    def _execute_query(self, query, params=None, cursor=None):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor
        except sql.Error as exc:
            LOG.error('SQLite error {}:', exc.args[0])
            raise DBSQLiteError from exc
        except ValueError:
            LOG.error('Value {}', str(params))
            LOG.error('Value type {}', type(params))
            raise

    def get_cursor(self):
        return self.conn.cursor()

    def get_cursor_for_dict_results(self):
        conn_cursor = self.conn.cursor()
        conn_cursor.row_factory = lambda c, r: dict(list(zip([col[0] for col in c.description], r)))
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
        query = f'SELECT {table_columns[1]} FROM {table_name} WHERE {table_columns[0]} = ?'
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
        query = f'SELECT {table_columns[1]} FROM {table_name} WHERE {table_columns[0]} = ?'
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
        update_query = f'UPDATE {table_name} SET {table_columns[1]} = ? WHERE {table_columns[0]} = ?'
        value = common.convert_to_string(value)
        cur = self._execute_query(update_query, (value, key))
        if cur.rowcount == 0:
            insert_query = f'INSERT INTO {table_name} ({table_columns[0]}, {table_columns[1]}) VALUES (?, ?)'
            self._execute_non_query(insert_query, (key, value))

    @handle_connection
    def set_values(self, dict_values, table=db_utils.TABLE_APP_CONF):
        """
        Store multiple values to database
        :param dict_values: The key/value to store
        :param table: Table map
        """
        table_name = table[0]
        table_columns = table[1]
        # Doing many sqlite operations at the same makes the performance much worse (especially on Kodi 18)
        # The use of 'executemany' and 'transaction' can improve performance up to about 75% !!
        if common.CmpVersion(sql.sqlite_version) < '3.24.0':
            query = f'INSERT OR REPLACE INTO {table_name} ({table_columns[0]}, {table_columns[1]}) VALUES (?, ?)'
            records_values = [(key, common.convert_to_string(value)) for key, value in dict_values.items()]
        else:
            # sqlite UPSERT clause exists only on sqlite >= 3.24.0
            query = (f'INSERT INTO {table_name} ({table_columns[0]}, {table_columns[1]}) VALUES (?, ?) '
                     f'ON CONFLICT({table_columns[0]}) DO UPDATE SET {table_columns[1]} = ? '
                     f'WHERE {table_columns[0]} = ?')
            records_values = []
            for key, value in dict_values.items():
                value_str = common.convert_to_string(value)
                records_values.append((key, value_str, value_str, key))
        cur = self.get_cursor()
        cur.execute("BEGIN TRANSACTION;")
        self._executemany_non_query(query, records_values, cur)
        cur.execute("COMMIT;")

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
        query = f'DELETE FROM {table_name} WHERE {table_columns[0]} = ?'
        cur = self._execute_query(query, (key,))
        return cur.rowcount

    def __del__(self):
        if self.conn:
            self.conn.close()
