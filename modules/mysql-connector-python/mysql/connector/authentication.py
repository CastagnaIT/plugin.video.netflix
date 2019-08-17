# Copyright (c) 2014, 2018, Oracle and/or its affiliates. All rights reserved.
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

"""Implementing support for MySQL Authentication Plugins"""

from hashlib import sha1, sha256
import struct

from . import errors
from .catch23 import PY2, isstr, UNICODE_TYPES


class BaseAuthPlugin(object):
    """Base class for authentication plugins


    Classes inheriting from BaseAuthPlugin should implement the method
    prepare_password(). When instantiating, auth_data argument is
    required. The username, password and database are optional. The
    ssl_enabled argument can be used to tell the plugin whether SSL is
    active or not.

    The method auth_response() method is used to retrieve the password
    which was prepared by prepare_password().
    """

    requires_ssl = False
    plugin_name = ''

    def __init__(self, auth_data, username=None, password=None, database=None,
                 ssl_enabled=False):
        """Initialization"""
        self._auth_data = auth_data
        self._username = username
        self._password = password
        self._database = database
        self._ssl_enabled = ssl_enabled

    def prepare_password(self):
        """Prepares and returns password to be send to MySQL

        This method needs to be implemented by classes inheriting from
        this class. It is used by the auth_response() method.

        Raises NotImplementedError.
        """
        raise NotImplementedError

    def auth_response(self):
        """Returns the prepared password to send to MySQL

        Raises InterfaceError on errors. For example, when SSL is required
        by not enabled.

        Returns str
        """
        if self.requires_ssl and not self._ssl_enabled:
            raise errors.InterfaceError("{name} requires SSL".format(
                name=self.plugin_name))
        return self.prepare_password()


class MySQLNativePasswordAuthPlugin(BaseAuthPlugin):
    """Class implementing the MySQL Native Password authentication plugin"""

    requires_ssl = False
    plugin_name = 'mysql_native_password'

    def prepare_password(self):
        """Prepares and returns password as native MySQL 4.1+ password"""
        if not self._auth_data:
            raise errors.InterfaceError("Missing authentication data (seed)")

        if not self._password:
            return b''
        password = self._password

        if isstr(self._password):
            password = self._password.encode('utf-8')
        else:
            password = self._password

        if PY2:
            password = buffer(password)  # pylint: disable=E0602
            try:
                auth_data = buffer(self._auth_data)  # pylint: disable=E0602
            except TypeError:
                raise errors.InterfaceError("Authentication data incorrect")
        else:
            password = password
            auth_data = self._auth_data

        hash4 = None
        try:
            hash1 = sha1(password).digest()
            hash2 = sha1(hash1).digest()
            hash3 = sha1(auth_data + hash2).digest()
            if PY2:
                xored = [ord(h1) ^ ord(h3) for (h1, h3) in zip(hash1, hash3)]
            else:
                xored = [h1 ^ h3 for (h1, h3) in zip(hash1, hash3)]
            hash4 = struct.pack('20B', *xored)
        except Exception as exc:
            raise errors.InterfaceError(
                "Failed scrambling password; {0}".format(exc))

        return hash4


class MySQLClearPasswordAuthPlugin(BaseAuthPlugin):
    """Class implementing the MySQL Clear Password authentication plugin"""

    requires_ssl = True
    plugin_name = 'mysql_clear_password'

    def prepare_password(self):
        """Returns password as as clear text"""
        if not self._password:
            return b'\x00'
        password = self._password

        if PY2:
            if isinstance(password, unicode):  # pylint: disable=E0602
                password = password.encode('utf8')
        elif isinstance(password, str):
            password = password.encode('utf8')

        return password + b'\x00'


class MySQLSHA256PasswordAuthPlugin(BaseAuthPlugin):
    """Class implementing the MySQL SHA256 authentication plugin

    Note that encrypting using RSA is not supported since the Python
    Standard Library does not provide this OpenSSL functionality.
    """

    requires_ssl = True
    plugin_name = 'sha256_password'

    def prepare_password(self):
        """Returns password as as clear text"""
        if not self._password:
            return b'\x00'
        password = self._password

        if PY2:
            if isinstance(password, unicode):  # pylint: disable=E0602
                password = password.encode('utf8')
        elif isinstance(password, str):
            password = password.encode('utf8')

        return password + b'\x00'


class MySQLCachingSHA2PasswordAuthPlugin(BaseAuthPlugin):
    """Class implementing the MySQL caching_sha2_password authentication plugin

    Note that encrypting using RSA is not supported since the Python
    Standard Library does not provide this OpenSSL functionality.
    """
    requires_ssl = False
    plugin_name = 'caching_sha2_password'
    perform_full_authentication = 4
    fast_auth_success = 3

    def _scramble(self):
        """ Returns a scramble of the password using a Nonce sent by the
        server.

        The scramble is of the form:
        XOR(SHA2(password), SHA2(SHA2(SHA2(password)), Nonce))
        """
        if not self._auth_data:
            raise errors.InterfaceError("Missing authentication data (seed)")

        if not self._password:
            return b''

        password = self._password.encode('utf-8') \
            if isinstance(self._password, UNICODE_TYPES) else self._password

        if PY2:
            password = buffer(password)  # pylint: disable=E0602
            try:
                auth_data = buffer(self._auth_data)  # pylint: disable=E0602
            except TypeError:
                raise errors.InterfaceError("Authentication data incorrect")
        else:
            password = password
            auth_data = self._auth_data

        hash1 = sha256(password).digest()
        hash2 = sha256()
        hash2.update(sha256(hash1).digest())
        hash2.update(auth_data)
        hash2 = hash2.digest()
        if PY2:
            xored = [ord(h1) ^ ord(h2) for (h1, h2) in zip(hash1, hash2)]
        else:
            xored = [h1 ^ h2 for (h1, h2) in zip(hash1, hash2)]
        hash3 = struct.pack('32B', *xored)

        return hash3

    def prepare_password(self):
        if len(self._auth_data) > 1:
            return self._scramble()
        elif self._auth_data[0] == self.perform_full_authentication:
            return self._full_authentication()
        return None

    def _full_authentication(self):
        """Returns password as as clear text"""
        if not self._ssl_enabled:
            raise errors.InterfaceError("{name} requires SSL".format(
                name=self.plugin_name))

        if not self._password:
            return b'\x00'
        password = self._password

        if PY2:
            if isinstance(password, unicode):  # pylint: disable=E0602
                password = password.encode('utf8')
        elif isinstance(password, str):
            password = password.encode('utf8')

        return password + b'\x00'


def get_auth_plugin(plugin_name):
    """Return authentication class based on plugin name

    This function returns the class for the authentication plugin plugin_name.
    The returned class is a subclass of BaseAuthPlugin.

    Raises errors.NotSupportedError when plugin_name is not supported.

    Returns subclass of BaseAuthPlugin.
    """
    for authclass in BaseAuthPlugin.__subclasses__():  # pylint: disable=E1101
        if authclass.plugin_name == plugin_name:
            return authclass

    raise errors.NotSupportedError(
        "Authentication plugin '{0}' is not supported".format(plugin_name))
