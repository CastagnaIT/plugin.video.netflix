# -*- coding: utf-8 -*-
"""Generic persistent on disk storage"""
from __future__ import unicode_literals

import os
import json

from .globals import DATA_PATH
from .logging import debug, error


class PersistentStorage(object):
    """
    Key-Value storage with a backing file on disk.
    Reads entire dict structure into memory on first access and updates
    the backing file with each changed entry.

    IMPORTANT: Changes to mutable objects inserted into the key-value-store
    are not automatically written to disk. You need to call commit() to
    persist these changes.
    """
    def __init__(self, storage_id):
        self.storage_id = storage_id
        self.backing_file = os.path.join(DATA_PATH, self.storage_id + '.ndb')
        self._contents = {}
        self._dirty = True
        debug('Instantiated {}'.format(self.storage_id))

    def __del__(self):
        debug('Destroying storage instance {}'.format(self.storage_id))
        self.commit()

    def __getitem__(self, key):
        return self.contents[key]

    def __setitem__(self, key, value):
        self._contents[key] = value
        self.commit()
        self._dirty = True

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
        with open(self.backing_file, 'w') as file_handle:
            json.dump(self._contents, file_handle)
        debug('Committed changes to backing file')

    def clear(self):
        """
        Clear contents and backing file
        """
        self._contents = {}
        self.commit()

    def _load_from_disk(self):
        debug('Trying to load contents from disk')
        try:
            with open(self.backing_file, 'r') as file_handle:
                self._contents = json.load(file_handle)
        except IOError:
            error('Backing file does not exist or is not accessible')
        self._dirty = False
        debug('Loaded contents from backing file: {}'.format(self._contents))
