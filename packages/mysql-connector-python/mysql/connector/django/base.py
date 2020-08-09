# MySQL Connector/Python - MySQL driver written in Python.

"""Django database Backend using MySQL Connector/Python

This Django database backend is heavily based on the MySQL backend coming
with Django.

Changes include:
* Support for microseconds (MySQL 5.6.3 and later)
* Using INFORMATION_SCHEMA where possible
* Using new defaults for, for example SQL_AUTO_IS_NULL

Requires and comes with MySQL Connector/Python v1.1 and later:
    http://dev.mysql.com/downloads/connector/python/
"""


from __future__ import unicode_literals

from datetime import datetime
import sys
import warnings

import django
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property

try:
    import mysql.connector
    from mysql.connector.conversion import MySQLConverter, MySQLConverterBase
    from mysql.connector.catch23 import PY2
except ImportError as err:
    raise ImproperlyConfigured(
        "Error loading mysql.connector module: {0}".format(err))

try:
    version = mysql.connector.__version_info__[0:3]
except AttributeError:
    from mysql.connector.version import VERSION
    version = VERSION[0:3]

try:
    from _mysql_connector import datetime_to_mysql, time_to_mysql
except ImportError:
    HAVE_CEXT = False
else:
    HAVE_CEXT = True

if version < (1, 11):
    raise ImproperlyConfigured(
        "MySQL Connector/Python v1.11.0 or newer "
        "is required; you have %s" % mysql.connector.__version__)

from django.db import utils
from django.db.backends import utils as backend_utils
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.signals import connection_created
from django.utils import (six, timezone, dateparse)
from django.conf import settings

from mysql.connector.django.client import DatabaseClient
from mysql.connector.django.creation import DatabaseCreation
from mysql.connector.django.introspection import DatabaseIntrospection
from mysql.connector.django.validation import DatabaseValidation
from mysql.connector.django.features import DatabaseFeatures
from mysql.connector.django.operations import DatabaseOperations
from mysql.connector.django.schema import DatabaseSchemaEditor


DatabaseError = mysql.connector.DatabaseError
IntegrityError = mysql.connector.IntegrityError
NotSupportedError = mysql.connector.NotSupportedError


def adapt_datetime_with_timezone_support(value):
    # Equivalent to DateTimeField.get_db_prep_value. Used only by raw SQL.
    if settings.USE_TZ:
        if timezone.is_naive(value):
            warnings.warn("MySQL received a naive datetime (%s)"
                          " while time zone support is active." % value,
                          RuntimeWarning)
            default_timezone = timezone.get_default_timezone()
            value = timezone.make_aware(value, default_timezone)
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    if HAVE_CEXT:
        return datetime_to_mysql(value)
    else:
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")


class DjangoMySQLConverter(MySQLConverter):
    """Custom converter for Django for MySQLConnection"""
    def _TIME_to_python(self, value, dsc=None):
        """Return MySQL TIME data type as datetime.time()

        Returns datetime.time()
        """
        return dateparse.parse_time(value.decode('utf-8'))

    def _DATETIME_to_python(self, value, dsc=None):
        """Connector/Python always returns naive datetime.datetime

        Connector/Python always returns naive timestamps since MySQL has
        no time zone support. Since Django needs non-naive, we need to add
        the UTC time zone.

        Returns datetime.datetime()
        """
        if not value:
            return None
        dt = MySQLConverter._DATETIME_to_python(self, value)
        if dt is None:
            return None
        if settings.USE_TZ and timezone.is_naive(dt):
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _safetext_to_mysql(self, value):
        if PY2:
            return self._unicode_to_mysql(value)
        else:
            return self._str_to_mysql(value)

    def _safebytes_to_mysql(self, value):
        return self._bytes_to_mysql(value)


class DjangoCMySQLConverter(MySQLConverterBase):
    """Custom converter for Django for CMySQLConnection"""
    def _TIME_to_python(self, value, dsc=None):
        """Return MySQL TIME data type as datetime.time()

        Returns datetime.time()
        """
        return dateparse.parse_time(str(value))

    def _DATETIME_to_python(self, value, dsc=None):
        """Connector/Python always returns naive datetime.datetime

        Connector/Python always returns naive timestamps since MySQL has
        no time zone support. Since Django needs non-naive, we need to add
        the UTC time zone.

        Returns datetime.datetime()
        """
        if not value:
            return None
        if settings.USE_TZ and timezone.is_naive(value):
            value = value.replace(tzinfo=timezone.utc)
        return value


