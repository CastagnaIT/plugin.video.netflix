# MySQL Connector/Python - MySQL driver written in Python.

import django
import subprocess

from django.db.backends.base.client import BaseDatabaseClient


class DatabaseClient(BaseDatabaseClient):
    executable_name = 'mysql'

    @classmethod
    def settings_to_cmd_args(cls, settings_dict):
        args = [cls.executable_name]

        db = settings_dict['OPTIONS'].get('database', settings_dict['NAME'])
        user = settings_dict['OPTIONS'].get('user',
                                            settings_dict['USER'])
        passwd = settings_dict['OPTIONS'].get('password',
                                              settings_dict['PASSWORD'])
        host = settings_dict['OPTIONS'].get('host', settings_dict['HOST'])
        port = settings_dict['OPTIONS'].get('port', settings_dict['PORT'])
        defaults_file = settings_dict['OPTIONS'].get('read_default_file')

        # --defaults-file should always be the first option
        if defaults_file:
            args.append("--defaults-file={0}".format(defaults_file))

        # We force SQL_MODE to TRADITIONAL
        args.append("--init-command=SET @@session.SQL_MODE=TRADITIONAL")

        if user:
            args.append("--user={0}".format(user))
        if passwd:
            args.append("--password={0}".format(passwd))

        if host:
            if '/' in host:
                args.append("--socket={0}".format(host))
            else:
                args.append("--host={0}".format(host))

        if port:
            args.append("--port={0}".format(port))

        if db:
            args.append("--database={0}".format(db))

        return args

    def runshell(self):
        args = DatabaseClient.settings_to_cmd_args(
            self.connection.settings_dict)
        subprocess.call(args)
