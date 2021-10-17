# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Handle the cookies

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import time

import resources.lib.utils.cookies as cookies
from resources.lib.common.exceptions import MissingCookiesError
from resources.lib.services.nfsession.session.base import SessionBase
from resources.lib.utils.logging import LOG

LOGIN_COOKIES = ['nfvdid', 'SecureNetflixId', 'NetflixId']


class SessionCookie(SessionBase):
    """Handle the cookies"""

    def _load_cookies(self):
        """Load stored cookies from disk"""
        # pylint: disable=broad-except
        if not self.session.cookies:
            try:
                self.session.cookies = cookies.load()
            except MissingCookiesError:
                return False
            except Exception as exc:
                import traceback
                LOG.error('Failed to load stored cookies: {}', type(exc).__name__)
                LOG.error(traceback.format_exc())
                return False
            LOG.info('Successfully loaded stored cookies')
        return True

    def _verify_session_cookies(self):
        """Verify that the session cookies have not expired"""
        if not self.session.cookies:
            return False
        for cookie_name in LOGIN_COOKIES:
            if cookie_name not in list(self.session.cookies.keys()):
                LOG.error('The cookie "{}" do not exist, it is not possible to check the expiration',
                          cookie_name)
                return False
            for cookie in self.session.cookies.jar:
                if cookie.name != cookie_name:
                    continue
                if cookie.expires <= int(time.time()):
                    LOG.info('Login is expired')
                    return False
        return True
