# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Stateful Netflix session management: handle the cookies

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time

import resources.lib.common as common
import resources.lib.common.cookies as cookies
from resources.lib.globals import g
from resources.lib.services.nfsession.nfsession_base import NFSessionBase

LOGIN_COOKIES = ['nfvdid', 'SecureNetflixId', 'NetflixId']


class NFSessionCookie(NFSessionBase):
    """Handle the cookies"""

    @common.time_execution(immediate=True)
    def _load_cookies(self):
        """Load stored cookies from disk"""
        # pylint: disable=broad-except
        if not self.session.cookies:
            try:
                self.session.cookies = cookies.load(self.account_hash)
            except cookies.MissingCookiesError:
                return False
            except Exception as exc:
                import traceback
                common.error('Failed to load stored cookies: {}', type(exc).__name__)
                common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
                return False
            common.info('Successfully loaded stored cookies')
        return True

    @common.time_execution(immediate=True)
    def _verify_session_cookies(self):
        """Verify that the session cookies have not expired"""
        if not self.session.cookies:
            return False
        for cookie_name in LOGIN_COOKIES:
            if cookie_name not in list(self.session.cookies.keys()):
                common.error(
                    'The cookie "{}" do not exist. It is not possible to check expiration. '
                    'Fallback to old validate method.',
                    cookie_name)
                break
            for cookie in list(self.session.cookies):
                if cookie.name != cookie_name:
                    continue
                if cookie.expires <= int(time.time()):
                    common.info('Login is expired')
                    return False
        return True
