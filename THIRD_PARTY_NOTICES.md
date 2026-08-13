# Third-party notices

Wukong ROM Studio contains and invokes third-party software. The root
`LICENSE` applies to original Wukong code unless a file or bundled work carries
its own notice. Existing notices and copyright headers must be preserved.

## MIO-KITCHEN-SOURCE

Files under `src/` that identify MIO-KITCHEN-SOURCE, including utilities used
by image extraction and payload handling, are licensed under GNU Affero General
Public License 3.0 as stated in those files. The original project is available
at <https://github.com/ColdWindScholar/MIO-KITCHEN-SOURCE>.

The pinned Linux runtime manifest also downloads selected standalone executables
from commit `a14828fdee37c402b32662ab48c4ea96f8a68ce9`. Their URLs, hashes and licenses
are recorded in `tools/linux-x86_64.json`. Distribution or network deployment of
the combined application must satisfy all applicable AGPL-3.0 requirements;
the GPL-3.0 label for new Wukong modules does not override those notices.

## Apktool

Apktool 3.0.2 is licensed under Apache License 2.0. Source:
<https://github.com/iBotPeaches/Apktool/tree/v3.0.2>.

## Android platform tools and filesystem utilities

The repository/runtime includes or invokes Android platform tools, e2fsprogs,
EROFS utilities, 7-Zip, GNU cpio, Brotli, Zstandard, Java, Python and .NET.
Each remains under its upstream license. Existing notices under `Flash_script`
and `bin/Windows/AMD64/7z.License.txt` are retained.

## Content-packs

APK, APEX, recovery images, firmware and other content-packs are not relicensed
under GPL-3.0 merely because Wukong can download or process them. Operators are
responsible for having permission to store, modify and distribute each content
pack and resulting ROM.

