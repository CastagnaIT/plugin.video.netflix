# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Local database access and functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
import resources.lib.database.db_base_sqlite as db_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.database.db_exceptions import (ProfilesMissing)


class NFLocalDatabase(db_sqlite.SQLiteDatabase):
    def __init__(self):  # pylint: disable=super-on-old-class
        super(NFLocalDatabase, self).__init__(db_utils.LOCAL_DB_FILENAME)

    def _get_active_guid_profile(self):
        query = 'SELECT Guid FROM profiles WHERE IsActive = 1'
        cur = self._execute_query(query)
        result = cur.fetchone()
        if result is None:
            raise ProfilesMissing
        return result[0]

    @db_sqlite.handle_connection
    def get_guid_owner_profile(self):
        """Get the guid of owner account profile"""
        query = 'SELECT Guid FROM profiles_config WHERE ' \
                'Name = \'isAccountOwner\' AND Value = \'True\''
        cur = self._execute_query(query)
        result = cur.fetchone()
        if result is None:
            raise ProfilesMissing
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
