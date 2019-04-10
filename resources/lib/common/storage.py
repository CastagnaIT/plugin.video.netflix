# -*- coding: utf-8 -*-
"""Generic persistent on disk storage"""
from __future__ import unicode_literals

import json

from .logging import debug, warn
from .fileops import save_file, load_file


class PersistentStorage(object):
    """
    Key-Value storage with a backing file on disk.
    Reads entire dict structure into memory on first access and updates
    the backing file with each changed entry.

    IMPORTANT: Changes to mutable objects inserted into the key-value-store
    are not automatically written to disk. You need to call commit() to
    persist these changes.
    """
    def __init__(self, storage_id, no_save_on_destroy=False):
        self.storage_id = storage_id
        self.backing_file = self.storage_id + '.ndb'
        self._contents = {}
        self._dirty = True
        self._no_save_on_destroy = no_save_on_destroy
        debug('Instantiated {}'.format(self.storage_id))

    def __del__(self):
        debug('Destroying storage instance (no_save_on_destroy={0}) {1}'.format(str(self._no_save_on_destroy), self.storage_id))
        if not self._no_save_on_destroy:
            self.commit()

    def __getitem__(self, key):
        return self.contents[key]

    def __setitem__(self, key, value):
        self.contents[key] = value
        self.commit()

    @property
    def contents(self):
        """
        The contents of the storage file
        """
        if self._dirty:
            self._load_from_disk()
        return self._contents

    def get(self, key, default=None):
        """
        Return the value associated with key. If key does not exist,
        return default (defaults to None)
        """
        return self.contents.get(key, default)

    def commit(self):
        """
        Write current contents to disk
        """
        save_file(self.backing_file, json.dumps(self._contents))
        debug('Committed changes to backing file')

    def clear(self):
        """
        Clear contents and backing file
        """
        self._contents = {}
        self.commit()

    def _load_from_disk(self):
        # pylint: disable=broad-except
        debug('Trying to load contents from disk')
        try:
            self._contents = json.loads(load_file(self.backing_file))
            debug('Loaded contents from backing file: {}'
                  .format(self._contents))
        except Exception:
            warn('Backing file does not exist or is not readable')
        self._dirty = False
