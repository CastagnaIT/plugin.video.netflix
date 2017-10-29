# Netflix Plugin for Kodi 18 (plugin.video.netflix)

[![Bitcoin donate button](https://img.shields.io/badge/bitcoin-donate-yellow.svg)](https://blockchain.info/address/1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF)
[![Build Status](https://travis-ci.org/asciidisco/plugin.video.netflix.svg?branch=master)](https://travis-ci.org/asciidisco/plugin.video.netflix)
[![Test Coverage](https://codeclimate.com/github/asciidisco/plugin.video.netflix/badges/coverage.svg)](https://codeclimate.com/github/asciidisco/plugin.video.netflix/coverage)
[![Issue Count](https://codeclimate.com/github/asciidisco/plugin.video.netflix/badges/issue_count.svg)](https://codeclimate.com/github/asciidisco/plugin.video.netflix)
[![Code Climate](https://codeclimate.com/github/asciidisco/plugin.video.netflix/badges/gpa.svg)](https://codeclimate.com/github/asciidisco/plugin.video.netflix)
[![GitHub release](https://img.shields.io/github/release/asciidisco/plugin.video.netflix.svg)](https://github.com/asciidisco/plugin.video.netflix/releases)
[![Docs](https://media.readthedocs.org/static/projects/badges/passing.svg)](https://asciidisco.github.io/plugin.video.netflix/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Disclaimer

This plugin is not officially commisioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

## Prerequisites

- Kodi 18 [nightlybuild](http://mirrors.kodi.tv/nightlies/)
- Inputstream.adaptive [>=v2.0.0](https://github.com/peak3d/inputstream.adaptive)
  (should be included in your Kodi 18 installation)
- Libwidevine >=1.4.8.970 (for non Android devices)
- Cryptdome python library (for Linux systems, install using `pip install --user pycryptodomex` as the user that will run Kodi)

Note: The link to download the Widevine Libary for none ARM Systems can be
found in the [Firefox Sources](https://hg.mozilla.org/mozilla-central/raw-file/31465a03c03d1eec31cd4dd5d6b803724dcb29cd/toolkit/content/gmp-sources/widevinecdm.json)
& needs to be placed in the `cdm` folder in [special://home](http://kodi.wiki/view/Special_protocol).

Please make sure to read the licence agreement that comes with it,
so you know what you´re getting yourself into.

## Installation & Updates

You can use
[our repository](https://github.com/kodinerds/repo/raw/master/repository.netflix/repository.netflix-1.0.1.zip)
to install plugin.
Using this, you´ll immediately receive updates once a
new release has been drafted.

Further installations instructions can be found in the [Wiki](https://github.com/asciidisco/plugin.video.netflix/wiki)

## FAQ

- [Does it work with Kodi 17](https://github.com/asciidisco/plugin.video.netflix/issues/25)
- [Does it work on a RPI](https://github.com/asciidisco/plugin.video.netflix/issues/28)
- [Which video resolutions are supported](https://github.com/asciidisco/plugin.video.netflix/issues/27)
- [Can it play 4k Videos](https://github.com/asciidisco/plugin.video.netflix/issues/86)

## Functionality

- Multiple profiles
- Search Netflix (incl. suggestions)
- Netflix categories, recommendations, "my list" & continue watching
- Rate show/movie
- Add & remove to/from "my list"
- Export of complete shows & movies in local database

## Something doesn't work

If something doesn't work for you, please:

- Make sure all prerequisites are met
- Enable verbose logging in the plugin settings
- Enable the Debug log in you Kodi settings
- Open an issue with a titles that summarises your problems

## Donate

If you like this project feel free to buy us some cups of coffee.
Our bitcoin address is: `1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF`

## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## Licence

Licenced under The MIT License.
