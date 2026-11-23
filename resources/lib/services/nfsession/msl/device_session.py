# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)

    Optional device-bound MSL user session

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import os

from resources.lib.globals import G
from resources.lib.utils.logging import LOG

FILENAME = 'device_session.json'


def _path():
    try:
        return os.path.join(G.DATA_PATH, FILENAME)
    except Exception:  # pylint: disable=broad-except
        return None


def load():
    """Return the optional device session: {esn, mastertoken, useridtoken}.

    The file is user-provisioned. When present, the ESN is pinned to the
    identity the tokens were minted for and MSL requests authenticate with
    userauthdata USER_ID_TOKEN carrying the pair, instead of the website
    NETFLIXID cookies, which the server rejects with MSL 205032 when the
    cookies belong to a different entity than the sender ESN.
    """
    path = _path()
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as file_handle:
            data = json.load(file_handle)
        if (isinstance(data, dict)
                and isinstance(data.get('esn'), str) and data.get('esn')
                and data.get('mastertoken') and data.get('useridtoken')):
            return data
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warn('device_session.json cannot be used: {}', exc)
    return None
