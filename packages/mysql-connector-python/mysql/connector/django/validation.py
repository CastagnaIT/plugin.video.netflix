# MySQL Connector/Python - MySQL driver written in Python.

import django

from django.db.backends.base.validation import BaseDatabaseValidation
from django.core import checks
from django.db import connection


class DatabaseValidation(BaseDatabaseValidation):
    def check_field(self, field, **kwargs):
        """
        MySQL has the following field length restriction:
        No character (varchar) fields can have a length exceeding 255
        characters if they have a unique index on them.
        """
        errors = super(DatabaseValidation, self).check_field(field,
                                                                **kwargs)

        # Ignore any related fields.
        if getattr(field, 'rel', None) is None:
            field_type = field.db_type(connection)

            if field_type is None:
                return errors

            if (field_type.startswith('varchar')  # Look for CharFields...
                    and field.unique  # ... that are unique
                    and (field.max_length is None or
                                    int(field.max_length) > 255)):
                errors.append(
                    checks.Error(
                        ('MySQL does not allow unique CharFields to have a '
                            'max_length > 255.'),
                        hint=None,
                        obj=field,
                        id='mysql.E001',
                    )
            )
        return errors
