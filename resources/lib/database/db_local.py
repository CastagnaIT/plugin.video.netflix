# -*- coding: utf-8 -*-
"""Local database access and functions"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_utils as db_utils

from resources.lib.database.db_exceptions import (ProfilesMissing)


class NFLocalDatabase(db_base.NFBaseDatabase):
    def _get_active_guid_profile(self):
        query = 'SELECT Guid FROM Profiles WHERE IsActive = 1'
        cur = self._execute_query(query)
        result = cur.fetchone()
        if result is None:
            raise ProfilesMissing
        return result[0]

    @db_base.sql_connect()
    def get_profile_config(self, key, default_value=None, guid=None):
        """Get a value from a profile, if guid is not specified, is obtained from active profile"""
        if guid is None:
            query = ('SELECT Value FROM ProfilesConfig '
                     'INNER JOIN Profiles ON ProfilesConfig.Guid = Profiles.Guid '
                     'WHERE '
                     'Profiles.IsActive = 1 AND '
                     'ProfilesConfig.Name = ?')
            cur = self._execute_query(query, (key,))
        else:
            query = ('SELECT Value FROM ProfilesConfig '
                     'WHERE '
                     'ProfilesConfig.Guid = ? AND '
                     'ProfilesConfig.Name = ?')
            cur = self._execute_query(query, (guid, key))
        result = cur.fetchone()
        return result[0] if result else default_value

    @db_base.sql_connect()
    def set_profile_config(self, key, value, guid=None):
        """Store a value to a profile, if guid is not specified, is stored to active profile"""
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        if not guid:
            guid = self._get_active_guid_profile()
        update_query = 'UPDATE ProfilesConfig SET Value = ? WHERE Guid = ? AND Name = ?'
        cur = self._execute_query(update_query, (value, guid, key))
        if cur.rowcount == 0:
            insert_query = 'INSERT INTO ProfilesConfig (Guid, Name, Value) VALUES (?, ?, ?)'
            self._execute_non_query(insert_query, (guid, key, value))

    @db_base.sql_connect()
    def set_profile(self, guid, is_active, sort_order):
        """Update or Insert a profile. Use is_active = None with the Shared Database"""
        # Update or insert approach, if there is no updated row then insert new one (no id changes)
        data = db_utils.sql_filtered_update('Profiles',
                                            ['IsActive', 'SortOrder'],
                                            ['Guid'],
                                            [is_active, sort_order, guid])
        cur = self._execute_query(data[0], data[1])
        if cur.rowcount == 0:
            data = db_utils.sql_filtered_insert('Profiles',
                                                ['Guid', 'IsActive', 'SortOrder'],
                                                [guid, is_active, sort_order])
            self._execute_non_query(data[0], data[1])

    @db_base.sql_connect()
    def switch_active_profile(self, guid):
        update_query = 'UPDATE Profiles SET IsActive = 0'
        self._execute_non_query(update_query)
        update_query = 'UPDATE Profiles SET IsActive = 1 WHERE Guid = ?'
        self._execute_non_query(update_query, (guid,))

    @db_base.sql_connect()
    def delete_profile(self, guid):
        query = 'DELETE FROM Profiles WHERE Guid = ?'
        self._execute_non_query(query, (guid,))

    @db_base.sql_connect()
    def get_active_profile_guid(self):
        return self._get_active_guid_profile()

    @db_base.sql_connect()
    def get_guid_profiles(self):
        query = 'SELECT Guid FROM Profiles ORDER BY SortOrder'
        cur = self._execute_query(query)
        return [row[0] for row in cur.fetchall()]
