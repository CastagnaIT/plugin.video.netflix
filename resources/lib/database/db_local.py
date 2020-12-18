# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Local database access and functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from datetime import datetime

import resources.lib.common as common
import resources.lib.database.db_base_sqlite as db_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.common.exceptions import DBProfilesMissing


class NFLocalDatabase(db_sqlite.SQLiteDatabase):
    def __init__(self):
        super().__init__(db_utils.LOCAL_DB_FILENAME)

    def _get_active_guid_profile(self):
        query = 'SELECT Guid FROM profiles WHERE IsActive = 1'
        cur = self._execute_query(query)
        result = cur.fetchone()
        if result is None:
            raise DBProfilesMissing
        return result[0]

    @db_sqlite.handle_connection
    def get_guid_owner_profile(self):
        """Get the guid of owner account profile"""
        query = 'SELECT Guid FROM profiles_config WHERE ' \
                'Name = \'isAccountOwner\' AND Value = \'True\''
        cur = self._execute_query(query)
        result = cur.fetchone()
        if result is None:
            raise DBProfilesMissing
        return result[0]

    @db_sqlite.handle_connection
    def get_profile_config(self, key, default_value=None, guid=None, data_type=None):
        """Get a value from a profile, if guid is not specified, is obtained from active profile"""
        if guid is None:
            query = ('SELECT Value FROM profiles_config '
                     'INNER JOIN profiles ON profiles_config.Guid = profiles.Guid '
                     'WHERE '
                     'profiles.IsActive = 1 AND '
                     'profiles_config.Name = ?')
            cur = self._execute_query(query, (key,))
        else:
            query = ('SELECT Value FROM profiles_config '
                     'WHERE '
                     'profiles_config.Guid = ? AND '
                     'profiles_config.Name = ?')
            cur = self._execute_query(query, (guid, key))
        result = cur.fetchone()
        if default_value is not None:
            data_type = type(default_value)
        elif data_type is None:
            data_type = str
        return common.convert_from_string(result[0], data_type) \
            if result is not None else default_value

    @db_sqlite.handle_connection
    def set_profile_config(self, key, value, guid=None):
        """Store a value to a profile, if guid is not specified, is stored to active profile"""
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        if not guid:
            guid = self._get_active_guid_profile()
        update_query = 'UPDATE profiles_config SET Value = ? WHERE Guid = ? AND Name = ?'
        value = common.convert_to_string(value)
        cur = self._execute_query(update_query, (value, guid, key))
        if cur.rowcount == 0:
            insert_query = 'INSERT INTO profiles_config (Guid, Name, Value) VALUES (?, ?, ?)'
            self._execute_non_query(insert_query, (guid, key, value))

    @db_sqlite.handle_connection
    def insert_profile_configs(self, dict_values, guid=None):
        """
        Store multiple values to a profile by deleting all existing values,
        if guid is not specified, is stored to active profile
        """
        # Doing many sqlite operations at the same makes the performance much worse (especially on Kodi 18)
        # The use of 'executemany' and 'transaction' can improve performance up to about 75% !!
        if not guid:
            guid = self._get_active_guid_profile()
        cur = self.get_cursor()
        cur.execute("BEGIN TRANSACTION;")
        query = 'DELETE FROM profiles_config WHERE Guid = ?'
        self._execute_non_query(query, (guid,), cur)
        records_values = [(guid, key, common.convert_to_string(value)) for key, value in dict_values.items()]
        insert_query = 'INSERT INTO profiles_config (Guid, Name, Value) VALUES (?, ?, ?)'
        self._executemany_non_query(insert_query, records_values, cur)
        cur.execute("COMMIT;")

    @db_sqlite.handle_connection
    def set_profile(self, guid, is_active, sort_order):
        """Update or Insert a profile"""
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        data = db_utils.sql_filtered_update('profiles',
                                            ['IsActive', 'SortOrder'],
                                            ['Guid'],
                                            [is_active, sort_order, guid])
        cur = self._execute_query(data[0], data[1])
        if cur.rowcount == 0:
            data = db_utils.sql_filtered_insert('profiles',
                                                ['Guid', 'IsActive', 'SortOrder'],
                                                [guid, is_active, sort_order])
            self._execute_non_query(data[0], data[1])

    @db_sqlite.handle_connection
    def switch_active_profile(self, guid):
        update_query = 'UPDATE profiles SET IsActive = 0'
        self._execute_non_query(update_query)
        update_query = 'UPDATE profiles SET IsActive = 1 WHERE Guid = ?'
        self._execute_non_query(update_query, (guid,))

    @db_sqlite.handle_connection
    def delete_profile(self, guid):
        query = 'DELETE FROM profiles WHERE Guid = ?'
        self._execute_non_query(query, (guid,))

    @db_sqlite.handle_connection
    def get_active_profile_guid(self):
        return self._get_active_guid_profile()

    @db_sqlite.handle_connection
    def get_guid_profiles(self):
        query = 'SELECT Guid FROM profiles ORDER BY SortOrder'
        cur = self._execute_query(query)
        return [row[0] for row in cur.fetchall()]

    @db_sqlite.handle_connection
    def get_search_list(self):
        guid = self.get_active_profile_guid()
        query = ('SELECT * FROM search '
                 'WHERE Guid = ? '
                 'ORDER BY datetime("LastAccess") DESC')
        cur = self.get_cursor_for_dict_results()
        cur = self._execute_query(query, (guid,), cur)
        return cur.fetchall()

    @db_sqlite.handle_connection
    def get_search_item(self, row_id):
        query = 'SELECT * FROM search WHERE ID = ?'
        cur = self.get_cursor_for_dict_results()
        cur = self._execute_query(query, (row_id,), cur)
        return cur.fetchone()

    @db_sqlite.handle_connection
    def insert_search_item(self, search_type, value, parameters=None):
        """Insert a new search item and return the ID of the new entry"""
        insert_query = ('INSERT INTO search (Guid, Type, Value, Parameters, LastAccess) '
                        'VALUES (?, ?, ?, ?, ?)')
        if parameters:
            parameters = common.convert_to_string(parameters)
        guid = self.get_active_profile_guid()
        date_last_access = common.convert_to_string(datetime.now())
        cur = self.get_cursor()
        self._execute_non_query(insert_query, (guid, search_type, value, parameters, date_last_access), cur)
        return str(cur.lastrowid)

    @db_sqlite.handle_connection
    def delete_search_item(self, row_id):
        """Delete a search item"""
        query = 'DELETE FROM search WHERE ID = ?'
        self._execute_non_query(query, (row_id,))

    @db_sqlite.handle_connection
    def clear_search_items(self):
        """Delete all search items"""
        query = 'DELETE FROM search WHERE Guid = ?'
        guid = self.get_active_profile_guid()
        self._execute_non_query(query, (guid,))

    @db_sqlite.handle_connection
    def update_search_item_last_access(self, row_id):
        """Update the last access data to a search item"""
        update_query = 'UPDATE search SET LastAccess = ? WHERE ID = ?'
        date_last_access = common.convert_to_string(datetime.now())
        self._execute_non_query(update_query, (date_last_access, row_id))

    @db_sqlite.handle_connection
    def update_search_item_value(self, row_id, value):
        """Update the 'value' data to a search item"""
        update_query = 'UPDATE search SET Value = ?, LastAccess = ? WHERE ID = ?'
        date_last_access = common.convert_to_string(datetime.now())
        self._execute_non_query(update_query, (value, date_last_access, row_id))
