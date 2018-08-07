# -*- coding: utf-8 -*-
# Author: caphm
# Module: storage
# Created on: 06.08.2018
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=import-error

"""
Easily accessible persistent storage
"""

import os
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmcvfs

from resources.lib.utils import LoggingComponent


class PersistentStorage(LoggingComponent):
    """
    Key-Value storage with a backing file on disk.
    Reads entire dict structure into memory on first access and updates
    the backing file with each changed entry.

    IMPORTANT: Changes to mutable objects inserted into the key-value-store
    are not automatically written to disk. You need to call commit() to
    persist these changes.
    """
    def __init__(self, storage_id, nx_common):
        LoggingComponent.__init__(self, nx_common)
        self.storage_id = storage_id
        self.backing_file = os.path.join(nx_common.data_path,
                                         self.storage_id + '.ndb')
        self._contents = {}
        self._dirty = True
        self.log('Instantiated {}'.format(self.storage_id))

    def __getitem__(self, key):
        self.log('Getting {}'.format(key))
        return self.contents[key]

    def __setitem__(self, key, value):
        self.log('Setting {} to {}'.format(key, value))
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
        f = xbmcvfs.File(self.backing_file, 'wb')
        pickle.dump(self._contents, f)
        f.close()
        self.log('Committed changes to backing file')

    def clear(self):
        """
        Clear contents and backing file
        """
        self._contents = {}
        self.commit()

    def _load_from_disk(self):
        self.log('Trying to load contents from disk')
        if xbmcvfs.exists(self.backing_file):
            f = xbmcvfs.File(self.backing_file, 'rb')
            self._contents = pickle.loads(f.read())
            self._dirty = False
            f.close()
            self.log('Loaded contents from backing file ({})'.format(self._contents))
        else:
            self.log('Backing file does not exist')
