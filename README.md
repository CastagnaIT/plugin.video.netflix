# Netflix Plugin for Kodi (plugin.video.netflix)

[![Kodi version](https://img.shields.io/badge/kodi%20versions-18-blue)](https://kodi.tv/)
[![GitHub release](https://img.shields.io/github/release/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/releases)
[![Build Status](https://travis-ci.org/castagnait/plugin.video.netflix.svg?branch=master)](https://travis-ci.org/castagnait/plugin.video.netflix)
[![Code Climate - Maintainability](https://api.codeclimate.com/v1/badges/9fbe3ac732f86c05ff00/maintainability)](https://codeclimate.com/github/CastagnaIT/plugin.video.netflix/maintainability)
[![Codecov status](https://img.shields.io/codecov/c/github/castagnait/plugin.video.netflix/master)](https://codecov.io/gh/castagnait/plugin.video.netflix/branch/master)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributors](https://img.shields.io/github/contributors/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/graphs/contributors)

## Disclaimer

This plugin is not officially commisioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

## Features

- Access to multiple profiles
- Search Netflix (incl. suggestions)
- Netflix categories, recommendations, "my list" & continue watching
- Browse all movies and all TV shows Netflix style includes genres
- Browse trailers & more of TV shows and movies (by context menu)
- Rate show/movie
- Add & remove to/from "my list"
- Export of complete shows & movies in (Kodi) local database
- Keep My List and (Kodi) local library in sync
- Export new seasons/episodes to (Kodi) local library when they become available on Netflix
- Share/Sync the (Kodi) local library and netflix addon data with multiple devices that running Kodi
- Possibility of playback with high resolutions 1080P and 4K (see table)
- Support of hi-res audio Dolby Digital Plus and Dolby Digital Atmos (on Premium accounts)
- Support of HDR and Dolby Vision (only on capable android devices, on Premium accounts)
- Support integration with Up Next add-on (proposes to play the next episode automatically)

## Installation & Updates

**[How to install with automatic updates](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-install-the-addon)**

#### Quick download links

Install add-on via repository - provide automatic installation of updates:
* [CastagnaIT Repository - repository.castagnait-1.0.0.zip](https://github.com/castagnait/repository.castagnait/raw/master/repository.castagnait-1.0.0.zip)

Install add-on manually - updates should always be installed manually:
* [Add-on download links to current and previous releases](https://github.com/CastagnaIT/plugin.video.netflix/releases)
* [Daily build - Add-on download link to get latest fixes](http://www.mediafire.com/folder/vifnw8ve44bi7/KodiNetflixAddon) (not always published see dates)

## FAQ

### Reference table of high resolutions

This table explains compatibility of high resolutions between devices and operating systems. This may change over time based on updates made by netflix.

| System                 | 1080P    | 4K    | Video Decoding             |
| ---------------------- | -------- | ----- | -------------------------- |
| Windows                | ✔\*1     | ✖\*2  | Software                   |
| Linux (Android) \*5    | ✔\*1, \*3| ✔\*4  | Software \\ Hardware \*4   |
| Linux (OSMC-LibreELEC) | ✔\*1     | ✖\*2  | Software                   |
| Linux (Distros)        | ✔\*1     | ✖\*2  | Software                   |
| MacOS/IOS              | ✔\*1     | ✖\*2  | Software                   |

\*1 With Software decoding not all videos could be at 1080P.<br/>
\*2 Currently not available due to widevine limitations.<br/>
\*3 To to have a chance to have all the videos at 1080P you must meet \*4 requirements.<br/>
\*4 Hardware decoding and 4k are supported only to devices with Netflix certification, Widevine Security Level L1 and HDCP 2.2 hardware.<br/>
\*5 Some android devices do not work properly, this is due to restrictions implemented by netflix with devices with false certifications (often with some Chinese boxes) in rare cases even happened to not being able to play the videos.

[Click here to view the list of known and tested android devices for 1080P and 4K playback](https://github.com/CastagnaIT/plugin.video.netflix/wiki/List-of-1080P-4k-Android-tested-devices)

### Video playback problems like frame drops, slowdown, stuttering

Usually happens to those devices where hardware video decoding is not available (due to Netflix licensing restrictions) and the CPU fails to process the video stream properly due to the high load.
All devices with software video decoding are affected by this problem (see *Reference table of high resolutions*) like personal computers, raspberry, android boxes (with Widevine sec. lev. L3), etc..

So to get a smooth reproduction **you'll need a CPU that can handle the load of software decoding 1080p video** otherwise you'll have the result of stuttering video playback.

You can try to solve this problem by trying one of these solutions:
- Limit the resolution to 720p<br/>
In the addon settings go to Expert page and change `Limit video stream resolution to` value to 720p.
- Limit InputStream Adaptive max bandwidth<br/>
In the addon settings go to Expert page open InputStream Adaptive settings and try to set Max Bandwidth between 2.500.000 and 4.000.000

### My android device supports 4K but does not playback at 4K

Before asking for help, please perform the following checks:
- Verify that your device support Widevine Security Level L1 (use an app like: DRM Info)
- Verify that your device is connected to a display and/or amplifier with HDCP 2.2 or higher
- Verify that in the Netflix website the streaming quality settings is set to Auto or High
- If possible change Kodi display resolution to 4K. If it is not possible, open InputStream Adaptive settings and set `Ignore Display Resolution` to ON
- Verify that in the addon settings these settings (in the Expert page) are set correctly:
`Enable VP9 profiles` to OFF
`Enable HEVC profiles` to ON
`Force support to HDCP 2.2` to ON
- Verify that in the InputStream Adaptive add-on these settings are set correctly:
`Override HDCP status` to ON
`Stream selection` to Auto

If again you don't get 4k resolution, take note of the ESN of your device, or get it from Netflix App (can be found under Settings => About) and write it down on Expert page, Manual ESN.

If again you don't get 4k resolution, open InputStream Adaptive settings and try to set:
`Ignore Display Resolution` to ON
`Min Bandwidth` to 18.000.000

### How to enable HDR and Dolby Vision

If 4K prerequisites are met, you must enabled HDR and/or DolbyVision profiles in addon settings.

- In the addon settings go to Expert page and set:
`Enable HEVC profiles` to ON
`Enable HDR profiles` to ON and/or `Enable DolbyVision profiles` to ON

Depending on your setup, there may be some tinkering required to get HDR to work. This depends on your TV,
if you are using an AV-Receiver, which device Kodi is running on, etc. Please make sure to search the issues and available forum threads for a solution before opening an issue!

### How to enable Dolby Atmos

It's enabled by default, when option `Enable Dolby Digital Plus` is enabled.
But only some films/tvshows have Atmos streams, they can be distinguished from the skin media-flag "Dolby-HD".
A premium netflix account is required.

### Common problems with subtitles

#### Problem with asian subtitles like Hebrew, Arabic, Thai, etc..
Some asian language are working, you can try an easy solution, so set the Arial font in the Kodi Skin and in the Kodi subtitles settings. There are also other solutions that provide for example the replacement of fonts in the Kodi skins, the best thing is to get information through the forum of Kodi.

#### I always see subtitles in every video

Just change how Kodi handles subtitles by choosing *forced only*.
In Kodi Settings -> Player -> Language
set: `Preferred subtitle language` to `Forced only`

#### In TV Shows subtitles don't always keep the language of your choice

The Kodi 18.x framework does not allow to fix this problem. So there is no solution.<br/>
If you prefer you can disable `Remember audio / subtitle preferences` in the addon Playback settings, so in each video you will manually enable the subtitles.

### My watched status is not being updated on website or apps

The addon does not report watched status back to Netflix (yet).

### How to export to Kodi library

The export of TV shows and movies in Kodi library allows you to take advantage of Kodi powerful browser, with the features offered by the information providers like TMDB TV show screaper.

To enhance this experience, Netflix add-on offers two export automation features:<br/>
- Auto-updates of the TV shows, in order to export automatically new seasons and episodes.
- Auto-sync with Netflix "My List" of an profile, in order to automatically synchronize the content of Kodi library.

[Click here to open the Wiki page with the instructions](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-to-export-and-sync-tv-shows-and-movies-in-Kodi-library)

### How to share the exported content in the library with multiple devices

Is possible to share the same Kodi/Netflix library with multiple devices where each device has its own Kodi installation.
In order to work it is necessary use Kodi with a MySQL server.

[Click here to open the Wiki page with the instructions](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Library-settings)

### Notice for the use of auto-update and auto-sync with Netflix "My List" feature

AN INTENSIVE USE OF THIS FEATURES due to many exported tv shows MAY CAUSE A TEMPORARY BAN OF THE ACCOUNT that varies starting from 24/48 hours. Use at your own risk.

If it happens often, there is the possibility to exclude the auto update from the tv shows, by open context menu on a tv show and selecting `Exclude from auto update`.

## Something doesn't work

If something doesn't work for you, please:
1. Open add-on settings, go to in Expert page and change `Debug logging level` to `Verbose`
2. Enable the Debug log in your Kodi settings
3. Perform the actions that cause the error, so they are written in the log
4. Open a new github issue (of type *Problem report*) by following the instructions in the report

We can't help you if you don't provide detailed information (i.e. explanation and full debug log) on your issue.
Please also use a service like pastebin or better [Kodi paste](http://paste.kodi.tv) to provide logs and refrain from uploading them to where they'll be hidden behind an ad-wall or any other sketchy services.

When the problem will be solved, remember to disable the debug logging, to avoid unnecessary slowing down in your device.

## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## License

Licensed under The MIT License.