class CursorWrapper(object):
    """Wrapper around MySQL Connector/Python's cursor class.

    The cursor class is defined by the options passed to MySQL
    Connector/Python. If buffered option is True in those options,
    MySQLCursorBuffered will be used.
    """
    codes_for_integrityerror = (1048,)

    def __init__(self, cursor):
        self.cursor = cursor

    def _execute_wrapper(self, method, query, args):
        """Wrapper around execute() and executemany()"""
        try:
            return method(query, args)
        except (mysql.connector.ProgrammingError) as err:
            six.reraise(utils.ProgrammingError,
                        utils.ProgrammingError(err.msg), sys.exc_info()[2])
        except (mysql.connector.IntegrityError) as err:
            six.reraise(utils.IntegrityError,
                        utils.IntegrityError(err.msg), sys.exc_info()[2])
        except mysql.connector.OperationalError as err:
            # Map some error codes to IntegrityError, since they seem to be
            # misclassified and Django would prefer the more logical place.
            if err.args[0] in self.codes_for_integrityerror:
                six.reraise(utils.IntegrityError,
                            utils.IntegrityError(err.msg), sys.exc_info()[2])
            else:
                six.reraise(utils.DatabaseError,
                            utils.DatabaseError(err.msg), sys.exc_info()[2])
        except mysql.connector.DatabaseError as err:
            six.reraise(utils.DatabaseError,
                        utils.DatabaseError(err.msg), sys.exc_info()[2])

    def _adapt_execute_args_dict(self, args):
        if not args:
            return args
        new_args = dict(args)
        for key, value in args.items():
            if isinstance(value, datetime):
                new_args[key] = adapt_datetime_with_timezone_support(value)

        return new_args

    def _adapt_execute_args(self, args):
        if not args:
            return args
        new_args = list(args)
        for i, arg in enumerate(args):
            if isinstance(arg, datetime):
                new_args[i] = adapt_datetime_with_timezone_support(arg)

        return tuple(new_args)

    def execute(self, query, args=None):
        """Executes the given operation

        This wrapper method around the execute()-method of the cursor is
        mainly needed to re-raise using different exceptions.
        """
        if isinstance(args, dict):
            new_args = self._adapt_execute_args_dict(args)
        else:
            new_args = self._adapt_execute_args(args)
        return self._execute_wrapper(self.cursor.execute, query, new_args)

    def executemany(self, query, args):
        """Executes the given operation

        This wrapper method around the executemany()-method of the cursor is
        mainly needed to re-raise using different exceptions.
        """
        return self._execute_wrapper(self.cursor.executemany, query, args)

    def __getattr__(self, attr):
        """Return attribute of wrapped cursor"""
        return getattr(self.cursor, attr)

    def __iter__(self):
        """Returns iterator over wrapped cursor"""
        return iter(self.cursor)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'mysql'
    # This dictionary maps Field objects to their associated MySQL column
    # types, as strings. Column-type strings can contain format strings; they'll
    # be interpolated against the values of Field.__dict__ before being output.
    # If a column type is set to None, it won't be included in the output.

    _data_types = {
        'AutoField': 'integer AUTO_INCREMENT',
        'BinaryField': 'longblob',
        'BooleanField': 'bool',
        'CharField': 'varchar(%(max_length)s)',
        'CommaSeparatedIntegerField': 'varchar(%(max_length)s)',
        'DateField': 'date',
        'DateTimeField': 'datetime',
        'DecimalField': 'numeric(%(max_digits)s, %(decimal_places)s)',
        'DurationField': 'bigint',
        'FileField': 'varchar(%(max_length)s)',
        'FilePathField': 'varchar(%(max_length)s)',
        'FloatField': 'double precision',
        'IntegerField': 'integer',
        'BigIntegerField': 'bigint',
        'IPAddressField': 'char(15)',
        'GenericIPAddressField': 'char(39)',
        'NullBooleanField': 'bool',
        'OneToOneField': 'integer',
        'PositiveIntegerField': 'integer UNSIGNED',
        'PositiveSmallIntegerField': 'smallint UNSIGNED',
        'SlugField': 'varchar(%(max_length)s)',
        'SmallIntegerField': 'smallint',
        'TextField': 'longtext',
        'TimeField': 'time',
        'UUIDField': 'char(32)',
    }

    @cached_property
    def data_types(self):
        if self.features.supports_microsecond_precision:
            return dict(self._data_types, DateTimeField='datetime(6)',
                        TimeField='time(6)')
        else:
            return self._data_types

    operators = {
        'exact': '= %s',
        'iexact': 'LIKE %s',
        'contains': 'LIKE BINARY %s',
        'icontains': 'LIKE %s',
        'regex': 'REGEXP BINARY %s',
        'iregex': 'REGEXP %s',
        'gt': '> %s',
        'gte': '>= %s',
        'lt': '< %s',
        'lte': '<= %s',
        'startswith': 'LIKE BINARY %s',
        'endswith': 'LIKE BINARY %s',
        'istartswith': 'LIKE %s',
        'iendswith': 'LIKE %s',
    }

    # The patterns below are used to generate SQL pattern lookup clauses when
    # the right-hand side of the lookup isn't a raw string (it might be an
    # expression or the result of a bilateral transformation).
    # In those cases, special characters for LIKE operators (e.g. \, *, _)
    # should be escaped on database side.
    #
    # Note: we use str.format() here for readability as '%' is used as a
    # wildcard for the LIKE operator.
    pattern_esc = (r"REPLACE(REPLACE(REPLACE({}, '\\', '\\\\'),"
                   r" '%%', '\%%'), '_', '\_')")
    pattern_ops = {
        'contains': "LIKE BINARY CONCAT('%%', {}, '%%')",
        'icontains': "LIKE CONCAT('%%', {}, '%%')",
        'startswith': "LIKE BINARY CONCAT({}, '%%')",
        'istartswith': "LIKE CONCAT({}, '%%')",
        'endswith': "LIKE BINARY CONCAT('%%', {})",
        'iendswith': "LIKE CONCAT('%%', {})",
    }

    SchemaEditorClass = DatabaseSchemaEditor
    Database = mysql.connector

    client_class = DatabaseClient
    creation_class = DatabaseCreation
    features_class = DatabaseFeatures
    introspection_class = DatabaseIntrospection
    ops_class = DatabaseOperations
    validation_class = DatabaseValidation

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        try:
            self._use_pure = self.settings_dict['OPTIONS']['use_pure']
        except KeyError:
            self._use_pure = True

        if not self.use_pure:
            self.converter = DjangoCMySQLConverter()
        else:
            self.converter = DjangoMySQLConverter()

    def _valid_connection(self):
        if self.connection:
            return self.connection.is_connected()
        return False

    def get_connection_params(self):
        kwargs = {
            'charset': 'utf8',
            'use_unicode': True,
            'buffered': False,
            'consume_results': True,
        }

        settings_dict = self.settings_dict

        if settings_dict['USER']:
            kwargs['user'] = settings_dict['USER']
        if settings_dict['NAME']:
            kwargs['database'] = settings_dict['NAME']
        if settings_dict['PASSWORD']:
            kwargs['passwd'] = settings_dict['PASSWORD']
        if settings_dict['HOST'].startswith('/'):
            kwargs['unix_socket'] = settings_dict['HOST']
        elif settings_dict['HOST']:
            kwargs['host'] = settings_dict['HOST']
        if settings_dict['PORT']:
            kwargs['port'] = int(settings_dict['PORT'])

        # Raise exceptions for database warnings if DEBUG is on
        kwargs['raise_on_warnings'] = settings.DEBUG

        kwargs['client_flags'] = [
            # Need potentially affected rows on UPDATE
            mysql.connector.constants.ClientFlag.FOUND_ROWS,
        ]
        try:
            kwargs.update(settings_dict['OPTIONS'])
        except KeyError:
            # OPTIONS missing is OK
            pass

        return kwargs

    def get_new_connection(self, conn_params):
        if not self.use_pure:
            conn_params['converter_class'] = DjangoCMySQLConverter
        else:
            conn_params['converter_class'] = DjangoMySQLConverter
        cnx = mysql.connector.connect(**conn_params)

        return cnx

    def init_connection_state(self):
        if self.mysql_version < (5, 5, 3):
            # See sysvar_sql_auto_is_null in MySQL Reference manual
            self.connection.cmd_query("SET SQL_AUTO_IS_NULL = 0")

        if 'AUTOCOMMIT' in self.settings_dict:
            try:
                self.set_autocommit(self.settings_dict['AUTOCOMMIT'])
            except AttributeError:
                self._set_autocommit(self.settings_dict['AUTOCOMMIT'])

    def create_cursor(self, name=None):
        cursor = self.connection.cursor()
        return CursorWrapper(cursor)

    def _connect(self):
        """Setup the connection with MySQL"""
        self.connection = self.get_new_connection(self.get_connection_params())
        connection_created.send(sender=self.__class__, connection=self)
        self.init_connection_state()

    def _cursor(self):
        """Return a CursorWrapper object

        Returns a CursorWrapper
        """
        try:
            return super(DatabaseWrapper, self)._cursor()
        except AttributeError:
            if not self.connection:
                self._connect()
            return self.create_cursor()

    def get_server_version(self):
        """Returns the MySQL server version of current connection

        Returns a tuple
        """
        try:
            self.ensure_connection()
        except AttributeError:
            if not self.connection:
                self._connect()

        return self.connection.get_server_version()

    def disable_constraint_checking(self):
        """Disables foreign key checks

        Disables foreign key checks, primarily for use in adding rows with
        forward references. Always returns True,
        to indicate constraint checks need to be re-enabled.

        Returns True
        """
        self.cursor().execute('SET @@session.foreign_key_checks = 0')
        return True

    def enable_constraint_checking(self):
        """Re-enable foreign key checks

        Re-enable foreign key checks after they have been disabled.
        """
        # Override needs_rollback in case constraint_checks_disabled is
        # nested inside transaction.atomic.
        self.needs_rollback, needs_rollback = False, self.needs_rollback
        try:
            self.cursor().execute('SET @@session.foreign_key_checks = 1')
        finally:
            self.needs_rollback = needs_rollback

    def check_constraints(self, table_names=None):
        """Check rows in tables for invalid foreign key references

        Checks each table name in `table_names` for rows with invalid foreign
        key references. This method is intended to be used in conjunction with
        `disable_constraint_checking()` and `enable_constraint_checking()`, to
        determine if rows with invalid references were entered while
        constraint checks were off.

        Raises an IntegrityError on the first invalid foreign key reference
        encountered (if any) and provides detailed information about the
        invalid reference in the error message.

        Backends can override this method if they can more directly apply
        constraint checking (e.g. via "SET CONSTRAINTS ALL IMMEDIATE")
        """
        ref_query = """
            SELECT REFERRING.`{0}`, REFERRING.`{1}` FROM `{2}` as REFERRING
            LEFT JOIN `{3}` as REFERRED
            ON (REFERRING.`{4}` = REFERRED.`{5}`)
            WHERE REFERRING.`{6}` IS NOT NULL AND REFERRED.`{7}` IS NULL"""
        cursor = self.cursor()
        if table_names is None:
            table_names = self.introspection.table_names(cursor)
        for table_name in table_names:
            primary_key_column_name = \
                self.introspection.get_primary_key_column(cursor, table_name)
            if not primary_key_column_name:
                continue
            key_columns = self.introspection.get_key_columns(cursor,
                                                             table_name)
            for column_name, referenced_table_name, referenced_column_name \
                    in key_columns:
                cursor.execute(ref_query.format(primary_key_column_name,
                                                column_name, table_name,
                                                referenced_table_name,
                                                column_name,
                                                referenced_column_name,
                                                column_name,
                                                referenced_column_name))
                for bad_row in cursor.fetchall():
                    msg = ("The row in table '{0}' with primary key '{1}' has "
                           "an invalid foreign key: {2}.{3} contains a value "
                           "'{4}' that does not have a corresponding value in "
                           "{5}.{6}.".format(table_name, bad_row[0],
                                             table_name, column_name,
                                             bad_row[1], referenced_table_name,
                                             referenced_column_name))
                    raise utils.IntegrityError(msg)

    def _rollback(self):
        try:
            BaseDatabaseWrapper._rollback(self)
        except NotSupportedError:
            pass

    def _set_autocommit(self, autocommit):
        with self.wrap_database_errors:
            self.connection.autocommit = autocommit

    def schema_editor(self, *args, **kwargs):
        """Returns a new instance of this backend's SchemaEditor"""
        return DatabaseSchemaEditor(self, *args, **kwargs)

    def is_usable(self):
        return self.connection.is_connected()

    @cached_property
    def mysql_version(self):
        config = self.get_connection_params()
        temp_conn = mysql.connector.connect(**config)
        server_version = temp_conn.get_server_version()
        temp_conn.close()

        return server_version

    @property
    def use_pure(self):
        return not HAVE_CEXT or self._use_pure
