# -*- coding: utf-8 -*-
"""MySQL database"""
from __future__ import unicode_literals

from functools import wraps

import mysql.connector

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_utils as db_utils
from resources.lib.database.db_exceptions import (MySQLConnectionError, MySQLError)
from resources.lib.globals import g


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
        except mysql.connector.Error as e:
            common.error("MySQL error {}:".format(e))
            raise MySQLConnectionError
        finally:
            if conn and conn.is_connected():
                conn.close()
    return wrapper


class MySQLDatabase(db_base.BaseDatabase):
    def __init__(self, test_config=None):
        self.is_mysql_database = True
        self.database = 'netflix_addon'
        if test_config:
            self.is_connection_test = True
            self.config = test_config
        else:
            self.is_connection_test = False
            self.config = {
                'user': g.ADDON.getSetting('mysql_username'),
                'password': g.ADDON.getSetting('mysql_password'),
                'host': g.ADDON.getSetting('mysql_host'),
                'port': g.ADDON.getSettingInt('mysql_port'),
                'database': 'netflix_addon',
                'autocommit': True,
                'charset': 'utf8',
                'use_unicode': True
            }
        super(MySQLDatabase, self).__init__()

    def _initialize_connection(self):
        try:
            common.debug('Trying connection to the MySQL database {}'.format(self.database))
            self.conn = mysql.connector.connect(**self.config)
            if self.conn.is_connected():
                db_info = self.conn.get_server_info()
                common.debug('MySQL database connection was successful (MySQL server ver. {})'
                             .format(db_info))
        except mysql.connector.Error as e:
            if e.errno == 1049 and not self.is_connection_test:
                # Database does not exist
                # TODO: create a new one
                if self.conn and self.conn.is_connected():
                    self.conn.close()
                self._initialize_connection()
                return
            common.error("MySql error {}:".format(e))
            raise MySQLConnectionError
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
                for result in results:  # 'multi' is lazy statement run sql only when needed
                    pass
        except mysql.connector.Error as e:
            common.error("MySQL error {}:".format(e))
            raise MySQLError
        except ValueError as exc_ve:
            common.error('Value {}'.format(str(params)))
            common.error('Value type {}'.format(type(params)))
            raise exc_ve

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
        except mysql.connector.Error as e:
            common.error("MySQL error {}:".format(e.args[0]))
            raise MySQLError
        except ValueError as exc_ve:
            common.error('Value {}'.format(str(params)))
            common.error('Value type {}'.format(type(params)))
            raise exc_ve

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
        query = 'SELECT {} FROM {} WHERE {} = ?'.format(table_columns[1],
                                                        table_name,
                                                        table_columns[0])
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
        query = 'DELETE FROM {} WHERE {} = ?'.format(table_name, table_columns[0])
        cur = self._execute_query(query, (key,))
        return cur.rowcount

    def __del__(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
