# DC Cloud secondary artifact mirror

Google Drive remains the canonical artifact provider and is the value exposed
as `publicUrl`. DC Cloud is an opt-in, best-effort mirror used only by the two
Linux GitHub Actions routes (hosted and `wukong-rom` self-hosted).

## Provisioning checklist

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

The device account is already scoped to `My Files/WukongROM`, so the rclone
paths used by the mirror start at `wukong-dccloud:ROM/...` (not a second
`WukongROM` segment).

Set these repository variables (the first one stays `false` until preflight
and a canary are complete):

```text
WUKONG_DCCLOUD_MIRROR_ENABLED=false
WUKONG_DCCLOUD_REMOTE=wukong-dccloud
WUKONG_DCCLOUD_ROOT=ROM
WUKONG_DCCLOUD_SHARE_URL=https://cloud.dabeecao.org/...
WUKONG_DCCLOUD_CLOUDREVE_VERSION=4.16.1
```

When enabled, `run-hybrid` verifies the remote, creates/removes a harmless
probe in `_staging`, checks the anonymous share, and records quota warnings at
80%. A failed mirror never changes a successful build to failed. Run the
manual **Wukong DC Cloud mirror repair** workflow with a `job_id` to download
and checksum the Drive artifact, then retry the mirror.
