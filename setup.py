# -*- coding: utf-8 -*-
# Module: default
# Author: asciidisco
# Created on: 24.07.2017
# License: MIT https://goo.gl/5bMj3H

"""Setup"""

import os
import re
import sys
from setuptools import find_packages, setup

REQUIRED_PYTHON_VERSION = (2, 7)
PACKAGES = find_packages()
INSTALL_DEPENDENCIES = []
SETUP_DEPENDENCIES = []
TEST_DEPENDENCIES = [
    'nose',
    'Kodistubs',
    'httpretty',
    'mock',
]
EXTRA_DEPENDENCIES = {
    'dev': [
        'nose',
        'flake8',
        'codeclimate-test-reporter',
        'pylint',
        'mccabe',
        'pycodestyle',
        'pyflakes',
        'Kodistubs',
        'httpretty',
        'mock',
        'requests',
        'pyDes',
        'radon',
        'Sphinx',
        'sphinx_rtd_theme',
        'm2r',
        'kodi-release-helper',
        'dennis',
        'blessings',
        'demjson',
        'restructuredtext_lint',
        'yamllint',
    ]
}


def get_addon_data():
    """Loads the Kodi plugin data from addon.xml"""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    pathname = os.path.join(root_dir, 'addon.xml')
    with open(pathname, 'rb') as addon_xml:
        addon_xml_contents = addon_xml.read()
        _id = re.search(
            r'(?<!xml )id="(.+?)"',
            addon_xml_contents).group(1)
        author = re.search(
            r'(?<!xml )provider-name="(.+?)"',
            addon_xml_contents).group(1)
        name = re.search(
            r'(?<!xml )name="(.+?)"',
            addon_xml_contents).group(1)
        version = re.search(
            r'(?<!xml )version="(.+?)"',
            addon_xml_contents).group(1)
        desc = re.search(
            r'(?<!xml )description lang="en_GB">(.+?)<',
            addon_xml_contents).group(1)
        email = re.search(
            r'(?<!xml )email>(.+?)<',
            addon_xml_contents).group(1)
        source = re.search(
            r'(?<!xml )source>(.+?)<',
            addon_xml_contents).group(1)
        return {
            'id': _id,
            'author': author,
            'name': name,
            'version': version,
            'desc': desc,
            'email': email,
            'source': source,
        }


if sys.version_info < REQUIRED_PYTHON_VERSION:
    sys.exit('Python >= 2.7 is required. Your version:\n' + sys.version)

if __name__ == '__main__':
    ADDON_DATA = get_addon_data()
    setup(
        name=ADDON_DATA.get('name'),
        version=ADDON_DATA.get('version'),
        author=ADDON_DATA.get('author'),
        author_email=ADDON_DATA.get('email'),
        description=ADDON_DATA.get('desc'),
        packages=PACKAGES,
        include_package_data=True,
        install_requires=INSTALL_DEPENDENCIES,
        setup_requires=SETUP_DEPENDENCIES,
        tests_require=TEST_DEPENDENCIES,
        extras_require=EXTRA_DEPENDENCIES,
        test_suite='nose.collector',
    )
