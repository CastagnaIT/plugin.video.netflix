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
- Libwidevine 1.4.8.962 (A german description how to get/install it, can be found [here](https://www.kodinerds.net/index.php/Thread/51486-Kodi-17-Inputstream-HowTo-AddOns-f%C3%BCr-Kodi-17-ab-Beta-6-aktuelle-Git-builds-Updat/))
- Inputstream.adaptive [v2.0.4](https://github.com/peak3d/inputstream.adaptive)

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

ToDo
----

> Note: Those Todos are considered enhancements, they´re not issues, nor they prevent the usage of the plugin for everyday business

If you feel, you´d like to contribute to this plugin or directly work on one of these items,
please open an issue & we can provide you with some help to get started

- [ ] Add missing meta data for episodes/seasons (Cast, bookmark position, etc.)
- [ ] Change list of shows to actual list of episodes in the "Continue watching"" section, like it´s done on the website
- [ ] Enable possibility to export single episodes or seasons to the Library
- [ ] Evaluate idea of an auto updating library exporter that keeps track (on Plugin start/on Service start maybe)
- [ ] If a new user has been created, they need to select their movie/show preferences to actually get started, we could provide the same mechanisms in Kodi
- [ ] Enable aggressive fetching of data in background (maybe using Futures), like the Netflix website does, to enhance the speed and the user experience when browsing the frontend

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
Our bitcoin address is: 1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF

Licence
-------

Licenced under The MIT License.
Includes [pyjsparser](https://github.com/PiotrDabkowski/pyjsparser) by [Piotr Dabkowski](https://github.com/PiotrDabkowski)
