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
  (must be separately installed from the Kodi repo since Leia Beta 5)
- Cryptdome python library (for Linux systems, install using `pip install --user pycryptodomex` as the user that will run Kodi)

For non-Android devices, the required Widevine DRM binaries will automatically be installed by inputstream.helper.
Please make sure to read the licence agreement that is presented upon Widevine installation, so you know what you´re getting yourself into.

## Installation & Updates

You can use [our repository](https://github.com/kodinerds/repo/raw/master/repository.netflix/repository.netflix-1.0.1.zip) to install the plugin.
Using this, you´ll immediately receive updates once a new release has been drafted.

## Functionality

- Multiple profiles
- Search Netflix (incl. suggestions)
- Netflix categories, recommendations, "my list" & continue watching
- Browse all movies and all TV shows Netflix style
- Rate show/movie
- Add & remove to/from "my list"
- Export of complete shows & movies in local database
- Keep My List and local database in sync
- Export new seasons/episodes to local database when they become available on Netflix

## FAQ

### Does it work with Kodi 17?
No. Netflix's DRM is incompatible with inpustream from Kodi 17.

### Does it work on a RPI?
Yes, but you most likely won't get 1080p playback to work properly (see next FAQ).

### Can it play 1080p videos?
Yes, as long as they are available from Netflix and your hardware can handle it. On Widevine L1 devices (some Android devices), this is usually not an issue, because DRM is built into the system and hardware decoding can be used.
On all other platforms, video is always software decoded due to Netflix licensing restrictions, so **you'll need a CPU that can handle the load of software decoding 1080p video**.

**Current RPI devices cannot play 1080p**, because they usually cannot deliver the required performance, which will result in stuttering video playback. 720p is maximum for those devices, and even then you need to make sure to properly cool your RPI or you'll have stuttering playback as well.

### Can it play 1080p on Linux?
Yes. There is a workaround included to enabled 1080p playback for titles that are usually locked to lower resolutions. This also extends to some titles, which will only play in 480p on Chrome on Windows as well (mostly Disney stuff).
The workaround uses the method devised by truedread for his Chrome plugin: https://github.com/truedread/netflix-1080p

### It only plays videos in 480p/720p, why is that?
inputstream.adaptive selects the stream to play based on an initial bandwidth measurement and your screen resolution.
If you want to force 1080p playback, set Min Bandwidth to 8,000,000 in inputstream.adaptive settings.
Also make sure your display resolution is at least 1080p or enable `Ignore display resolution` in inputstream.adaptive settings.
If it's still not playing 1080p, the title most probably just isn't available in 1080p.

### Can it play 4K videos?
Yes, but only on Android devices with Widevine L1. You need to enter the ESN from your Netflix App (can be found unter Settings => About) and enable HEVC profiles in addon settings.

### Can it play HDR?
Yes, as long as the 4K prerequisites are met. Additionally, you must enabled HDR and/or DolbyVision profiles
in addon settings.
Depending on your setup, there may be some tinkering required to get HDR to work. This depends on your TV,
if you are using an AV-Receiver, which device Kodi is running on, etc. Please make sure to search the issues and available forum threads for a solution before opening an issue!

### Does it support 5.1 audio?
Yes, enable Dolby Sound in addon settings (is enabled by default).

### Is Dolby Atmos supported?
Yes. It's disabled by default, so you'll need to enable it in the settings.

### Are image based subtitles (Hebrew, Arabic, ...) supported?
No. They are provided in a different format, which requires some work to support, either on Kodi or the addon side.
It's on the roadmap but doesn't have an ETA.

### I added/removed something to My List on PC/in the Netflix App but it doesn't show up in my Kodi library?
Only add/remove to My List from within the addon keeps the Kodi library in sync. Changes made in other clients (PC, App, ...) are not recognized because it's unclear how to handle those actions with multiple profiles.

### My watched status is not being updated?!
The addon does not report watched status back to Netflix (yet). This is a top priority on our roadmap, but we haven't been able to figure this out just yet.

## Something doesn't work

If something doesn't work for you, please:
- Make sure all prerequisites are met
- Enable the Debug log in your Kodi settings
- Open an issue with a title that summarises your problems and **attach the full debug log**

We can't help you if you don't provide detailed information (i.e. explanation and full debug log) on your issue.
Please also use a service like pastebin to provide logs and refrain from uploading them to where they'll be hidden behind an ad-wall or any other sketchy services.

## Donate

If you like this project feel free to buy us some cups of coffee.
Our bitcoin address is: `1DHGftMkFXXsDY7UnqQuatWwxQzKVu88sF`

## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## Licence

Licenced under The MIT License.
