# Netflix Plugin for Kodi 18 (plugin.video.netflix)


[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This source code comes from the [caphm repository](https://github.com/caphm/plugin.video.netflix) given the discontinuity of his work, i'm trying to keep the project alive, help from skilled people are welcome.
The initial project is on the [repository of asciidisco](https://github.com/asciidisco/plugin.video.netflix) no longer maintained but used as a reference.

## Disclaimer

This plugin is not officially commisioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

## Prerequisites

- Kodi 18 [official download](https://kodi.tv/download)
- Inputstream.adaptive [>=v2.0.0](https://github.com/peak3d/inputstream.adaptive)
  (with Kodi 18 should be installed automatically, otherwise you will be notified)
- Cryptdome python library, with Kodi 18 will be installed automatically
(for Linux systems, install using `pip install --user pycryptodomex` as the user that will run Kodi)

- Widevine DRM
For non-Android devices, will automatically be installed (by inputstream.helper).
Please make sure to read the licence agreement that is presented upon Widevine installation, so you know what you´re getting yourself into.

## Installation & Updates

Repository that provides automatic updates for release builds:
[repository.castagnait-1.0.0.zip](https://github.com/castagnait/repository.castagnait/raw/master/repository.castagnait-1.0.0.zip)

- First download the repository zip
- Open Kodi, go to menu Add-ons, select "Install from zip file", and select the downloaded zip
- Last step, go to "Install from repository", select CastagnaIT repository and Netflix addon

For those who prefer to stay up to date with the daily build should do the manual installation, or use other repositories
[Daily builds](http://www.mediafire.com/folder/vifnw8ve44bi7/KodiNetflixAddon)

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
- On Android devices
Yes, as long as they are available from Netflix and your hardware can handle it.
To understand if your device can handle them, you need to check if it has support for the Widewine L1 DRM

- Other platform (Windows, Linux, ...)
The video is always software decoded due to Netflix licensing restrictions, so **you'll need a CPU that can handle the load of software decoding 1080p video** otherwise you'll have the result of stuttering video playback.
Which is what happens with certain RPI, 720p is maximum for those devices, and even then you need to make sure to properly cool your RPI or you'll have stuttering playback as well.

### It only plays videos in 480p/720p, why is that?
inputstream.adaptive selects the stream to play based on an initial bandwidth measurement and your screen resolution.
If you want to force 1080p playback, set Min Bandwidth to 8,000,000 in inputstream.adaptive settings.
Also make sure your display resolution is at least 1080p or enable `Ignore display resolution` in inputstream.adaptive settings.
If it's still not playing 1080p, the title most probably just isn't available in 1080p.

### Can it play 4K videos?
Yes, but only on Android devices with Widevine L1, and you need to set the following parameters:
- In the addon settings, Expert page:
`Enable VP9 profiles` to OFF
`Enable HEVC profiles` to ON
`Force support to HDCP 2.2` to ON
- In the Inputstream Addon settings, Account page:
`Override HDCP status` to ON

If you don't get 4k resolution when you play:
Try to enter the ESN from your Netflix App (can be found unter Settings => About).

### Can it play HDR?
Yes, as long as the 4K prerequisites are met. Additionally, you must enabled HDR and/or DolbyVision profiles
in addon settings.
Depending on your setup, there may be some tinkering required to get HDR to work. This depends on your TV,
if you are using an AV-Receiver, which device Kodi is running on, etc. Please make sure to search the issues and available forum threads for a solution before opening an issue!

### Does it support 5.1 audio?
Yes, enable the option `Enable Dolby Digital Plus` in addon settings (is enabled by default).

### Is Dolby Atmos supported?
Yes. It's enabled by default, when option `Enable Dolby Digital Plus` is enabled.
But only some videos have Atmos, they can be distinguished from the skin media-flag "Dolby-HD".
Note: Need a premium netflix account.

### Are image based subtitles (Hebrew, Arabic, ...) supported?
No. They are provided in a different format, which requires some work to support, either on Kodi or the addon side.
It's on the roadmap but doesn't have an ETA.

### Why do i always see subtitles in every video?
Just change how Kodi handles subtitles by choosing forced only.
In Kodi Settings -> Player -> Language
set: `Preferred subtitle language` to `Forced only`

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

## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## Licence

Licenced under The MIT License.
