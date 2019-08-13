# MySQL Connector/Python - MySQL driver written in Python.

import django
from django.db.backends.base.features import BaseDatabaseFeatures
from django.utils.functional import cached_property
from django.utils import six

try:
    import pytz
    HAVE_PYTZ = True
except ImportError:
    HAVE_PYTZ = False


class DatabaseFeatures(BaseDatabaseFeatures):
    """Features specific to MySQL

    Microsecond precision is supported since MySQL 5.6.3 and turned on
    by default if this MySQL version is used.
    """
    empty_fetchmany_value = []
    update_can_self_select = False
    allows_group_by_pk = True
    related_fields_match_type = True
    allow_sliced_subqueries = False
    has_bulk_insert = True
    has_select_for_update = True
    has_select_for_update_nowait = False
    supports_forward_references = False
    supports_regex_backreferencing = False
    supports_date_lookup_using_string = False
    can_introspect_autofield = True
    can_introspect_binary_field = False
    can_introspect_small_integer_field = True
    supports_timezones = False
    requires_explicit_null_ordering_when_grouping = True
    allows_auto_pk_0 = False
    allows_primary_key_0 = False
    uses_savepoints = True
    atomic_transactions = False
    supports_column_check_constraints = False

    def __init__(self, connection):
        super(DatabaseFeatures, self).__init__(connection)

    @cached_property
    def supports_microsecond_precision(self):
        if self.connection.mysql_version >= (5, 6, 3):
            return True
        return False

    @cached_property
    def mysql_storage_engine(self):
        """Get default storage engine of MySQL

        This method creates a table without ENGINE table option and inspects
        which engine was used.

        Used by Django tests.
        """
        tblname = 'INTROSPECT_TEST'

        droptable = 'DROP TABLE IF EXISTS {table}'.format(table=tblname)
        with self.connection.cursor() as cursor:
            cursor.execute(droptable)
            cursor.execute('CREATE TABLE {table} (X INT)'.format(table=tblname))

            if self.connection.mysql_version >= (5, 0, 0):
                cursor.execute(
                    "SELECT ENGINE FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                    (self.connection.settings_dict['NAME'], tblname))
                engine = cursor.fetchone()[0]
            else:
                # Very old MySQL servers..
                cursor.execute("SHOW TABLE STATUS WHERE Name='{table}'".format(
                    table=tblname))
                engine = cursor.fetchone()[1]
            cursor.execute(droptable)

        self._cached_storage_engine = engine
        return engine

    @cached_property
    def _disabled_supports_transactions(self):
        return self.mysql_storage_engine == 'InnoDB'

    @cached_property
    def can_introspect_foreign_keys(self):
        """Confirm support for introspected foreign keys

        Only the InnoDB storage engine supports Foreigen Key (not taking
        into account MySQL Cluster here).
        """
        return self.mysql_storage_engine == 'InnoDB'

    @cached_property
    def has_zoneinfo_database(self):
        """Tests if the time zone definitions are installed

        MySQL accepts full time zones names (eg. Africa/Nairobi) but rejects
        abbreviations (eg. EAT). When pytz isn't installed and the current
        time zone is LocalTimezone (the only sensible value in this context),
        the current time zone name will be an abbreviation. As a consequence,
        MySQL cannot perform time zone conversions reliably.
        """
        if not HAVE_PYTZ:
            return False

        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM mysql.time_zone LIMIT 1")
            return cursor.fetchall() != []

    def introspected_boolean_field_type(self, *args, **kwargs):
        return 'IntegerField'
