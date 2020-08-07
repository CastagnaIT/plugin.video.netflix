# Copyright (c) 2009, 2019, Oracle and/or its affiliates. All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2.0, as
# published by the Free Software Foundation.
#
# This program is also distributed with certain software (including
# but not limited to OpenSSL) that is licensed under separate terms,
# as designated in a particular file or component or in included license
# documentation.  The authors of MySQL hereby grant you an
# additional permission to link the program and your derivative works
# with the separately licensed software that they have included with
# MySQL.
#
# Without limiting anything contained in the foregoing, this file,
# which is part of MySQL Connector/Python, is also subject to the
# Universal FOSS Exception, version 1.0, a copy of which can be found at
# http://oss.oracle.com/licenses/universal-foss-exception.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License, version 2.0, for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA

"""
MySQL Connector/Python - MySQL driver written in Python
"""

try:
    import _mysql_connector  # pylint: disable=F0401
    from .connection_cext import CMySQLConnection
except ImportError:
    HAVE_CEXT = False
else:
    HAVE_CEXT = True

from . import version
from .connection import MySQLConnection
from .errors import (  # pylint: disable=W0622
    Error, Warning, InterfaceError, DatabaseError,
    NotSupportedError, DataError, IntegrityError, ProgrammingError,
    OperationalError, InternalError, custom_error_exception, PoolError)
from .constants import FieldFlag, FieldType, CharacterSet, \
    RefreshOption, ClientFlag
from .dbapi import (
    Date, Time, Timestamp, Binary, DateFromTicks,
    TimestampFromTicks, TimeFromTicks,
    STRING, BINARY, NUMBER, DATETIME, ROWID,
    apilevel, threadsafety, paramstyle)
from .optionfiles import read_option_files

_CONNECTION_POOLS = {}

def _get_pooled_connection(**kwargs):
    """Return a pooled MySQL connection"""
    # If no pool name specified, generate one
    from .pooling import (
        MySQLConnectionPool, generate_pool_name,
        CONNECTION_POOL_LOCK)

    try:
        pool_name = kwargs['pool_name']
    except KeyError:
        pool_name = generate_pool_name(**kwargs)

    # Setup the pool, ensuring only 1 thread can update at a time
    with CONNECTION_POOL_LOCK:
        if pool_name not in _CONNECTION_POOLS:
            _CONNECTION_POOLS[pool_name] = MySQLConnectionPool(**kwargs)
        elif isinstance(_CONNECTION_POOLS[pool_name], MySQLConnectionPool):
            # pool_size must be the same
            check_size = _CONNECTION_POOLS[pool_name].pool_size
            if ('pool_size' in kwargs
                    and kwargs['pool_size'] != check_size):
                raise PoolError("Size can not be changed "
                                "for active pools.")

    # Return pooled connection
    try:
        return _CONNECTION_POOLS[pool_name].get_connection()
    except AttributeError:
        raise InterfaceError(
            "Failed getting connection from pool '{0}'".format(pool_name))


def _get_failover_connection(**kwargs):
    """Return a MySQL connection and try to failover if needed

    An InterfaceError is raise when no MySQL is available. ValueError is
    raised when the failover server configuration contains an illegal
    connection argument. Supported arguments are user, password, host, port,
    unix_socket and database. ValueError is also raised when the failover
    argument was not provided.

    Returns MySQLConnection instance.
    """
    config = kwargs.copy()
    try:
        failover = config['failover']
    except KeyError:
        raise ValueError('failover argument not provided')
    del config['failover']

    support_cnx_args = set(
        ['user', 'password', 'host', 'port', 'unix_socket',
         'database', 'pool_name', 'pool_size'])

    # First check if we can add all use the configuration
    for server in failover:
        diff = set(server.keys()) - support_cnx_args
        if diff:
            raise ValueError(
                "Unsupported connection argument {0} in failover: {1}".format(
                    's' if len(diff) > 1 else '',
                    ', '.join(diff)))

    for server in failover:
        new_config = config.copy()
        new_config.update(server)
        try:
            return connect(**new_config)
        except Error:
            # If we failed to connect, we try the next server
            pass

    raise InterfaceError("Could not failover: no MySQL server available")


def connect(*args, **kwargs):
    """Create or get a MySQL connection object

    In its simpliest form, Connect() will open a connection to a
    MySQL server and return a MySQLConnection object.

    When any connection pooling arguments are given, for example pool_name
    or pool_size, a pool is created or a previously one is used to return
    a PooledMySQLConnection.

    Returns MySQLConnection or PooledMySQLConnection.
    """
    # Option files
    if 'read_default_file' in kwargs:
        kwargs['option_files'] = kwargs['read_default_file']
        kwargs.pop('read_default_file')

    if 'option_files' in kwargs:
        new_config = read_option_files(**kwargs)
        return connect(**new_config)

    # Failover
    if 'failover' in kwargs:
        return _get_failover_connection(**kwargs)

    # Pooled connections
    try:
        from .constants import CNX_POOL_ARGS
        if any([key in kwargs for key in CNX_POOL_ARGS]):
            return _get_pooled_connection(**kwargs)
    except NameError:
        # No pooling
        pass

    # Use C Extension by default
    use_pure = kwargs.get('use_pure', False)
    if 'use_pure' in kwargs:
        del kwargs['use_pure']  # Remove 'use_pure' from kwargs
        if not use_pure and not HAVE_CEXT:
            raise ImportError("MySQL Connector/Python C Extension not "
                              "available")

    if HAVE_CEXT and not use_pure:
        return CMySQLConnection(*args, **kwargs)
    return MySQLConnection(*args, **kwargs)
Connect = connect  # pylint: disable=C0103

__version_info__ = version.VERSION
__version__ = version.VERSION_TEXT

__all__ = [
    'MySQLConnection', 'Connect', 'custom_error_exception',

    # Some useful constants
    'FieldType', 'FieldFlag', 'ClientFlag', 'CharacterSet', 'RefreshOption',
    'HAVE_CEXT',

    # Error handling
    'Error', 'Warning',
    'InterfaceError', 'DatabaseError',
    'NotSupportedError', 'DataError', 'IntegrityError', 'ProgrammingError',
    'OperationalError', 'InternalError',

    # DBAPI PEP 249 required exports
    'connect', 'apilevel', 'threadsafety', 'paramstyle',
    'Date', 'Time', 'Timestamp', 'Binary',
    'DateFromTicks', 'DateFromTicks', 'TimestampFromTicks', 'TimeFromTicks',
    'STRING', 'BINARY', 'NUMBER',
    'DATETIME', 'ROWID',

    # C Extension
    'CMySQLConnection',
    ]
