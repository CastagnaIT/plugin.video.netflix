# -*- coding: utf-8 -*-
"""
    Copyright (C) 2021 Stefano Gottardo - @CastagnaIT
    Helper to enable TCP Keep Alive

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import socket
import sys

TCP_KEEP_IDLE = 45
TCP_KEEPALIVE_INTERVAL = 10
TCP_KEEP_CNT = 6


def enable_tcp_keep_alive(sock):
    """Enable TCP Keep-Alive (by default disabled)"""
    # More info on PR: https://github.com/CastagnaIT/plugin.video.netflix/pull/1065
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if sys.platform == 'linux':
        # TCP Keep Alive Probes for Linux/Android
        if hasattr(socket, 'TCP_KEEPIDLE'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEP_IDLE)
        if hasattr(socket, 'TCP_KEEPINTVL'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPALIVE_INTERVAL)
        if hasattr(socket, 'TCP_KEEPCNT'):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, TCP_KEEP_CNT)
    elif sys.platform == 'darwin':
        # TCP Keep Alive Probes for MacOS
        # NOTE: The socket constants from MacOS netinet/tcp.h are not exported by python's socket module
        # The MacOS TCP_KEEPALIVE(0x10) constant should be the same thing of the linux TCP_KEEPIDLE constant
        sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPIDLE', 0x10), TCP_KEEP_IDLE)
        sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPINTVL', 0x101), TCP_KEEPALIVE_INTERVAL)
        sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, 'TCP_KEEPCNT', 0x102), TCP_KEEP_CNT)
    elif sys.platform == 'win32':
        # TCP Keep Alive Probes for Windows
        sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, TCP_KEEP_IDLE * 1000, TCP_KEEPALIVE_INTERVAL * 1000))
