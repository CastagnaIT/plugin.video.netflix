# -*- coding: utf-8 -*-
# Module: Utils
# Author: asciidisco
# Created on: 11.10.2017
# License: MIT https://goo.gl/5bMj3H

"""Tests for the `Utils` module"""

import unittest
import mock
from resources.lib.utils import get_user_agent

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
    def test_get_user_agent_Windows(self, mock_machine, mock_system):
        """ADD ME"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'arm'
        self.assertIn(
            container=get_user_agent(),
            member='armv')
