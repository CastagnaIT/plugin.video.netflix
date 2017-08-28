# plugin.video.netflix

## Netflix Plugin for Kodi 18

<span class="badge-bitcoin"><a href="https://blockchain.info/address/1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF" title="Donate to this project using Bitcoin"><img src="https://img.shields.io/badge/bitcoin-donate-yellow.svg" alt="Bitcoin donate button" /></a></span>

Disclaimer
-------------
This plugin is not officially commisioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

Prerequisites
-------------

- Kodi 18 [nightlybuild](http://mirrors.kodi.tv/nightlies/)
- Inputstream.adaptive [>=v2.0.4](https://github.com/peak3d/inputstream.adaptive) (should be included in your Kodi 18 installation)
- Libwidevine 1.4.8.962 (A german description how to get/install it, can be found [here](https://www.kodinerds.net/index.php/Thread/51486-Kodi-17-Inputstream-HowTo-AddOns-f%C3%BCr-Kodi-17-ab-Beta-6-aktuelle-Git-builds-Updat/))

Note: The link to download the Widevine Libary for none ARM Systems can be found in the [Firefox Sources](https://hg.mozilla.org/mozilla-central/raw-file/31465a03c03d1eec31cd4dd5d6b803724dcb29cd/toolkit/content/gmp-sources/widevinecdm.json) & needs to be placed in the `cdm` folder in [special://home](http://kodi.wiki/view/Special_protocol).

Please make sure to read the licence agreement that comes with it, so you know what you´re getting yourself into.

Installation & Updates
----------------------

You can use [our repository](https://github.com/kodinerds/repo/raw/master/repository.netflix/repository.netflix-1.0.1.zip) to install plugin. Using this, you´ll immediately receive updates once a new release has been drafted.

FAQ
---

- [Does it work with Kodi 17](https://github.com/asciidisco/plugin.video.netflix/issues/25)
- [Does it work on a RPI](https://github.com/asciidisco/plugin.video.netflix/issues/28)
- [Which video resolutions are supported](https://github.com/asciidisco/plugin.video.netflix/issues/27)

Functionality
-------------
- Multiple profiles
- Search Netflix (incl. suggestions)
- Netflix categories, recommendations, "my list" & continue watching
- Rate show/movie
- Add & remove to/from "my list"
- Export of complete shows & movies in local database (custom library folder can be configured, by default the .strm files are stored in `userdata/addon_data/plugin.video.netflix` )

Something doesn't work
----------------------

If something doesn't work for you, please:

- Make sure all prerequisites are met
- Enable verbose logging in the plugin settings
- Enable the Debug log in you Kodi settings
- Open an issue with a titles that summarises your problems and include:
	- Kodi version (git sha if possible)
	- Inputstream.adaptive version (git sha if possible)
	- Your OS and OS version
	- Libwedevine version
	- A Kodi debug log that represents your issue

Donate
------

If you like this project feel free to buy us some cups of coffee.
Our bitcoin address is: `1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF`

Licence
-------

Licenced under The MIT License.
Includes [pyjsparser](https://github.com/PiotrDabkowski/pyjsparser) by [Piotr Dabkowski](https://github.com/PiotrDabkowski)
