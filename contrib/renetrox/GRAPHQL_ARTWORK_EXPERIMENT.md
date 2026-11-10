# Experimental Netflix GraphQL artwork bridge — review notes

This branch is a **proof of concept** based on the art mapping and persisted `DetailModal` operation researched in [upstream issue #1807](https://github.com/CastagnaIT/plugin.video.netflix/issues/1807). It is *not* a new claim to that discovery and should be reviewed as possible UI-wiring guidance, **not** a replacement for the researcher's GraphQL transport/client and tests.

## Changes

- `resources/lib/services/nfsession/session/endpoints.py`: register an absolute-document-host `/graphql` JSON endpoint using the existing authenticated session.
- `resources/lib/services/nfsession/nfsession_ops.py`: add an NFSession IPC slot for optional artwork.
- `resources/lib/services/nfsession/renetrox_artwork_graphql.py`: request `DetailModal`, scope `Image` nodes to video ID, map `StoryArt`/sdp/logos to Kodi art fields, reject non-Netflix image hosts.
- `resources/lib/kodi/renetrox_artwork_cache.py`: cache per profile/video/language, limit new requests to 12 per plugin invocation; on error use existing art.
- `resources/lib/kodi/infolabels.py`: enrich `ListItem.setArt()` after existing information is constructed.

**No changes** to `access.py`, video profiles, inputstream.adaptive, Widevine, PINs, account keys or credentials.

## What was and was not verified

A local installer variant of this approach was applied on Kodi Flatpak/ Debian 12 x86_64, CastagnaIT 1.23.5+matrix.1. The user saw background fanart and horizontal cards and reported that Netflix had recovered. Installer/rollback and image extraction were tested offline with synthetic data.

This branch is an **upstream-oriented adaptation** (including profile-aware cache keys) and has **not itself been deployed and tested end-to-end** on that installation. The screenshot is an after-only illustration, not proof of live GraphQL responses. The underlying persisted query was observed by the original researcher in October 2026, not freshly revalidated.

## Before upstream merging

1. Prefer reusing the branch/client/tests from #1807. This branch has a small independent transport for experimental review only.
2. Replace synchronous per-card IPC with batching, lazy loading or a background artwork queue. Twelve queries per plugin invocation is a temporary circuit-breaker, not real per-menu paging.
3. Add tests for response errors, session renewal, per-profile cache scoping, Kodi artwork labels, version/operation expiry and UI regressions.
4. Test against the developer's broader API migration in #1796/#1803.
5. Do not combine with the separate experimental `profilehub` authentication workaround. See #1806.
