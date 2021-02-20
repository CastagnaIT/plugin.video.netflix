# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2021 Stefano Gottardo - @CastagnaIT
    Helper to enable TCP Keep Alive

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import socket
import sys

from requests.adapters import HTTPAdapter, DEFAULT_POOLBLOCK
from urllib3 import HTTPSConnectionPool, HTTPConnectionPool, PoolManager
from urllib3.connection import HTTPConnection

TCP_KEEP_IDLE = 45
TCP_KEEPALIVE_INTERVAL = 10
TCP_KEEP_CNT = 6


class KeepAliveHTTPAdapter(HTTPAdapter):
    """Transport adapter that allows us to use TCP Keep-Alive over HTTPS."""
    def init_poolmanager(self, connections, maxsize, block=DEFAULT_POOLBLOCK, **pool_kwargs):
        self.poolmanager = KeepAlivePoolManager(num_pools=connections, maxsize=maxsize,
                                                block=block, strict=True, **pool_kwargs)


class KeepAlivePoolManager(PoolManager):
    """
    This Pool Manager has only had the pool_classes_by_scheme variable changed.
    This now points at the TCPKeepAlive connection pools rather than the default connection pools.
    """
    def __init__(self, num_pools=10, headers=None, **connection_pool_kw):
        super().__init__(num_pools=num_pools, headers=headers, **connection_pool_kw)
        self.pool_classes_by_scheme = {
            "http": HTTPConnectionPool,
            "https": TCPKeepAliveHTTPSConnectionPool
        }


class TCPKeepAliveHTTPSConnectionPool(HTTPSConnectionPool):
    """This class overrides the _validate_conn method in the HTTPSConnectionPool class. This is the entry point to use
    for modifying the socket as it is called after the socket is created and before the request is made."""
    def _validate_conn(self, conn):
        """Called right before a request is made, after the socket is created."""
        super()._validate_conn(conn)
        # NOTE: conn.sock can be of many types of classes, some classes like (WrappedSocket)
        #       not inherit all socket methods and conn.sock.socket is not always available,
        #       then the best way is to use default_socket_options, with the exception of Windows which requires ioctl
        # TCP Keep Alive Probes for Windows
        # pylint: disable=no-member
        conn.sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, TCP_KEEP_IDLE * 1000, TCP_KEEPALIVE_INTERVAL * 1000))


def enable_tcp_keep_alive(session):
    """Enable TCP Keep-Alive (by default on urllib3 used by Requests is disabled)"""
    # More info on PR: https://github.com/CastagnaIT/plugin.video.netflix/pull/1065
    sock_options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    if sys.platform == 'linux':
        # TCP Keep Alive Probes for Linux/Android
        if hasattr(socket, 'TCP_KEEPIDLE'):
            sock_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEP_IDLE))
        if hasattr(socket, 'TCP_KEEPINTVL'):
            sock_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPALIVE_INTERVAL))
        if hasattr(socket, 'TCP_KEEPCNT'):
            sock_options.append((socket.IPPROTO_TCP, socket.TCP_KEEPCNT, TCP_KEEP_CNT))
    elif sys.platform == 'darwin':
        # TCP Keep Alive Probes for MacOS
        # NOTE: The socket constants from MacOS netinet/tcp.h are not exported by python's socket module
        # The MacOS TCP_KEEPALIVE(0x10) constant should be the same thing of the linux TCP_KEEPIDLE constant
        sock_options.append((socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPIDLE', 0x10), TCP_KEEP_IDLE))
        sock_options.append((socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPINTVL', 0x101), TCP_KEEPALIVE_INTERVAL))
        sock_options.append((socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPCNT', 0x102), TCP_KEEP_CNT))
    elif sys.platform == 'win32':
        # Windows use ioctl to enable and set Keep-Alive settings on single connection,
        # the only way to set it is create a new HTTP adapter
        session.mount('https://', KeepAliveHTTPAdapter())
    HTTPConnection.default_socket_options = HTTPConnection.default_socket_options + sock_options
