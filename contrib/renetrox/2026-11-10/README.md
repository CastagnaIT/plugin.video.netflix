# Field report: restoring Netflix on Kodi Flatpak (Nov 10, 2026)

**Environment:** Debian 12 x86_64, Kodi Flatpak (tv.kodi.Kodi), CastagnaIT `1.23.5+matrix.1`. One local installation. This report contains no account credentials, auth keys, cookies or DRM binaries.

The following **three independent** experimental changes restored login, video, and artwork in the reported configuration. Their local success does not establish compatibility with other installations.

## 1) Authentication: HTTP 404 at retired profilehub

After updating from `1.23.3`, which had `InvalidAuthURLError`, importing a locally generated `NFAuthentication.key` encountered:
`HTTPError 404: /api/shakti/mre/profilehub` during the account password's secondary parental-control verification.

A *local temporary bypass* of **only that endpoint's HTTP 404** allowed login to complete. See `profilehub-404-EXPERIMENTAL.patch` and upstream [issue #1806](https://github.com/CastagnaIT/plugin.video.netflix/issues/1806).

**Security warning:** The workaround skips secondary password verification when this route returns 404. This is **not an adequate security-correct upstream fix**, must not be broadly generalized, and does not prove the supplied password was validated. A supported verification flow is required before merging a solution.

## 2) Black picture with working audio

After login, the catalog and audio worked but the displayed video was black. Removing `PROFILES['h264_prk_qc']` from `enabled_profiles()` in `resources/lib/services/nfsession/msl/profiles.py` restored picture and sound in the test environment.

A matching upstream proposal already exists: [PR #1791](https://github.com/CastagnaIT/plugin.video.netflix/pull/1791). **Please review/merge that PR instead of treating this as an independent discovery.** A copy of the tested change is also on this fork's `fix/h264-prkqc-audio-only-20261110` branch for reproducibility.

## 3) Missing backgrounds and horizontal artwork

Vertical covers still appeared, while background fanarts and horizontal art were missing. An experimental `DetailModal` GraphQL bridge was installed that:
- Reused CastagnaIT's existing authenticated NF session and IPC
- Requested a persisted `DetailModal` operation and parsed `StoryArt`, `sdp`, branded/unbranded logos
- Enriched Kodi `ListItem.setArt()` and used the old art as fallback
- Cached per-title results and capped requests to 12 new titles per listing
- Did not change authentication, playback, or Widevine

Afterwards the user reported that fanart and horizontal art were visible. A screenshot was taken. **This screenshot is not proof that all artwork originated from GraphQL**: individual live responses were not inspected, and multi-title coverage, session expiry, per-profile caching and performance remain unverified.

The GraphQL operation ID, protocol and artwork mapping come from the **original researcher** in [issue #1807](https://github.com/CastagnaIT/plugin.video.netflix/issues/1807) and [their branch](https://github.com/shithead/plugin.video.netflix/tree/netflix-api-rework). That branch's GraphQL client and tests should be preferred over competing code. An experimental integration branch is provided separately as `experiment/graphql-artwork-flatpak-20261110`; it is **not merge-ready**.

## Coordination / upstream suggestions

- Keep auth / playback / artwork fixes separate.
- Follow existing work in [#1791](https://github.com/CastagnaIT/plugin.video.netflix/pull/1791), [#1796](https://github.com/CastagnaIT/plugin.video.netflix/pull/1796), [#1803](https://github.com/CastagnaIT/plugin.video.netflix/pull/1803), [#1806](https://github.com/CastagnaIT/plugin.video.netflix/issues/1806), [#1807](https://github.com/CastagnaIT/plugin.video.netflix/issues/1807).
- For authentication, replace retired validation with a supported flow rather than shipping a bypass.
- For artwork, add production UI wiring to the original research with cache and non-blocking collection strategies, then run network tests and review errors.
- Do not distribute real `NFAuthentication.key`, cookies, PINs, account passwords, license information or session data.

This report and proof of concept were prepared with AI assistance; credit for existing upstream work belongs to its original authors.
