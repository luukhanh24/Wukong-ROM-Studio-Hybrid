# DC Cloud secondary artifact mirror

Google Drive remains the canonical artifact provider and is the value exposed
as `publicUrl`. DC Cloud is an opt-in, best-effort mirror used only by the two
Linux GitHub Actions routes (hosted and `wukong-rom` self-hosted).

## Production mode: Cloudflare-safe WebDAV multipart

The production configuration splits each ROM into 64 MiB raw parts before it
uses the existing scoped WebDAV device. This keeps every request below the
Cloudflare upload limit and needs no DNS, administrator access, CAPTCHA bypass,
browser cookie, or Cloudreve refresh token.

1. Keep `WukongROM/ROM` as the read-only public share and
   `WukongROM/_staging` outside the share.
2. Set the repository variables below. Keep the feature flag disabled until
   preflight and the representative ROM repair both pass.

   ```text
   WUKONG_DCCLOUD_MIRROR_ENABLED=false
   WUKONG_DCCLOUD_UPLOAD_MODE=multipart
   WUKONG_DCCLOUD_REMOTE=wukong-dccloud
   WUKONG_DCCLOUD_ROOT=ROM
   WUKONG_DCCLOUD_SHARE_URL=https://cloud.dabeecao.org/...
   WUKONG_DCCLOUD_CLOUDREVE_VERSION=4.18.0
   ```

Each upload first enters `WukongROM/_staging/<job_id>`, outside the public
share. Verified parts are server-side copied to `<artifact>.parts`; numbered
parts and reconstruction scripts become usable only after `manifest.json` is
published last. A retry downloads and checks SHA-256 before reusing any part.
The preflight workflow can run 100 MiB or 1 GiB round-trip canaries and removes
only its unique `_canary` folder afterwards.

## Optional Cloudreve native mode

The repository retains a native REST uploader for installations that can issue
a refresh token without interactive CAPTCHA. The current DC Cloud login is
protected by Turnstile, so this mode is not used for production and the
password bootstrap cannot complete on this account. Do not copy browser
cookies or attempt to bypass CAPTCHA.

## Legacy single-PUT WebDAV mode

1. Confirm Cloudreve is `>= 4.16.1` before granting a scoped WebDAV account;
   older releases are affected by [GHSA-w5fv-7x5q-g8qp](https://github.com/cloudreve/cloudreve/security/advisories/GHSA-w5fv-7x5q-g8qp).
2. Create `WukongROM/ROM` (public artifacts) and `WukongROM/_staging`
   (private, temporary uploads). Do not include `_staging` in the share.
3. Create a writable WebDAV device account rooted at `My Files/WukongROM`.
   Enable dot-file blocking and disable reverse-proxy mode. The device
   credential is stored only inside `RCLONE_CONFIG_B64`.
4. Create a non-expiring share for `WukongROM/ROM` with anonymous `Read`
   permission only. Upload/create/update/delete must be denied.
5. Add a `[wukong-dccloud]` WebDAV remote (`vendor = other`) to the private
   rclone config. Never commit its URL, username, or password.
6. Keep the WebDAV hostname DNS-only (not Cloudflare-proxied). If the public
   Cloudreve hostname is proxied, set `WUKONG_DCCLOUD_WEBDAV_URL` to a direct
   HTTPS hostname such as `https://dav.dabeecao.org/dav`; WebDAV uses a
   single-stream PUT and Cloudflare's request-size limit will reject multi-GB
   ROMs before they reach Cloudreve.

The device account is already scoped to `My Files/WukongROM`, so the rclone
paths used by the mirror start at `wukong-dccloud:ROM/...` (not a second
`WukongROM` segment).

For installations with a DNS-only direct hostname, set these repository
variables instead:

```text
WUKONG_DCCLOUD_MIRROR_ENABLED=false
WUKONG_DCCLOUD_UPLOAD_MODE=webdav
WUKONG_DCCLOUD_REMOTE=wukong-dccloud
WUKONG_DCCLOUD_ROOT=ROM
WUKONG_DCCLOUD_SHARE_URL=https://cloud.dabeecao.org/...
WUKONG_DCCLOUD_WEBDAV_URL=https://dav.dabeecao.org/dav
WUKONG_DCCLOUD_CLOUDREVE_VERSION=4.16.1
```

The optional `WUKONG_DCCLOUD_WEBDAV_URL` overrides only the WebDAV transport
URL at runtime; the public share URL remains `WUKONG_DCCLOUD_SHARE_URL`.
Use the **DC Cloud · Direct WebDAV hostname** workflow to inspect or provision
the DNS-only hostname after confirming the Cloudflare token has DNS-edit
permission. Do not enable the override until the hostname resolves directly
to the Cloudreve origin and accepts the WebDAV device certificate.

When enabled, `run-hybrid` verifies the selected transport, creates/removes a harmless
probe in `_staging`, checks the anonymous share, and records quota warnings at
80%. A failed mirror never changes a successful build to failed. Run the
manual **Wukong DC Cloud mirror repair** workflow with a `job_id` to download
and checksum the Drive artifact, then retry the mirror.

## Automatic recovery

When an initial mirror upload fails, the executor retries from the local ZIP
after the canonical Drive upload completes. This first repair does not depend
on Drive and runs while the build runner still owns the original artifact.

If the terminal manifest still contains a failed DC Cloud mirror, the control
plane atomically adds one repair request to its D1 outbox. It dispatches
`mirror-repair.yml` immediately and retries a failed dispatch from the minute
maintenance trigger, with a maximum of five dispatch attempts. Repeated
terminal callbacks do not create duplicate repair requests. The repair workflow
falls back to the Google Drive file ID when the stored artifact path cannot be
resolved, then verifies the downloaded size and SHA-256 before uploading.
