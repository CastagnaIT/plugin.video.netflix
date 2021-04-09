# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Functions for updating the databases

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from resources.lib.common import CmpVersion
from resources.lib.globals import G


def run_local_db_updates(current_version, upgrade_to_version):  # pylint: disable=unused-argument
    """Perform database actions for a db version change"""
    # The changes must be left in sequence to allow cascade operations on non-updated databases
    if CmpVersion(current_version) < '0.2':
        # Changes: added table 'search'
        import sqlite3 as sql
        from resources.lib.database.db_base_sqlite import CONN_ISOLATION_LEVEL
        from resources.lib.database import db_utils

        shared_db_conn = sql.connect(db_utils.get_local_db_path(db_utils.LOCAL_DB_FILENAME),
                                     isolation_level=CONN_ISOLATION_LEVEL)
        cur = shared_db_conn.cursor()

        table = str('CREATE TABLE search ('
                    'ID         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,'
                    'Guid       TEXT    NOT NULL REFERENCES profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE,'
                    'Type       TEXT    NOT NULL,'
                    'Value      TEXT    NOT NULL,'
                    'Parameters TEXT,'
                    'LastAccess TEXT);')
        cur.execute(table)
        shared_db_conn.close()

    if CmpVersion(current_version) < '0.3':
        pass


def run_shared_db_updates(current_version, upgrade_to_version):  # pylint: disable=unused-argument
    """Perform database actions for a db version change"""
    # The changes must be left in sequence to allow cascade operations on non-updated databases

    if CmpVersion(current_version) < '0.2':
        # Changes: added table 'watched_status_override'

        # SQLite
        import sqlite3 as sql
        from resources.lib.database.db_base_sqlite import CONN_ISOLATION_LEVEL
        from resources.lib.database import db_utils

        shared_db_conn = sql.connect(db_utils.get_local_db_path(db_utils.SHARED_DB_FILENAME),
                                     isolation_level=CONN_ISOLATION_LEVEL)
        cur = shared_db_conn.cursor()

        cur.execute('SELECT name FROM sqlite_master WHERE type="table";')
        tables = cur.fetchall()
        # Check if watched_status_override exists
        # (temporary check, usually not needed, applied for previous oversight in the code, can be removed in future)
        if ('watched_status_override',) not in tables:
            table = str('CREATE TABLE watched_status_override ('
                        'ProfileGuid      TEXT    NOT NULL,'
                        'VideoID          INTEGER NOT NULL,'
                        'Value            TEXT,'
                        'PRIMARY KEY (ProfileGuid, VideoID ),'
                        'FOREIGN KEY (ProfileGuid)'
                        'REFERENCES Profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE);')
            cur.execute(table)
            shared_db_conn.close()

            # MySQL
            if G.ADDON.getSettingBool('use_mysql'):
                import mysql.connector
                from resources.lib.database.db_base_mysql import MySQLDatabase

                shared_db_conn = MySQLDatabase()
                shared_db_conn.conn = mysql.connector.connect(**shared_db_conn.config)
                cur = shared_db_conn.conn.cursor()

                table = ('CREATE TABLE netflix_addon.watched_status_override ('
                         'ProfileGuid VARCHAR(50) NOT NULL,'
                         'VideoID INT(11) NOT NULL,'
                         'Value TEXT DEFAULT NULL,'
                         'PRIMARY KEY (ProfileGuid, VideoID))'
                         'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
                alter_tbl = ('ALTER TABLE netflix_addon.watched_status_override '
                             'ADD CONSTRAINT FK_watchedstatusoverride_ProfileGuid FOREIGN KEY (ProfileGuid)'
                             'REFERENCES netflix_addon.profiles(Guid) ON DELETE CASCADE ON UPDATE CASCADE;')
                cur.execute(table)
                cur.execute(alter_tbl)
                shared_db_conn.conn.close()

    if CmpVersion(current_version) < '0.3':
        pass
