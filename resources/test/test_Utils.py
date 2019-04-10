# -*- coding: utf-8 -*-
# Module: Utils
# Author: asciidisco
# Created on: 11.10.2017
# License: MIT https://goo.gl/5bMj3H

"""Tests for the `Utils` module"""

import unittest
import mock
from resources.lib.utils import get_user_agent, noop, uniq_id, get_class_methods, __get_mac_address as gma
from mocks.MinimalClassMocks import MockClass
from mocks.LoggerMocks import TestLoggerWithArgs, TestLoggerWithCredentialArgs, TestLoggerWithNoArgs


class UtilsTestCase(unittest.TestCase):
    """Tests for the `Utils` module"""

    def test_get_user_agent(self):
        """ADD ME"""
        self.assertIn(
            container=get_user_agent(),
            member='Chrome/59.0.3071.115')

    @mock.patch('platform.system')
    def test_get_user_agent_Linux(self, mock_system):
        """ADD ME"""
        mock_system.return_value = 'Linux'
        self.assertIn(
            container=get_user_agent(),
            member='Linux')

    @mock.patch('platform.system')
    def test_get_user_agent_Darwin(self, mock_system):
        """ADD ME"""
        mock_system.return_value = 'Darwin'
        self.assertIn(
            container=get_user_agent(),
            member='Mac')

    @mock.patch('platform.system')
    def test_get_user_agent_Windows(self, mock_system):
        """ADD ME"""
        mock_system.return_value = 'Windows'
        self.assertIn(
            container=get_user_agent(),
            member='Win')

    @mock.patch('platform.system')
    @mock.patch('platform.machine')
    def test_get_user_agent_Arm(self, mock_machine, mock_system):
        """ADD ME"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'arm'
        self.assertIn(
            container=get_user_agent(),
            member='armv')

    @mock.patch('xbmcaddon.Addon')
    def test_uniq_id(self, mock_xbmcaddon):
        """ADD ME"""
        self.assertEquals(
            first=uniq_id(delay=1),
            second='=\x05\xc1\xf7\x0b\xb5&\xd0\xa2\xd1]\xce\xf3\xee\x92\x8a\xb5\xc7\x985\x8a{\xf5A6TD\xf3/\x93\x84W')

    @mock.patch('xbmc.getInfoLabel')
    def test_get_mac_address_delay(self, mock_getInfoLabel):
        """ADD ME"""
        mock_getInfoLabel.return_value = '00:80:41:ae:fd:7e'
        self.assertEqual(
            first=uniq_id(delay=2),
            second='\xf7K\x87\xb3\xc4\xd2\xd4\xea7\x91\x99( C\xb2\x8e\xa7\x8d}L\xdbP\x93\xfaM&4\x8a\xb6\xda\xcfG')

    @mock.patch('xbmc.getInfoLabel')
    def test_get_mac_address(self, mock_getInfoLabel):
        """ADD ME"""
        mock_getInfoLabel.return_value = '00:80:41:ae:fd:7e'
        self.assertEqual(
            first=gma(),
            second='00:80:41:ae:fd:7e')

    @mock.patch('xbmc.getInfoLabel')
    def test_get_mac_address_malformed(self, mock_getInfoLabel):
        """ADD ME"""
        mock_getInfoLabel.return_value = '00-80-41-ae-fd-7e'
        self.assertEqual(
            first=gma(),
            second='00-80-41-ae-fd-7e')

    def test_noop(self):
        """ADD ME"""
        self.assertEqual(
            first=noop(a='a'),
            second={'a': 'a'})

    def test_log_decorator(self):
        """Does log messages if a log function is applied to the parent class"""
        def logger_1(message):
            if 'returned' in message:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithNoArgs::to_be_logged" returned: None')
            else:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithNoArgs::to_be_logged" called')
        instTestLoggerWithNoArgs = TestLoggerWithNoArgs(logger_1=logger_1)
        instTestLoggerWithNoArgs.to_be_logged()

        def logger_2(message):
            if 'returned' in message:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithArgs::to_be_logged" returned: None')
            else:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithArgs::to_be_logged" called with arguments :a = b:')
        instTestLoggerWithArgs = TestLoggerWithArgs(logger_2=logger_2)
        instTestLoggerWithArgs.to_be_logged(a='b')

        def logger_3(message):
            if 'returned' in message:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithCredentialArgs::to_be_logged" returned: None')
            else:
                self.assertEqual(
                    first=message,
                    second='"TestLoggerWithCredentialArgs::to_be_logged" called with arguments :a = b:')
        instTestLoggerWithCredentialArgs = TestLoggerWithCredentialArgs(logger_3=logger_3)
        instTestLoggerWithCredentialArgs.to_be_logged(credentials='foo', account='bar', a='b')

    def test_get_class_methods(self):
        self.assertEqual(
            first=get_class_methods(class_item=MockClass),
            second=['bar', 'foo', '__init__'])
