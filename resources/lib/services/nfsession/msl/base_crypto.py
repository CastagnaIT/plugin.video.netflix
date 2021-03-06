# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Common base for crypto handlers

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import base64
import time

import resources.lib.common as common
from resources.lib.services.nfsession.msl.msl_utils import MSL_DATA_FILENAME
from resources.lib.utils.esn import get_esn
from resources.lib.utils.logging import LOG


class MSLBaseCrypto:
    """
    Common base class for MSL crypto operations.
    Handles MasterToken and sequence number
    """

    def __init__(self):
        self._msl_data = None
        self.mastertoken = None
        self.serial_number = None
        self.sequence_number = None
        self.renewal_window = None
        self.expiration = None
        self.bound_esn = None  # Specify the ESN bound to mastertoken

    def load_msl_data(self, msl_data=None):
        self._msl_data = msl_data if msl_data else {}
        if msl_data:
            self.set_mastertoken(msl_data['tokens']['mastertoken'])
            self.bound_esn = msl_data.get('bound_esn', get_esn())

    def compare_mastertoken(self, mastertoken):
        """Check if the new MasterToken is different from current due to renew"""
        if not self._mastertoken_is_newer_that(mastertoken):
            LOG.debug('MSL mastertoken is changed due to renew')
            self.set_mastertoken(mastertoken)
            self._save_msl_data()

    def _mastertoken_is_newer_that(self, mastertoken):
        """Check if current MasterToken is newer than mastertoken specified"""
        # Based on cadmium player sourcecode and ref. to [isNewerThan] in:
        # https://github.com/Netflix/msl/blob/master/core/src/main/java/com/netflix/msl/tokens/MasterToken.java
        new_tokendata = json.loads(
            base64.standard_b64decode(mastertoken['tokendata'].encode('utf-8')).decode('utf-8'))
        if new_tokendata['sequencenumber'] == self.sequence_number:
            return new_tokendata['expiration'] > self.expiration
        if new_tokendata['sequencenumber'] > self.sequence_number:
            cut_off = new_tokendata['sequencenumber'] - pow(2, 53) + 127
            return self.sequence_number >= cut_off
        cut_off = self.sequence_number - pow(2, 53) + 127
        return new_tokendata['sequencenumber'] < cut_off

    def parse_key_response(self, headerdata, esn, save_to_disk):
        """Parse a key response and update crypto keys"""
        self.set_mastertoken(headerdata['keyresponsedata']['mastertoken'])
        self._init_keys(headerdata['keyresponsedata'])
        self.bound_esn = esn
        if save_to_disk:
            self._save_msl_data()

    def set_mastertoken(self, mastertoken):
        """Set the MasterToken and check it for validity"""
        tokendata = json.loads(
            base64.standard_b64decode(mastertoken['tokendata'].encode('utf-8')).decode('utf-8'))
        self.mastertoken = mastertoken
        self.serial_number = tokendata['serialnumber']
        self.sequence_number = tokendata.get('sequencenumber', 0)
        self.renewal_window = tokendata['renewalwindow']
        self.expiration = tokendata['expiration']

    def _save_msl_data(self):
        """Save crypto keys and MasterToken to disk"""
        self._msl_data['tokens'] = {'mastertoken': self.mastertoken}
        self._msl_data.update(self._export_keys())
        self._msl_data['bound_esn'] = self.bound_esn
        common.save_file_def(MSL_DATA_FILENAME, json.dumps(self._msl_data).encode('utf-8'))
        LOG.debug('Successfully saved MSL data to disk')

    def _init_keys(self, key_response_data):
        """Initialize crypto keys from key_response_data"""
        raise NotImplementedError

    def _export_keys(self):
        """Export crypto keys to a dict"""
        raise NotImplementedError

    def get_user_id_token(self, profile_guid):
        """Get a valid the user id token associated to a profile guid"""
        if 'user_id_tokens' in self._msl_data:
            user_id_token = self._msl_data['user_id_tokens'].get(profile_guid)
            if user_id_token and not self.is_user_id_token_expired(user_id_token):
                return user_id_token
        return None

    def save_user_id_token(self, profile_guid, user_token_id):
        """Save or update a user id token associated to a profile guid"""
        if 'user_id_tokens' not in self._msl_data:
            save_msl_data = True
            self._msl_data['user_id_tokens'] = {
                profile_guid: user_token_id
            }
        else:
            save_msl_data = not self._msl_data['user_id_tokens'].get(profile_guid) == user_token_id
            self._msl_data['user_id_tokens'][profile_guid] = user_token_id
        if save_msl_data:
            self._save_msl_data()

    def clear_user_id_tokens(self):
        """Clear all user id tokens"""
        self._msl_data.pop('user_id_tokens', None)
        self._save_msl_data()

    def is_user_id_token_expired(self, user_id_token):
        """Check if user id token is expired"""
        token_data = json.loads(base64.standard_b64decode(user_id_token['tokendata']))
        # Subtract 5min as a safety measure
        return (token_data['expiration'] - 300) < time.time()

    def is_current_mastertoken_expired(self):
        """Check if the current MasterToken is expired"""
        return self.expiration <= time.time()

    def get_current_mastertoken_validity(self):
        """Gets a dict values to know if current MasterToken is renewable and/or expired"""
        time_now = time.time()
        renewable = self.renewal_window < time_now
        expired = self.expiration <= time_now
        return {'is_renewable': renewable, 'is_expired': expired}
