# -*- coding: utf-8 -*-
"""Common base for crypto handlers"""
from __future__ import absolute_import, division, unicode_literals

import json
import base64

import resources.lib.common as common


class MSLBaseCrypto(object):
    """Common base class for MSL crypto operations.
    Handles mastertoken and sequence number"""
    # pylint: disable=too-few-public-methods
    def __init__(self, msl_data=None):
        if msl_data:
            self._set_mastertoken(msl_data['tokens']['mastertoken'])
        else:
            self.mastertoken = None

    def compare_mastertoken(self, mastertoken):
        """Check if the new mastertoken is different from current due to renew"""
        if not self._mastertoken_is_newer_that(mastertoken):
            common.debug('MSL mastertoken is changed due to renew')
            self._set_mastertoken(mastertoken)
            self._save_msl_data()

    def _mastertoken_is_newer_that(self, mastertoken):
        """Check if current mastertoken is newer than mastertoken specified"""
        # Based on cadmium player sourcecode and ref. to [isNewerThan] in:
        # https://github.com/Netflix/msl/blob/master/core/src/main/java/com/netflix/msl/tokens/MasterToken.java
        new_tokendata = json.loads(
            base64.standard_b64decode(mastertoken['tokendata']))
        if new_tokendata['sequencenumber'] == self.sequence_number:
            return new_tokendata['expiration'] > self.expiration
        if new_tokendata['sequencenumber'] > self.sequence_number:
            cut_off = new_tokendata['sequencenumber'] - pow(2, 53) + 127
            return self.sequence_number >= cut_off
        cut_off = self.sequence_number - pow(2, 53) + 127
        return new_tokendata['sequencenumber'] < cut_off

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
        self.mastertoken = mastertoken
        self.serial_number = tokendata['serialnumber']
        self.sequence_number = tokendata.get('sequencenumber', 0)
        self.renewal_window = tokendata['renewalwindow']
        self.expiration = tokendata['expiration']

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
