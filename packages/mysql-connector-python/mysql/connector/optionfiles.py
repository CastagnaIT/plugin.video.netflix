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

"""Implements parser to parse MySQL option files.
"""

import codecs
import io
import os
import re

from .catch23 import PY2
from .constants import DEFAULT_CONFIGURATION, CNX_POOL_ARGS

# pylint: disable=F0401
if PY2:
    from ConfigParser import SafeConfigParser, MissingSectionHeaderError
else:
    from configparser import (ConfigParser as SafeConfigParser,
                              MissingSectionHeaderError)
# pylint: enable=F0401

DEFAULT_EXTENSIONS = {
    'nt': ('ini', 'cnf'),
    'posix': ('cnf',)
}


def read_option_files(**config):
    """
    Read option files for connection parameters.

    Checks if connection arguments contain option file arguments, and then
    reads option files accordingly.
    """
    if 'option_files' in config:
        try:
            if isinstance(config['option_groups'], str):
                config['option_groups'] = [config['option_groups']]
            groups = config['option_groups']
            del config['option_groups']
        except KeyError:
            groups = ['client', 'connector_python']

        if isinstance(config['option_files'], str):
            config['option_files'] = [config['option_files']]
        option_parser = MySQLOptionsParser(list(config['option_files']),
                                           keep_dashes=False)
        del config['option_files']

        config_from_file = option_parser.get_groups_as_dict_with_priority(
            *groups)
        config_options = {}
        for group in groups:
            try:
                for option, value in config_from_file[group].items():
                    try:
                        if option == 'socket':
                            option = 'unix_socket'

                        if (option not in CNX_POOL_ARGS and
                                option != 'failover'):
                            # pylint: disable=W0104
                            DEFAULT_CONFIGURATION[option]
                            # pylint: enable=W0104

                        if (option not in config_options or
                                config_options[option][1] <= value[1]):
                            config_options[option] = value
                    except KeyError:
                        if group == 'connector_python':
                            raise AttributeError("Unsupported argument "
                                                 "'{0}'".format(option))
            except KeyError:
                continue

        not_evaluate = ('password', 'passwd')
        for option, value in config_options.items():
            if option not in config:
                try:
                    if option in not_evaluate:
                        config[option] = value[0]
                    else:
                        config[option] = eval(value[0])  # pylint: disable=W0123
                except (NameError, SyntaxError):
                    config[option] = value[0]

    return config


