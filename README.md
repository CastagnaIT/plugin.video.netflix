# Netflix Plugin for Kodi (plugin.video.netflix)

[![Kodi version](https://img.shields.io/badge/kodi%20versions-19--20-blue)](https://kodi.tv/)
[![GitHub release](https://img.shields.io/github/release/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/releases)
[![CI](https://github.com/castagnait/plugin.video.netflix/workflows/CI/badge.svg)](https://github.com/castagnait/plugin.video.netflix/actions?query=workflow:CI)
[![Code Climate - Maintainability](https://api.codeclimate.com/v1/badges/9fbe3ac732f86c05ff00/maintainability)](https://codeclimate.com/github/CastagnaIT/plugin.video.netflix/maintainability)
[![Codecov status](https://img.shields.io/codecov/c/github/castagnait/plugin.video.netflix/master)](https://codecov.io/gh/castagnait/plugin.video.netflix/branch/master)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributors](https://img.shields.io/github/contributors/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/graphs/contributors)

## Disclaimer

This plugin is not officially commissioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

## Main features

- Access to all profiles and relative My list management
- Show the most used lists such as New releases, Recently added, Netflix originals, ...
- Show trailers lists (by context menu)
- Synchronize the watched status with Netflix service - [How works and limitations](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Sync-of-watched-status-with-Netflix)
- Export and synchronize Kodi library with Netflix
- Share/Sync a Kodi library with multiple devices that using Kodi (requires a MySQL server)
- Capability of 1080P and 4K resolutions (see high resolutions table)
- Dolby Digital Plus and Dolby Digital Atmos (requires a premium account)
- HDR / HDR10 / Dolby Vision only on capable Android devices (requires a premium account)
- Support integration with Up Next add-on (proposes to play the next episode automatically)

## Installation & Updates

**[How to install with automatic updates](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-install-the-addon)**

#### Quick download links

Install add-on via repository - provide automatic installation of updates:<br/>
[CastagnaIT Repository for Kodi - repository.castagnait-2.0.0.zip](https://github.com/castagnait/repository.castagnait/raw/kodi/repository.castagnait-2.0.0.zip)<br/>
_**NOTICE FOR KODI v18**: Support and development for Kodi v18 has been stopped [#975](https://github.com/CastagnaIT/plugin.video.netflix/issues/975), use Kodi v19 or above._

Install add-on manually - updates should always be installed manually:<br/>
https://castagnait.github.io/repository.castagnait/ (url to add in the Kodi file manager)

## Login with Authentication key

An alternative login method to avoid "incorrect password" error
* [How to login with Authentication key - wiki](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Login-with-Authentication-key)

## Reference table of high resolutions

This table explains in brief the availability of high resolutions between devices and operating systems. This may change over time based on changes made by Netflix itself.

Unlike official apps (on Smart TV or certified TV Boxes) in some cases using this add-on there are some limitations.
Here Netflix could provide the same TV shows/movies with lower resolutions, this mostly depends on the type of system/device in use.
Devices with more limited resolutions are all those that use Linux operating system (certified Android excluded). Even between different Linux machines there may be differences.

| System                              | 1080P     | 4K      | Video Decoding             |
| ----------------------------------- | --------- | ------- | -------------------------- |
| Windows                             | ✔️\*1     | ❌\*2  | Software                   |
| Linux (Android) \*5                 | ✔️\*1, \*3| ✔️\*4  | Software \\ Hardware \*4   |
| Linux (Distributions)               | ✔️\*1     | ❌\*2  | Software                   |
| Linux (OSMC-CoreElec-LibreELEC-...) | ✔️\*1     | ❌\*2  | Software                   |
| MacOS                               | ✔️\*1     | ❌\*2  | Software                   |
| iOS / tvOS                          | ❌        | ❌     | Not supported              |

<sub><br/>
*1 <b>With Software decoding 1080P is not guaranteed.</b><br/>
*2 Currently not available due to widevine limitations.<br/>
*3 To to have a chance to have all the videos at 1080P you must meet \*4 requirements.<br/>
*4 Hardware decoding and 4k are supported only to devices with Netflix certification, Widevine Security Level L1 and HDCP 2.2 hardware.<br/>
*5 Some android devices do not work properly, this is due to restrictions implemented by netflix with devices with false certifications (often with some Chinese boxes) in rare cases even happened to not being able to play the videos.
</sub>

In order to have a better chance to have high resolutions, we suggest to use the following operating systems:<br/>
Windows (x86/x64), MacOS, Certified Android (better with Netflix certification)

[List of known and tested android devices for 1080P and 4K playback](https://github.com/CastagnaIT/plugin.video.netflix/wiki/List-of-1080P-4k-Android-tested-devices)

#### For video playback problems or 4K problems, BEFORE open an Issue:

- [Try read the FAQ on Wiki page for the common playback problems](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Audio%2C-Video%2C-Subtitle%2C-Other%29)
- [Try ask for help to the official Kodi forum](https://forum.kodi.tv/showthread.php?tid=329767)

## YOU NEED OTHER HELP? Read the Wiki page!

What you can find?

FAQs:

- [FAQ with how to for common problems with Audio, Video, Subtitles and other](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Audio%2C-Video%2C-Subtitle%2C-Other%29)
- [FAQ with how to for common errors](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Errors%29)

Some guides like:
- [How to export to Kodi library and use auto-sync](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-to-export-and-sync-tv-shows-and-movies-in-Kodi-library)
- [How to share the exported content in the library with multiple devices](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Share-STRM-library-with-multiple-devices)
- [How works and limitations of the synchronisation of watched status with Netflix](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Sync-of-watched-status-with-Netflix)

And much more...

[***Click here to open the Wiki page or click on Wiki button***](https://github.com/CastagnaIT/plugin.video.netflix/wiki)

## Notice for the use of auto-update and auto-sync with Netflix "My List" feature

AN INTENSIVE USE OF THIS FEATURES due to many exported tv shows MAY CAUSE A TEMPORARY BAN OF THE ACCOUNT that varies starting from 24/48 hours. Use at your own risk.

If it happens often, there is the possibility to exclude the auto update from the tv shows, by open context menu on a tv show and selecting `Exclude from auto update`.

## Something doesn't work

***Before open a new Issue and engage the developers, please try to find your answer on other channels like:
old closed Issues (on Issue tab), the Wiki pages or ask in the Kodi forum.***

If you have encountered an error or misbehaviour:
1. Open add-on `Expert` settings and turn on `Enable debug logging` setting, then press OK button
2. Enable Kodi debug, go to Kodi `Settings` > `System Settings` > `Logging` and enable `Enable debug logging`
3. Perform the actions that cause the error, so they are written in the log file
4. Open a new GitHub Issue (of type *Bug report*) and fill in the page with detailed information
5. Attach/link in your Issue thread the log file is mandatory (follow rules below)

Rules for the log:
- You can attach the log file or use a service like [Kodi paste](http://paste.kodi.tv) to make a link
- Do not paste the content of the log directly into a Issue or message
- Do not cut, edit or remove parts of the log (there are no sensitive data)

When the problem will be solved, remember to disable the debug logging, to avoid unnecessary slowing down in your device.

**Why my Issue is labeled with ![Ignored rules](https://img.shields.io/badge/-Ignored%20rules-red) ?**

This happens when the guidelines for compiling the Issue thread have not been followed. Therefore if the information will not be filled and or changed in the right way, the Issue post will be closed in the next days.


## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## License

Licensed under The MIT License.

## Support the project

[Info for contribute and donations](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Contribute-and-donations)
