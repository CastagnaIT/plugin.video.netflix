# -*- coding: utf-8 -*-
"""Common base for crypto handlers"""
from __future__ import unicode_literals

import time
import json
import base64

import resources.lib.common as common

from .exceptions import MastertokenExpired


class MSLBaseCrypto(object):
    """Common base class for MSL crypto operations.
    Handles mastertoken and sequence number"""
    # pylint: disable=too-few-public-methods
    def __init__(self, msl_data=None):
        if msl_data:
            self._set_mastertoken(msl_data['tokens']['mastertoken'])

    def parse_key_response(self, headerdata, save_to_disk):
        """Parse a key response and update crypto keys"""
        self._set_mastertoken(headerdata['keyresponsedata']['mastertoken'])
        self._init_keys(headerdata['keyresponsedata'])
        if save_to_disk:
            self._save_msl_data()

    def _set_mastertoken(self, mastertoken):
        """Set the mastertoken and check it for validity"""
        tokendata = json.loads(
            base64.standard_b64decode(mastertoken['tokendata']))
        remaining_ttl = (int(tokendata['expiration']) - time.time())
        if remaining_ttl / 60 / 60 >= 10:
            self.mastertoken = mastertoken
            self.sequence_number = tokendata.get('sequencenumber', 0)
        else:
            common.error('Mastertoken has expired')
            raise MastertokenExpired

    def _save_msl_data(self):
        """Save crypto keys and mastertoken to disk"""
        msl_data = {'tokens': {'mastertoken': self.mastertoken}}
        msl_data.update(self._export_keys())
        common.save_file('msl_data.json', json.dumps(msl_data))
        common.debug('Successfully saved MSL data to disk')

    def _init_keys(self, key_response_data):
        """Initialize crypto keys from key_response_data"""
        raise NotImplementedError

    def _export_keys(self):
        """Export crypto keys to a dict"""
        raise NotImplementedError