class MySQLOptionsParser(SafeConfigParser):  # pylint: disable=R0901
    """This class implements methods to parse MySQL option files"""

    def __init__(self, files=None, keep_dashes=True):  # pylint: disable=W0231
        """Initialize

        If defaults is True, default option files are read first

        Raises ValueError if defaults is set to True but defaults files
        cannot be found.
        """

        # Regular expression to allow options with no value(For Python v2.6)
        self.OPTCRE = re.compile(           # pylint: disable=C0103
            r'(?P<option>[^:=\s][^:=]*)'
            r'\s*(?:'
            r'(?P<vi>[:=])\s*'
            r'(?P<value>.*))?$'
        )

        self._options_dict = {}

        if PY2:
            SafeConfigParser.__init__(self)
        else:
            SafeConfigParser.__init__(self, strict=False)

        self.default_extension = DEFAULT_EXTENSIONS[os.name]
        self.keep_dashes = keep_dashes

        if not files:
            raise ValueError('files argument should be given')
        if isinstance(files, str):
            self.files = [files]
        else:
            self.files = files

        self._parse_options(list(self.files))
        self._sections = self.get_groups_as_dict()

    def optionxform(self, optionstr):
        """Converts option strings

        Converts option strings to lower case and replaces dashes(-) with
        underscores(_) if keep_dashes variable is set.
        """
        if not self.keep_dashes:
            optionstr = optionstr.replace('-', '_')
        return optionstr.lower()

    def _parse_options(self, files):
        """Parse options from files given as arguments.
         This method checks for !include or !inculdedir directives and if there
         is any, those files included by these directives are also parsed
         for options.

        Raises ValueError if any of the included or file given in arguments
        is not readable.
        """
        index = 0
        err_msg = "Option file '{0}' being included again in file '{1}'"

        for file_ in files:
            try:
                if file_ in files[index+1:]:
                    raise ValueError("Same option file '{0}' occurring more "
                                     "than once in the list".format(file_))
                with open(file_, 'r') as op_file:
                    for line in op_file.readlines():
                        if line.startswith('!includedir'):
                            _, dir_path = line.split(None, 1)
                            dir_path = dir_path.strip()
                            for entry in os.listdir(dir_path):
                                entry = os.path.join(dir_path, entry)
                                if entry in files:
                                    raise ValueError(err_msg.format(
                                        entry, file_))
                                if (os.path.isfile(entry) and
                                        entry.endswith(self.default_extension)):
                                    files.insert(index+1, entry)

                        elif line.startswith('!include'):
                            _, filename = line.split(None, 1)
                            filename = filename.strip()
                            if filename in files:
                                raise ValueError(err_msg.format(
                                    filename, file_))
                            files.insert(index+1, filename)

                    index += 1

            except (IOError, OSError) as exc:
                raise ValueError("Failed reading file '{0}': {1}".format(
                    file_, str(exc)))

        read_files = self.read(files)
        not_read_files = set(files) - set(read_files)
        if not_read_files:
            raise ValueError("File(s) {0} could not be read.".format(
                ', '.join(not_read_files)))

    def read(self, filenames):  # pylint: disable=W0221
        """Read and parse a filename or a list of filenames.

        Overridden from ConfigParser and modified so as to allow options
        which are not inside any section header

        Return list of successfully read files.
        """
        if isinstance(filenames, str):
            filenames = [filenames]
        read_ok = []
        for priority, filename in enumerate(filenames):
            try:
                out_file = io.StringIO()
                for line in codecs.open(filename, encoding='utf-8'):
                    line = line.strip()
                    match_obj = self.OPTCRE.match(line)
                    if not self.SECTCRE.match(line) and match_obj:
                        optname, delimiter, optval = match_obj.group('option',
                                                                     'vi',
                                                                     'value')
                        if optname and not optval and not delimiter:
                            out_file.write(line + "=\n")
                        else:
                            out_file.write(line + '\n')
                    else:
                        out_file.write(line + '\n')
                out_file.seek(0)
            except IOError:
                continue
            try:
                self._read(out_file, filename)
                for group in self._sections.keys():
                    try:
                        self._options_dict[group]
                    except KeyError:
                        self._options_dict[group] = {}
                    for option, value in self._sections[group].items():
                        self._options_dict[group][option] = (value, priority)

                self._sections = self._dict()

            except MissingSectionHeaderError:
                self._read(out_file, filename)
            out_file.close()
            read_ok.append(filename)
        return read_ok

    def get_groups(self, *args):
        """Returns options as a dictionary.

        Returns options from all the groups specified as arguments, returns
        the options from all groups if no argument provided. Options are
        overridden when they are found in the next group.

        Returns a dictionary
        """
        if not args:
            args = self._options_dict.keys()

        options = {}
        priority = {}
        for group in args:
            try:
                for option, value in [(key, value,) for key, value in
                                      self._options_dict[group].items() if
                                      key != "__name__" and
                                      not key.startswith("!")]:
                    if option not in options or priority[option] <= value[1]:
                        priority[option] = value[1]
                        options[option] = value[0]
            except KeyError:
                pass

        return options

    def get_groups_as_dict_with_priority(self, *args): # pylint: disable=C0103
        """Returns options as dictionary of dictionaries.

        Returns options from all the groups specified as arguments. For each
        group the option are contained in a dictionary. The order in which
        the groups are specified is unimportant. Also options are not
        overridden in between the groups.

        The value is a tuple with two elements, first being the actual value
        and second is the priority of the value which is higher for a value
        read from a higher priority file.

        Returns an dictionary of dictionaries
        """
        if not args:
            args = self._options_dict.keys()

        options = dict()
        for group in args:
            try:
                options[group] = dict((key, value,) for key, value in
                                      self._options_dict[group].items() if
                                      key != "__name__" and
                                      not key.startswith("!"))
            except KeyError:
                pass

        return options

    def get_groups_as_dict(self, *args):
        """Returns options as dictionary of dictionaries.

        Returns options from all the groups specified as arguments. For each
        group the option are contained in a dictionary. The order in which
        the groups are specified is unimportant. Also options are not
        overridden in between the groups.

        Returns an dictionary of dictionaries
        """
        if not args:
            args = self._options_dict.keys()

        options = dict()
        for group in args:
            try:
                options[group] = dict((key, value[0],) for key, value in
                                      self._options_dict[group].items() if
                                      key != "__name__" and
                                      not key.startswith("!"))
            except KeyError:
                pass

        return options
