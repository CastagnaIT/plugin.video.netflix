# MySQL Connector/Python - MySQL driver written in Python.


import django
from django.db.models.sql import compiler
from django.utils.six.moves import zip_longest


class SQLCompiler(compiler.SQLCompiler):
    def resolve_columns(self, row, fields=()):
        values = []
        index_extra_select = len(self.query.extra_select)
        bool_fields = ("BooleanField", "NullBooleanField")
        for value, field in zip_longest(row[index_extra_select:], fields):
            if (field and field.get_internal_type() in bool_fields and
                    value in (0, 1)):
                value = bool(value)
            values.append(value)
        return row[:index_extra_select] + tuple(values)

    def as_subquery_condition(self, alias, columns, compiler):
        qn = compiler.quote_name_unless_alias
        qn2 = self.connection.ops.quote_name
        sql, params = self.as_sql()
        return '(%s) IN (%s)' % (', '.join('%s.%s' % (qn(alias), qn2(column)) for column in columns), sql), params


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    pass


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
