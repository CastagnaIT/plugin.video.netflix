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

"""Implementing communication with MySQL servers.
"""

from io import IOBase
import os
import platform
import socket
import time

from .authentication import get_auth_plugin
from .catch23 import PY2, isstr, UNICODE_TYPES
from .constants import (
    ClientFlag, ServerCmd, ServerFlag,
    flag_is_set, ShutdownType, NET_BUFFER_LENGTH
)

from . import errors, version
from .conversion import MySQLConverter
from .cursor import (
    CursorBase, MySQLCursor, MySQLCursorRaw,
    MySQLCursorBuffered, MySQLCursorBufferedRaw, MySQLCursorPrepared,
    MySQLCursorDict, MySQLCursorBufferedDict, MySQLCursorNamedTuple,
    MySQLCursorBufferedNamedTuple)
from .network import MySQLUnixSocket, MySQLTCPSocket
from .protocol import MySQLProtocol
from .utils import int4store, linux_distribution
from .abstracts import MySQLConnectionAbstract


class MySQLConnection(MySQLConnectionAbstract):
    """Connection to a MySQL Server"""
    def __init__(self, *args, **kwargs):
        self._protocol = None
        self._socket = None
        self._handshake = None
        super(MySQLConnection, self).__init__(*args, **kwargs)

        self._converter_class = MySQLConverter

        self._client_flags = ClientFlag.get_default()
        self._charset_id = 45
        self._sql_mode = None
        self._time_zone = None
        self._autocommit = False

        self._user = ''
        self._password = ''
        self._database = ''
        self._host = '127.0.0.1'
        self._port = 3306
        self._unix_socket = None
        self._client_host = ''
        self._client_port = 0
        self._ssl = {}
        self._force_ipv6 = False

        self._use_unicode = True
        self._get_warnings = False
        self._raise_on_warnings = False
        self._buffered = False
        self._unread_result = False
        self._have_next_result = False
        self._raw = False
        self._in_transaction = False

        self._prepared_statements = None

        self._ssl_active = False
        self._auth_plugin = None
        self._pool_config_version = None

        self._columns_desc = []

        if kwargs:
            try:
                self.connect(**kwargs)
            except:
                # Tidy-up underlying socket on failure
                self.close()
                self._socket = None
                raise

    def _add_default_conn_attrs(self):
        """Add the default connection attributes."""
        if os.name == "nt":
            if "64" in platform.architecture()[0]:
                platform_arch = "x86_64"
            elif "32" in platform.architecture()[0]:
                platform_arch = "i386"
            else:
                platform_arch = platform.architecture()
            os_ver = "Windows-{}".format(platform.win32_ver()[1])
        else:
            platform_arch = platform.machine()
            if platform.system() == "Darwin":
                os_ver = "{}-{}".format("macOS", platform.mac_ver()[0])
            else:
                os_ver = "-".join(linux_distribution()[0:2])

        license_chunks = version.LICENSE.split(" ")
        if license_chunks[0] == "GPLv2":
            client_license = "GPL-2.0"
        else:
            client_license = "Commercial"
        default_conn_attrs = {
            "_pid": str(os.getpid()),
            "_platform": platform_arch,
            "_source_host": socket.gethostname(),
            "_client_name": "mysql-connector-python",
            "_client_license": client_license,
            "_client_version": ".".join([str(x) for x in version.VERSION[0:3]]),
            "_os": os_ver}

        self._conn_attrs.update((default_conn_attrs))

    def _do_handshake(self):
        """Get the handshake from the MySQL server"""
        packet = self._socket.recv()
        if packet[4] == 255:
            raise errors.get_exception(packet)

        self._handshake = None
        try:
            handshake = self._protocol.parse_handshake(packet)
        except Exception as err:
            # pylint: disable=E1101
            raise errors.get_mysql_exception(msg=err.msg, errno=err.errno,
                                             sqlstate=err.sqlstate)

        self._server_version = self._check_server_version(
            handshake['server_version_original'])

        if not handshake['capabilities'] & ClientFlag.SSL:
            self._client_flags &= ~ClientFlag.SSL
            if self._ssl.get('verify_cert'):
                raise errors.InterfaceError("SSL is required but the server "
                                            "doesn't support it", errno=2026)
        elif not self._ssl_disabled:
            self._client_flags |= ClientFlag.SSL

        if handshake['capabilities'] & ClientFlag.PLUGIN_AUTH:
            self.set_client_flags([ClientFlag.PLUGIN_AUTH])

        self._handshake = handshake

    def _do_auth(self, username=None, password=None, database=None,
                 client_flags=0, charset=45, ssl_options=None, conn_attrs=None):
        """Authenticate with the MySQL server

        Authentication happens in two parts. We first send a response to the
        handshake. The MySQL server will then send either an AuthSwitchRequest
        or an error packet.

        Raises NotSupportedError when we get the old, insecure password
        reply back. Raises any error coming from MySQL.
        """
        self._ssl_active = False
        if client_flags & ClientFlag.SSL:
            packet = self._protocol.make_auth_ssl(charset=charset,
                                                  client_flags=client_flags)
            self._socket.send(packet)
            self._socket.switch_to_ssl(ssl_options.get('ca'),
                                       ssl_options.get('cert'),
                                       ssl_options.get('key'),
                                       ssl_options.get('verify_cert') or False,
                                       ssl_options.get('verify_identity') or
                                       False,
                                       ssl_options.get('cipher'),
                                       ssl_options.get('version', None))
            self._ssl_active = True

        packet = self._protocol.make_auth(
            handshake=self._handshake,
            username=username, password=password, database=database,
            charset=charset, client_flags=client_flags,
            ssl_enabled=self._ssl_active,
            auth_plugin=self._auth_plugin,
            conn_attrs=conn_attrs)
        self._socket.send(packet)
        self._auth_switch_request(username, password)

        if not (client_flags & ClientFlag.CONNECT_WITH_DB) and database:
            self.cmd_init_db(database)

        return True

    def _auth_switch_request(self, username=None, password=None):
        """Handle second part of authentication

        Raises NotSupportedError when we get the old, insecure password
        reply back. Raises any error coming from MySQL.
        """
        auth = None
        new_auth_plugin = self._auth_plugin or self._handshake["auth_plugin"]
        packet = self._socket.recv()
        if packet[4] == 254 and len(packet) == 5:
            raise errors.NotSupportedError(
                "Authentication with old (insecure) passwords "
                "is not supported. For more information, lookup "
                "Password Hashing in the latest MySQL manual")
        elif packet[4] == 254:
            # AuthSwitchRequest
            (new_auth_plugin,
             auth_data) = self._protocol.parse_auth_switch_request(packet)
            auth = get_auth_plugin(new_auth_plugin)(
                auth_data, password=password, ssl_enabled=self._ssl_active)
            response = auth.auth_response()
            self._socket.send(response)
            packet = self._socket.recv()

        if packet[4] == 1:
            auth_data = self._protocol.parse_auth_more_data(packet)
            auth = get_auth_plugin(new_auth_plugin)(
                auth_data, password=password, ssl_enabled=self._ssl_active)
            if new_auth_plugin == "caching_sha2_password":
                response = auth.auth_response()
                if response:
                    self._socket.send(response)
                packet = self._socket.recv()

        if packet[4] == 0:
            return self._handle_ok(packet)
        elif packet[4] == 255:
            raise errors.get_exception(packet)
        return None

    def _get_connection(self, prtcls=None):
        """Get connection based on configuration

        This method will return the appropriated connection object using
        the connection parameters.

        Returns subclass of MySQLBaseSocket.
        """
        conn = None
        if self.unix_socket and os.name != 'nt':
            conn = MySQLUnixSocket(unix_socket=self.unix_socket)
        else:
            conn = MySQLTCPSocket(host=self.server_host,
                                  port=self.server_port,
                                  force_ipv6=self._force_ipv6)

        conn.set_connection_timeout(self._connection_timeout)
        return conn

    def _open_connection(self):
        """Open the connection to the MySQL server

        This method sets up and opens the connection to the MySQL server.

        Raises on errors.
        """
        self._protocol = MySQLProtocol()
        self._socket = self._get_connection()
        try:
            self._socket.open_connection()
            self._do_handshake()
            self._do_auth(self._user, self._password,
                          self._database, self._client_flags, self._charset_id,
                          self._ssl, self._conn_attrs)
            self.set_converter_class(self._converter_class)
            if self._client_flags & ClientFlag.COMPRESS:
                self._socket.recv = self._socket.recv_compressed
                self._socket.send = self._socket.send_compressed
        except:
            # close socket
            self.close()
            raise

    def shutdown(self):
        """Shut down connection to MySQL Server.
        """
        if not self._socket:
            return

        try:
            self._socket.shutdown()
        except (AttributeError, errors.Error):
            pass  # Getting an exception would mean we are disconnected.

    def close(self):
        """Disconnect from the MySQL server"""
        if not self._socket:
            return

        try:
            self.cmd_quit()
        except (AttributeError, errors.Error):
            pass  # Getting an exception would mean we are disconnected.
        self._socket.close_connection()

    disconnect = close

    def _send_cmd(self, command, argument=None, packet_number=0, packet=None,
                  expect_response=True, compressed_packet_number=0):
        """Send a command to the MySQL server

        This method sends a command with an optional argument.
        If packet is not None, it will be sent and the argument will be
        ignored.

        The packet_number is optional and should usually not be used.

        Some commands might not result in the MySQL server returning
        a response. If a command does not return anything, you should
        set expect_response to False. The _send_cmd method will then
        return None instead of a MySQL packet.

        Returns a MySQL packet or None.
        """
        self.handle_unread_result()

        try:
            self._socket.send(
                self._protocol.make_command(command, packet or argument),
                packet_number, compressed_packet_number)
        except AttributeError:
            raise errors.OperationalError("MySQL Connection not available.")

        if not expect_response:
            return None
        return self._socket.recv()

    def _send_data(self, data_file, send_empty_packet=False):
        """Send data to the MySQL server

        This method accepts a file-like object and sends its data
        as is to the MySQL server. If the send_empty_packet is
        True, it will send an extra empty package (for example
        when using LOAD LOCAL DATA INFILE).

        Returns a MySQL packet.
        """
        self.handle_unread_result()

        if not hasattr(data_file, 'read'):
            raise ValueError("expecting a file-like object")

        try:
            buf = data_file.read(NET_BUFFER_LENGTH - 16)
            while buf:
                self._socket.send(buf)
                buf = data_file.read(NET_BUFFER_LENGTH - 16)
        except AttributeError:
            raise errors.OperationalError("MySQL Connection not available.")

        if send_empty_packet:
            try:
                self._socket.send(b'')
            except AttributeError:
                raise errors.OperationalError(
                    "MySQL Connection not available.")

        return self._socket.recv()

    def _handle_server_status(self, flags):
        """Handle the server flags found in MySQL packets

        This method handles the server flags send by MySQL OK and EOF
        packets. It, for example, checks whether there exists more result
        sets or whether there is an ongoing transaction.
        """
        self._have_next_result = flag_is_set(ServerFlag.MORE_RESULTS_EXISTS,
                                             flags)
        self._in_transaction = flag_is_set(ServerFlag.STATUS_IN_TRANS, flags)

    @property
    def in_transaction(self):
        """MySQL session has started a transaction"""
        return self._in_transaction

    def _handle_ok(self, packet):
        """Handle a MySQL OK packet

        This method handles a MySQL OK packet. When the packet is found to
        be an Error packet, an error will be raised. If the packet is neither
        an OK or an Error packet, errors.InterfaceError will be raised.

        Returns a dict()
        """
        if packet[4] == 0:
            ok_pkt = self._protocol.parse_ok(packet)
            self._handle_server_status(ok_pkt['status_flag'])
            return ok_pkt
        elif packet[4] == 255:
            raise errors.get_exception(packet)
        raise errors.InterfaceError('Expected OK packet')

    def _handle_eof(self, packet):
        """Handle a MySQL EOF packet

        This method handles a MySQL EOF packet. When the packet is found to
        be an Error packet, an error will be raised. If the packet is neither
        and OK or an Error packet, errors.InterfaceError will be raised.

        Returns a dict()
        """
        if packet[4] == 254:
            eof = self._protocol.parse_eof(packet)
            self._handle_server_status(eof['status_flag'])
            return eof
        elif packet[4] == 255:
            raise errors.get_exception(packet)
        raise errors.InterfaceError('Expected EOF packet')

    def _handle_load_data_infile(self, filename):
        """Handle a LOAD DATA INFILE LOCAL request"""
        try:
            data_file = open(filename, 'rb')
        except IOError:
            # Send a empty packet to cancel the operation
            try:
                self._socket.send(b'')
            except AttributeError:
                raise errors.OperationalError(
                    "MySQL Connection not available.")
            raise errors.InterfaceError(
                "File '{0}' could not be read".format(filename))

        return self._handle_ok(self._send_data(data_file,
                                               send_empty_packet=True))

    def _handle_result(self, packet):
        """Handle a MySQL Result

        This method handles a MySQL result, for example, after sending the
        query command. OK and EOF packets will be handled and returned. If
        the packet is an Error packet, an errors.Error-exception will be
        raised.

        The dictionary returned of:
        - columns: column information
        - eof: the EOF-packet information

        Returns a dict()
        """
        if not packet or len(packet) < 4:
            raise errors.InterfaceError('Empty response')
        elif packet[4] == 0:
            return self._handle_ok(packet)
        elif packet[4] == 251:
            if PY2:
                filename = str(packet[5:])
            else:
                filename = packet[5:].decode()
            return self._handle_load_data_infile(filename)
        elif packet[4] == 254:
            return self._handle_eof(packet)
        elif packet[4] == 255:
            raise errors.get_exception(packet)

        # We have a text result set
        column_count = self._protocol.parse_column_count(packet)
        if not column_count or not isinstance(column_count, int):
            raise errors.InterfaceError('Illegal result set.')

        self._columns_desc = [None,] * column_count
        for i in range(0, column_count):
            self._columns_desc[i] = self._protocol.parse_column(
                self._socket.recv(), self.python_charset)

        eof = self._handle_eof(self._socket.recv())
        self.unread_result = True
        return {'columns': self._columns_desc, 'eof': eof}

    def get_row(self, binary=False, columns=None, raw=None):
        """Get the next rows returned by the MySQL server

        This method gets one row from the result set after sending, for
        example, the query command. The result is a tuple consisting of the
        row and the EOF packet.
        If no row was available in the result set, the row data will be None.

        Returns a tuple.
        """
        (rows, eof) = self.get_rows(count=1, binary=binary, columns=columns,
                                    raw=raw)
        if rows:
            return (rows[0], eof)
        return (None, eof)

    def get_rows(self, count=None, binary=False, columns=None, raw=None,
                 prep_stmt=None):
        """Get all rows returned by the MySQL server

        This method gets all rows returned by the MySQL server after sending,
        for example, the query command. The result is a tuple consisting of
        a list of rows and the EOF packet.

        Returns a tuple()
        """
        if raw is None:
            raw = self._raw

        if not self.unread_result:
            raise errors.InternalError("No result set available.")

        try:
            if binary:
                charset = self.charset
                if charset == 'utf8mb4':
                    charset = 'utf8'
                rows = self._protocol.read_binary_result(
                    self._socket, columns, count, charset)
            else:
                rows = self._protocol.read_text_result(self._socket,
                                                       self._server_version,
                                                       count=count)
        except errors.Error as err:
            self.unread_result = False
            raise err

        rows, eof_p = rows

        if not (binary or raw) and self._columns_desc is not None and rows \
           and hasattr(self, 'converter'):
            row_to_python = self.converter.row_to_python
            rows = [row_to_python(row, self._columns_desc) for row in rows]

        if eof_p is not None:
            self._handle_server_status(eof_p['status_flag'] if 'status_flag' in
                                       eof_p else eof_p['server_status'])
            self.unread_result = False

        return rows, eof_p

    def consume_results(self):
        """Consume results
        """
        if self.unread_result:
            self.get_rows()

    def cmd_init_db(self, database):
        """Change the current database

        This method changes the current (default) database by sending the
        INIT_DB command. The result is a dictionary containing the OK packet
        information.

        Returns a dict()
        """
        return self._handle_ok(
            self._send_cmd(ServerCmd.INIT_DB, database.encode('utf-8')))

    def cmd_query(self, query, raw=False, buffered=False, raw_as_string=False):
        """Send a query to the MySQL server

        This method send the query to the MySQL server and returns the result.

        If there was a text result, a tuple will be returned consisting of
        the number of columns and a list containing information about these
        columns.

        When the query doesn't return a text result, the OK or EOF packet
        information as dictionary will be returned. In case the result was
        an error, exception errors.Error will be raised.

        Returns a tuple()
        """
        if not isinstance(query, bytes):
            query = query.encode('utf-8')
        result = self._handle_result(self._send_cmd(ServerCmd.QUERY, query))

        if self._have_next_result:
            raise errors.InterfaceError(
                'Use cmd_query_iter for statements with multiple queries.')

        return result

    def cmd_query_iter(self, statements):
        """Send one or more statements to the MySQL server

        Similar to the cmd_query method, but instead returns a generator
        object to iterate through results. It sends the statements to the
        MySQL server and through the iterator you can get the results.

        statement = 'SELECT 1; INSERT INTO t1 VALUES (); SELECT 2'
        for result in cnx.cmd_query(statement, iterate=True):
            if 'columns' in result:
                columns = result['columns']
                rows = cnx.get_rows()
            else:
                # do something useful with INSERT result

        Returns a generator.
        """
        if not isinstance(statements, bytearray):
            if isstr(statements) and isinstance(statements, UNICODE_TYPES):
                statements = statements.encode('utf8')
            statements = bytearray(statements)

        # Handle the first query result
        yield self._handle_result(self._send_cmd(ServerCmd.QUERY, statements))

        # Handle next results, if any
        while self._have_next_result:
            self.handle_unread_result()
            yield self._handle_result(self._socket.recv())

    def cmd_refresh(self, options):
        """Send the Refresh command to the MySQL server

        This method sends the Refresh command to the MySQL server. The options
        argument should be a bitwise value using constants.RefreshOption.
        Usage example:
         RefreshOption = mysql.connector.RefreshOption
         refresh = RefreshOption.LOG | RefreshOption.THREADS
         cnx.cmd_refresh(refresh)

        The result is a dictionary with the OK packet information.

        Returns a dict()
        """
        return self._handle_ok(
            self._send_cmd(ServerCmd.REFRESH, int4store(options)))

    def cmd_quit(self):
        """Close the current connection with the server

        This method sends the QUIT command to the MySQL server, closing the
        current connection. Since the no response can be returned to the
        client, cmd_quit() will return the packet it send.

        Returns a str()
        """
        self.handle_unread_result()

        packet = self._protocol.make_command(ServerCmd.QUIT)
        self._socket.send(packet, 0, 0)
        return packet

    def cmd_shutdown(self, shutdown_type=None):
        """Shut down the MySQL Server

        This method sends the SHUTDOWN command to the MySQL server and is only
        possible if the current user has SUPER privileges. The result is a
        dictionary containing the OK packet information.

        Note: Most applications and scripts do not the SUPER privilege.

        Returns a dict()
        """
        if shutdown_type:
            if not ShutdownType.get_info(shutdown_type):
                raise errors.InterfaceError("Invalid shutdown type")
            atype = shutdown_type
        else:
            atype = ShutdownType.SHUTDOWN_DEFAULT
        return self._handle_eof(self._send_cmd(ServerCmd.SHUTDOWN,
                                               int4store(atype)))

    def cmd_statistics(self):
        """Send the statistics command to the MySQL Server

        This method sends the STATISTICS command to the MySQL server. The
        result is a dictionary with various statistical information.

        Returns a dict()
        """
        self.handle_unread_result()

        packet = self._protocol.make_command(ServerCmd.STATISTICS)
        self._socket.send(packet, 0, 0)
        return self._protocol.parse_statistics(self._socket.recv())

    def cmd_process_kill(self, mysql_pid):
        """Kill a MySQL process

        This method send the PROCESS_KILL command to the server along with
        the process ID. The result is a dictionary with the OK packet
        information.

        Returns a dict()
        """
        return self._handle_ok(
            self._send_cmd(ServerCmd.PROCESS_KILL, int4store(mysql_pid)))

    def cmd_debug(self):
        """Send the DEBUG command

        This method sends the DEBUG command to the MySQL server, which
        requires the MySQL user to have SUPER privilege. The output will go
        to the MySQL server error log and the result of this method is a
        dictionary with EOF packet information.

        Returns a dict()
        """
        return self._handle_eof(self._send_cmd(ServerCmd.DEBUG))

    def cmd_ping(self):
        """Send the PING command

        This method sends the PING command to the MySQL server. It is used to
        check if the the connection is still valid. The result of this
        method is dictionary with OK packet information.

        Returns a dict()
        """
        return self._handle_ok(self._send_cmd(ServerCmd.PING))

    def cmd_change_user(self, username='', password='', database='',
                        charset=45):
        """Change the current logged in user

        This method allows to change the current logged in user information.
        The result is a dictionary with OK packet information.

        Returns a dict()
        """
        self.handle_unread_result()

        if self._compress:
            raise errors.NotSupportedError("Change user is not supported with "
                                           "compression.")

        packet = self._protocol.make_change_user(
            handshake=self._handshake,
            username=username, password=password, database=database,
            charset=charset, client_flags=self._client_flags,
            ssl_enabled=self._ssl_active,
            auth_plugin=self._auth_plugin)
        self._socket.send(packet, 0, 0)

        ok_packet = self._auth_switch_request(username, password)

        try:
            if not (self._client_flags & ClientFlag.CONNECT_WITH_DB) \
                    and database:
                self.cmd_init_db(database)
        except:
            raise

        self._charset_id = charset
        self._post_connection()

        return ok_packet

    @property
    def database(self):
        """Get the current database"""
        return self.info_query("SELECT DATABASE()")[0]

    @database.setter
    def database(self, value):  # pylint: disable=W0221
        """Set the current database"""
        self.cmd_query("USE %s" % value)

    def is_connected(self):
        """Reports whether the connection to MySQL Server is available

        This method checks whether the connection to MySQL is available.
        It is similar to ping(), but unlike the ping()-method, either True
        or False is returned and no exception is raised.

        Returns True or False.
        """
        try:
            self.cmd_ping()
        except:
            return False  # This method does not raise
        return True

    def reset_session(self, user_variables=None, session_variables=None):
        """Clears the current active session

        This method resets the session state, if the MySQL server is 5.7.3
        or later active session will be reset without re-authenticating.
        For other server versions session will be reset by re-authenticating.

        It is possible to provide a sequence of variables and their values to
        be set after clearing the session. This is possible for both user
        defined variables and session variables.
        This method takes two arguments user_variables and session_variables
        which are dictionaries.

        Raises OperationalError if not connected, InternalError if there are
        unread results and InterfaceError on errors.
        """
        if not self.is_connected():
            raise errors.OperationalError("MySQL Connection not available.")

        try:
            self.cmd_reset_connection()
        except errors.NotSupportedError:
            self.cmd_change_user(self._user, self._password,
                                 self._database, self._charset_id)

        cur = self.cursor()
        if user_variables:
            for key, value in user_variables.items():
                cur.execute("SET @`{0}` = %s".format(key), (value,))
        if session_variables:
            for key, value in session_variables.items():
                cur.execute("SET SESSION `{0}` = %s".format(key), (value,))

    def reconnect(self, attempts=1, delay=0):
        """Attempt to reconnect to the MySQL server

        The argument attempts should be the number of times a reconnect
        is tried. The delay argument is the number of seconds to wait between
        each retry.

        You may want to set the number of attempts higher and use delay when
        you expect the MySQL server to be down for maintenance or when you
        expect the network to be temporary unavailable.

        Raises InterfaceError on errors.
        """
        counter = 0
        while counter != attempts:
            counter = counter + 1
            try:
                self.disconnect()
                self.connect()
                if self.is_connected():
                    break
            except Exception as err:  # pylint: disable=W0703
                if counter == attempts:
                    msg = "Can not reconnect to MySQL after {0} "\
                          "attempt(s): {1}".format(attempts, str(err))
                    raise errors.InterfaceError(msg)
            if delay > 0:
                time.sleep(delay)

    def ping(self, reconnect=False, attempts=1, delay=0):
        """Check availability of the MySQL server

        When reconnect is set to True, one or more attempts are made to try
        to reconnect to the MySQL server using the reconnect()-method.

        delay is the number of seconds to wait between each retry.

        When the connection is not available, an InterfaceError is raised. Use
        the is_connected()-method if you just want to check the connection
        without raising an error.

        Raises InterfaceError on errors.
        """
        try:
            self.cmd_ping()
        except:
            if reconnect:
                self.reconnect(attempts=attempts, delay=delay)
            else:
                raise errors.InterfaceError("Connection to MySQL is"
                                            " not available.")

    @property
    def connection_id(self):
        """MySQL connection ID"""
        try:
            return self._handshake['server_threadid']
        except KeyError:
            return None

    def cursor(self, buffered=None, raw=None, prepared=None, cursor_class=None,
               dictionary=None, named_tuple=None):
        """Instantiates and returns a cursor

        By default, MySQLCursor is returned. Depending on the options
        while connecting, a buffered and/or raw cursor is instantiated
        instead. Also depending upon the cursor options, rows can be
        returned as dictionary or named tuple.

        Dictionary and namedtuple based cursors are available with buffered
        output but not raw.

        It is possible to also give a custom cursor through the
        cursor_class parameter, but it needs to be a subclass of
        mysql.connector.cursor.CursorBase.

        Raises ProgrammingError when cursor_class is not a subclass of
        CursorBase. Raises ValueError when cursor is not available.

        Returns a cursor-object
        """
        self.handle_unread_result()

        if not self.is_connected():
            raise errors.OperationalError("MySQL Connection not available.")
        if cursor_class is not None:
            if not issubclass(cursor_class, CursorBase):
                raise errors.ProgrammingError(
                    "Cursor class needs be to subclass of cursor.CursorBase")
            return (cursor_class)(self)

        buffered = buffered if buffered is not None else self._buffered
        raw = raw if raw is not None else self._raw

        cursor_type = 0
        if buffered is True:
            cursor_type |= 1
        if raw is True:
            cursor_type |= 2
        if dictionary is True:
            cursor_type |= 4
        if named_tuple is True:
            cursor_type |= 8
        if prepared is True:
            cursor_type |= 16

        types = {
            0: MySQLCursor,  # 0
            1: MySQLCursorBuffered,
            2: MySQLCursorRaw,
            3: MySQLCursorBufferedRaw,
            4: MySQLCursorDict,
            5: MySQLCursorBufferedDict,
            8: MySQLCursorNamedTuple,
            9: MySQLCursorBufferedNamedTuple,
            16: MySQLCursorPrepared
        }
        try:
            return (types[cursor_type])(self)
        except KeyError:
            args = ('buffered', 'raw', 'dictionary', 'named_tuple', 'prepared')
            raise ValueError('Cursor not available with given criteria: ' +
                             ', '.join([args[i] for i in range(5)
                                        if cursor_type & (1 << i) != 0]))

    def commit(self):
        """Commit current transaction"""
        self._execute_query("COMMIT")

    def rollback(self):
        """Rollback current transaction"""
        if self.unread_result:
            self.get_rows()

        self._execute_query("ROLLBACK")

    def _execute_query(self, query):
        """Execute a query

        This method simply calls cmd_query() after checking for unread
        result. If there are still unread result, an errors.InterfaceError
        is raised. Otherwise whatever cmd_query() returns is returned.

        Returns a dict()
        """
        self.handle_unread_result()
        self.cmd_query(query)

    def info_query(self, query):
        """Send a query which only returns 1 row"""
        cursor = self.cursor(buffered=True)
        cursor.execute(query)
        return cursor.fetchone()

    def _handle_binary_ok(self, packet):
        """Handle a MySQL Binary Protocol OK packet

        This method handles a MySQL Binary Protocol OK packet. When the
        packet is found to be an Error packet, an error will be raised. If
        the packet is neither an OK or an Error packet, errors.InterfaceError
        will be raised.

        Returns a dict()
        """
        if packet[4] == 0:
            return self._protocol.parse_binary_prepare_ok(packet)
        elif packet[4] == 255:
            raise errors.get_exception(packet)
        raise errors.InterfaceError('Expected Binary OK packet')

    def _handle_binary_result(self, packet):
        """Handle a MySQL Result

        This method handles a MySQL result, for example, after sending the
        query command. OK and EOF packets will be handled and returned. If
        the packet is an Error packet, an errors.Error-exception will be
        raised.

        The tuple returned by this method consist of:
        - the number of columns in the result,
        - a list of tuples with information about the columns,
        - the EOF packet information as a dictionary.

        Returns tuple() or dict()
        """
        if not packet or len(packet) < 4:
            raise errors.InterfaceError('Empty response')
        elif packet[4] == 0:
            return self._handle_ok(packet)
        elif packet[4] == 254:
            return self._handle_eof(packet)
        elif packet[4] == 255:
            raise errors.get_exception(packet)

        # We have a binary result set
        column_count = self._protocol.parse_column_count(packet)
        if not column_count or not isinstance(column_count, int):
            raise errors.InterfaceError('Illegal result set.')

        columns = [None] * column_count
        for i in range(0, column_count):
            columns[i] = self._protocol.parse_column(
                self._socket.recv(), self.python_charset)

        eof = self._handle_eof(self._socket.recv())
        return (column_count, columns, eof)

    def cmd_stmt_fetch(self, statement_id, rows=1):
        """Fetch a MySQL statement Result Set

        This method will send the FETCH command to MySQL together with the
        given statement id and the number of rows to fetch.
        """
        packet = self._protocol.make_stmt_fetch(statement_id, rows)
        self.unread_result = False
        self._send_cmd(ServerCmd.STMT_FETCH, packet, expect_response=False)
        self.unread_result = True

    def cmd_stmt_prepare(self, statement):
        """Prepare a MySQL statement

        This method will send the PREPARE command to MySQL together with the
        given statement.

        Returns a dict()
        """
        packet = self._send_cmd(ServerCmd.STMT_PREPARE, statement)
        result = self._handle_binary_ok(packet)

        result['columns'] = []
        result['parameters'] = []
        if result['num_params'] > 0:
            for _ in range(0, result['num_params']):
                result['parameters'].append(
                    self._protocol.parse_column(self._socket.recv(),
                                                self.python_charset))
            self._handle_eof(self._socket.recv())
        if result['num_columns'] > 0:
            for _ in range(0, result['num_columns']):
                result['columns'].append(
                    self._protocol.parse_column(self._socket.recv(),
                                                self.python_charset))
            self._handle_eof(self._socket.recv())

        return result

    def cmd_stmt_execute(self, statement_id, data=(), parameters=(), flags=0):
        """Execute a prepared MySQL statement"""
        parameters = list(parameters)
        long_data_used = {}

        if data:
            for param_id, _ in enumerate(parameters):
                if isinstance(data[param_id], IOBase):
                    binary = True
                    try:
                        binary = 'b' not in data[param_id].mode
                    except AttributeError:
                        pass
                    self.cmd_stmt_send_long_data(statement_id, param_id,
                                                 data[param_id])
                    long_data_used[param_id] = (binary,)

        execute_packet = self._protocol.make_stmt_execute(
            statement_id, data, tuple(parameters), flags,
            long_data_used, self.charset)
        packet = self._send_cmd(ServerCmd.STMT_EXECUTE, packet=execute_packet)
        result = self._handle_binary_result(packet)
        return result

    def cmd_stmt_close(self, statement_id):
        """Deallocate a prepared MySQL statement

        This method deallocates the prepared statement using the
        statement_id. Note that the MySQL server does not return
        anything.
        """
        self._send_cmd(ServerCmd.STMT_CLOSE, int4store(statement_id),
                       expect_response=False)

    def cmd_stmt_send_long_data(self, statement_id, param_id, data):
        """Send data for a column

        This methods send data for a column (for example BLOB) for statement
        identified by statement_id. The param_id indicate which parameter
        the data belongs too.
        The data argument should be a file-like object.

        Since MySQL does not send anything back, no error is raised. When
        the MySQL server is not reachable, an OperationalError is raised.

        cmd_stmt_send_long_data should be called before cmd_stmt_execute.

        The total bytes send is returned.

        Returns int.
        """
        chunk_size = 8192
        total_sent = 0
        # pylint: disable=W0212
        prepare_packet = self._protocol._prepare_stmt_send_long_data
        # pylint: enable=W0212
        try:
            buf = data.read(chunk_size)
            while buf:
                packet = prepare_packet(statement_id, param_id, buf)
                self._send_cmd(ServerCmd.STMT_SEND_LONG_DATA, packet=packet,
                               expect_response=False)
                total_sent += len(buf)
                buf = data.read(chunk_size)
        except AttributeError:
            raise errors.OperationalError("MySQL Connection not available.")

        return total_sent

    def cmd_stmt_reset(self, statement_id):
        """Reset data for prepared statement sent as long data

        The result is a dictionary with OK packet information.

        Returns a dict()
        """
        self._handle_ok(self._send_cmd(ServerCmd.STMT_RESET,
                                       int4store(statement_id)))

    def cmd_reset_connection(self):
        """Resets the session state without re-authenticating

        Works only for MySQL server 5.7.3 or later.
        The result is a dictionary with OK packet information.

        Returns a dict()
        """
        if self._server_version < (5, 7, 3):
            raise errors.NotSupportedError("MySQL version 5.7.2 and "
                                           "earlier does not support "
                                           "COM_RESET_CONNECTION.")
        self._handle_ok(self._send_cmd(ServerCmd.RESET_CONNECTION))
        self._post_connection()

    def handle_unread_result(self):
        """Check whether there is an unread result"""
        if self.can_consume_results:
            self.consume_results()
        elif self.unread_result:
            raise errors.InternalError("Unread result found")
