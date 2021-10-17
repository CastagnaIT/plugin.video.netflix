# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Main functions for access to MySQL database

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from functools import wraps

import mysql.connector

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_utils as db_utils
import resources.lib.database.db_create_mysql as db_create_mysql
from resources.lib.common.exceptions import DBMySQLConnectionError, DBMySQLError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


def handle_connection(func):
    """
    A decorator that handle the connection status with the database
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not args[0].is_mysql_database:
            # If database is not mysql pass to next decorator
            return func(*args, **kwargs)
        conn = None
        try:
            if not args[0].conn or (args[0].conn and not args[0].conn.is_connected()):
                args[0].conn = mysql.connector.connect(**args[0].config)
                conn = args[0].conn
            return func(*args, **kwargs)
        except mysql.connector.Error as exc:
            LOG.error('MySQL error {}:', exc)
            raise DBMySQLConnectionError from exc
        finally:
            if conn and conn.is_connected():
                conn.close()
    return wrapper


class MySQLDatabase(db_base.BaseDatabase):
    def __init__(self, test_config=None):  # pylint: disable=super-on-old-class
        self.is_mysql_database = True
        self.database = 'netflix_addon'
        if test_config:
            self.is_connection_test = True
            self.config = test_config
        else:
            self.is_connection_test = False
            self.config = {
                'user': G.ADDON.getSetting('mysql_username'),
                'password': G.ADDON.getSetting('mysql_password'),
                'host': G.ADDON.getSetting('mysql_host'),
                'port': G.ADDON.getSettingInt('mysql_port'),
                'database': 'netflix_addon',
                'autocommit': True,
                'charset': 'utf8',
                'use_unicode': True
            }
        super().__init__()

    def _initialize_connection(self):
        try:
            LOG.debug('Trying connection to the MySQL database {}', self.database)
            self.conn = mysql.connector.connect(**self.config)
            if self.conn.is_connected():
                db_info = self.conn.get_server_info()
                LOG.debug('MySQL database connection was successful (MySQL server ver. {})',
                          db_info)
        except mysql.connector.Error as exc:
            if exc.errno == 1049 and not self.is_connection_test:
                # Database does not exist, create a new one
                try:
                    db_create_mysql.create_database(self.config.copy())
                    self._initialize_connection()
                    return
                except mysql.connector.Error as e:
                    LOG.error('MySql error {}:', e)
                    if e.errno == 1115:  # Unknown character set: 'utf8mb4'
                        # Means an outdated MySQL/MariaDB version in use, needed MySQL => 5.5.3 or MariaDB => 5.5
                        raise DBMySQLError('Your MySQL/MariaDB version is outdated, consider an upgrade') from e
                    raise DBMySQLError(str(e)) from e
            LOG.error('MySql error {}:', exc)
            raise DBMySQLConnectionError from exc
        finally:
            if self.conn and self.conn.is_connected():
                self.conn.close()

    def _execute_non_query(self, query, params=None, cursor=None, **kwargs):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            query = query.replace("?", "%s")  # sqlite use '?' placeholder
            if params is not None:
                results = cursor.execute(query, params, kwargs)
            else:
                results = cursor.execute(query, kwargs)
            if 'multi' in kwargs:
                # 'multi' is lazy statement run sql only when needed
                for result in results:  # pylint: disable=unused-variable
                    pass
        except mysql.connector.Error as exc:
            LOG.error('MySQL error {}:', exc)
            raise DBMySQLError from exc
        except ValueError:
            LOG.error('Value {}', str(params))
            LOG.error('Value type {}', type(params))
            raise

    def _execute_query(self, query, params=None, cursor=None):
        try:
            if cursor is None:
                cursor = self.get_cursor()
            query = query.replace("?", "%s")  # sqlite use '?' placeholder
            if params is not None:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor
        except mysql.connector.Error as exc:
            LOG.error('MySQL error {}:', exc.args[0])
            raise DBMySQLError from exc
        except ValueError:
            LOG.error('Value {}', str(params))
            LOG.error('Value type {}', type(params))
            raise

    def get_cursor(self):
        return self.conn.cursor()

    def get_cursor_for_dict_results(self):
        conn_cursor = self.conn.cursor(dictionary=True)
        return conn_cursor

    def get_cursor_for_list_results(self):
        # In MySql does not exist row_factory such as sqlite,
        # so need to convert results in while we get rows to reduce cycles see: return_rows_as_list
        conn_cursor = self.conn.cursor(buffered=True)
        return conn_cursor

    def return_rows_as_list(self, conn_cursor):
        # see note in: get_cursor_for_list_results
        return [row[0] for row in conn_cursor]

    @handle_connection
    def get_value(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF,
                  data_type=None):
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
    def get_values(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF):
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
    def set_value(self, key, value, table=db_utils.TABLE_SHARED_APP_CONF):
        """
        Store a single value to database
        :param key: The key to store the value
        :param value: Value to save
        :param table: Table map
        """
        table_name = table[0]
        table_columns = table[1]
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        query = db_utils.mysql_insert_or_update(table_name, [table_columns[0]], [table_columns[1]])
        value = common.convert_to_string(value)
        self._execute_non_query(query, (key, value), multi=True)

    @handle_connection
    def delete_key(self, key, table=db_utils.TABLE_SHARED_APP_CONF):
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
        if self.conn and self.conn.is_connected():
            self.conn.close()
