# MySQL Connector/Python - MySQL driver written in Python.

import django
from django.db import models

from django.db.backends.base.creation import BaseDatabaseCreation
from django.db.backends.utils import truncate_name

class DatabaseCreation(BaseDatabaseCreation):
    """Maps Django Field object with MySQL data types
    """
    def __init__(self, connection):
        super(DatabaseCreation, self).__init__(connection)

    def sql_table_creation_suffix(self):
        suffix = []
        test_settings = self.connection.settings_dict['TEST']
        if test_settings['CHARSET']:
            suffix.append('CHARACTER SET %s' % test_settings['CHARSET'])
        if test_settings['COLLATION']:
            suffix.append('COLLATE %s' % test_settings['COLLATION'])

        return ' '.join(suffix)

    def sql_for_inline_foreign_key_references(self, model, field,
                                              known_models, style):
        "All inline references are pending under MySQL"
        return [], True

    def sql_for_inline_many_to_many_references(self, model, field, style):
        opts = model._meta
        qn = self.connection.ops.quote_name

        columndef = '    {column} {type} {options},'
        table_output = [
            columndef.format(
                column=style.SQL_FIELD(qn(field.m2m_column_name())),
                type=style.SQL_COLTYPE(models.ForeignKey(model).db_type(
                    connection=self.connection)),
                options=style.SQL_KEYWORD('NOT NULL')
            ),
            columndef.format(
                column=style.SQL_FIELD(qn(field.m2m_reverse_name())),
                type=style.SQL_COLTYPE(models.ForeignKey(field.rel.to).db_type(
                    connection=self.connection)),
                options=style.SQL_KEYWORD('NOT NULL')
            ),
        ]

        deferred = [
            (field.m2m_db_table(), field.m2m_column_name(), opts.db_table,
                opts.pk.column),
            (field.m2m_db_table(), field.m2m_reverse_name(),
                field.rel.to._meta.db_table, field.rel.to._meta.pk.column)
        ]
        return table_output, deferred

    def sql_destroy_indexes_for_fields(self, model, fields, style):
        if len(fields) == 1 and fields[0].db_tablespace:
            tablespace_sql = self.connection.ops.tablespace_sql(
                fields[0].db_tablespace)
        elif model._meta.db_tablespace:
            tablespace_sql = self.connection.ops.tablespace_sql(
                model._meta.db_tablespace)
        else:
            tablespace_sql = ""
        if tablespace_sql:
            tablespace_sql = " " + tablespace_sql

        field_names = []
        qn = self.connection.ops.quote_name
        for f in fields:
            field_names.append(style.SQL_FIELD(qn(f.column)))

        index_name = "{0}_{1}".format(model._meta.db_table,
                                      self._digest([f.name for f in fields]))

        return [
            style.SQL_KEYWORD("DROP INDEX") + " " +
            style.SQL_TABLE(qn(truncate_name(index_name,
                self.connection.ops.max_name_length()))) + " " +
            style.SQL_KEYWORD("ON") + " " +
            style.SQL_TABLE(qn(model._meta.db_table)) + ";",
        ]
