import { ZIP_MAX_CLIENT_BYTES, ZIP_MAX_METADATA_FIELDS, ZIP_MAX_METADATA_FILES, ZIP_MAX_METADATA_FILE_BYTES, ZIP_MAX_METADATA_TEXT_BYTES, ZIP_MAX_RANGE_BYTES, ZIP_METADATA_SUFFIXES } from "./state.js";

function zipNumber(value, label) {
  const maximum = BigInt(Number.MAX_SAFE_INTEGER);
  if (typeof value === "bigint") {
    if (value < 0n || value > maximum) throw new Error(`${label} exceeds the browser ZIP limit`);
    return Number(value);
  }
  if (!Number.isSafeInteger(value) || value < 0) throw new Error(`${label} is invalid`);
  return value;
}

async function fetchProbeRange(session, start, end, signal) {
  if (!session?.url || !Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end < start) {
    throw new Error("ROM range session is invalid");
  }
  const length = end - start + 1;
  if (length > ZIP_MAX_RANGE_BYTES) throw new Error("ROM ZIP range exceeds 8 MiB");
  const response = await fetch(session.url, {
    headers: { Range: `bytes=${start}-${end}` },
    cache: "no-store",
    signal
  });
  if (response.status !== 206) throw new Error(`ROM range returned HTTP ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength !== length) throw new Error("ROM range length does not match the request");
  return bytes;
}

async function fetchProbeBytes(session, start, length, signal) {
  if (!Number.isSafeInteger(length) || length < 0 || length > ZIP_MAX_CLIENT_BYTES) {
    throw new Error("ROM ZIP metadata exceeds the 16 MiB inspection budget");
  }
  const chunks = [];
  let offset = 0;
  while (offset < length) {
    const chunkLength = Math.min(ZIP_MAX_RANGE_BYTES, length - offset);
    chunks.push(await fetchProbeRange(
      session,
      start + offset,
      start + offset + chunkLength - 1,
      signal
    ));
    offset += chunkLength;
  }
  const output = new Uint8Array(length);
  let outputOffset = 0;
  chunks.forEach((chunk) => {
    output.set(chunk, outputOffset);
    outputOffset += chunk.byteLength;
  });
  return output;
}

function findZipSignature(bytes, signature) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let offset = bytes.byteLength - 4; offset >= 0; offset -= 1) {
    if (view.getUint32(offset, true) === signature) return offset;
  }
  return -1;
}

function zip64Extra(extra, needs) {
  const view = new DataView(extra.buffer, extra.byteOffset, extra.byteLength);
  let offset = 0;
  while (offset + 4 <= extra.byteLength) {
    const id = view.getUint16(offset, true);
    const length = view.getUint16(offset + 2, true);
    const start = offset + 4;
    const end = start + length;
    if (end > extra.byteLength) throw new Error("ZIP extra field is truncated");
    if (id === 0x0001) {
      let cursor = start;
      const values = {};
      for (const name of ["uncompressedSize", "compressedSize", "localOffset", "disk"]) {
        if (!needs[name]) continue;
        const width = name === "disk" ? 4 : 8;
        if (cursor + width > end) throw new Error("ZIP64 extra field is truncated");
        values[name] = width === 8
          ? zipNumber(view.getBigUint64(cursor, true), `ZIP64 ${name}`)
          : view.getUint32(cursor, true);
        cursor += width;
      }
      return values;
    }
    offset = end;
  }
  return {};
}

async function zipDirectory(result, signal) {
  const size = zipNumber(Number(result?.sizeBytes), "ROM size");
  if (size < 22) throw new Error("ROM ZIP is too small");
  const session = result?.rangeSession;
  const tailLength = Math.min(size, 65557);
  const tailStart = size - tailLength;
  const tail = await fetchProbeBytes(session, tailStart, tailLength, signal);
  const eocdOffset = findZipSignature(tail, 0x06054b50);
  if (eocdOffset < 0 || eocdOffset + 22 > tail.byteLength) {
    throw new Error("ROM ZIP central directory was not found");
  }
  const view = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
  let entryCount = view.getUint16(eocdOffset + 10, true);
  let directorySize = view.getUint32(eocdOffset + 12, true);
  let directoryOffset = view.getUint32(eocdOffset + 16, true);
  if (entryCount === 0xffff || directorySize === 0xffffffff || directoryOffset === 0xffffffff) {
    const locatorOffset = findZipSignature(tail.slice(0, eocdOffset), 0x07064b50);
    if (locatorOffset < 0 || locatorOffset + 20 > tail.byteLength) {
      throw new Error("ROM ZIP64 locator was not found");
    }
    const zip64Offset = zipNumber(view.getBigUint64(locatorOffset + 8, true), "ZIP64 directory offset");
    const zip64Header = await fetchProbeBytes(session, zip64Offset, 56, signal);
    const zip64View = new DataView(zip64Header.buffer, zip64Header.byteOffset, zip64Header.byteLength);
    if (zip64View.getUint32(0, true) !== 0x06064b50) throw new Error("ROM ZIP64 directory is invalid");
    entryCount = zipNumber(zip64View.getBigUint64(32, true), "ZIP64 entry count");
    directorySize = zipNumber(zip64View.getBigUint64(40, true), "ZIP64 directory size");
    directoryOffset = zipNumber(zip64View.getBigUint64(48, true), "ZIP64 directory offset");
  }
  if (directorySize > ZIP_MAX_CLIENT_BYTES - tailLength) {
    throw new Error("ROM ZIP central directory exceeds the inspection budget");
  }
  if (directoryOffset + directorySize > size || entryCount > 1000000) {
    throw new Error("ROM ZIP central directory is invalid");
  }
  return {
    entries: entryCount,
    bytes: await fetchProbeBytes(session, directoryOffset, directorySize, signal)
  };
}

function metadataZipEntries(directory) {
  const bytes = directory.bytes;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const decoder = new TextDecoder("utf-8", { fatal: false });
  const entries = [];
  let offset = 0;
  let parsed = 0;
  while (offset < bytes.byteLength && parsed < directory.entries) {
    if (offset + 46 > bytes.byteLength || view.getUint32(offset, true) !== 0x02014b50) {
      throw new Error("ROM ZIP central directory entry is invalid");
    }
    const flags = view.getUint16(offset + 8, true);
    const method = view.getUint16(offset + 10, true);
    let compressedSize = view.getUint32(offset + 20, true);
    let uncompressedSize = view.getUint32(offset + 24, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    let localOffset = view.getUint32(offset + 42, true);
    const end = offset + 46 + nameLength + extraLength + commentLength;
    if (end > bytes.byteLength) throw new Error("ROM ZIP central directory is truncated");
    const name = decoder.decode(bytes.subarray(offset + 46, offset + 46 + nameLength));
    const extra = bytes.subarray(
      offset + 46 + nameLength,
      offset + 46 + nameLength + extraLength
    );
    const zip64 = zip64Extra(extra, {
      uncompressedSize: uncompressedSize === 0xffffffff,
      compressedSize: compressedSize === 0xffffffff,
      localOffset: localOffset === 0xffffffff,
      disk: view.getUint16(offset + 34, true) === 0xffff
    });
    uncompressedSize = zip64.uncompressedSize ?? uncompressedSize;
    compressedSize = zip64.compressedSize ?? compressedSize;
    localOffset = zip64.localOffset ?? localOffset;
    const normalized = name.replaceAll("\\", "/").toLowerCase();
    if (ZIP_METADATA_SUFFIXES.some((suffix) => normalized.endsWith(suffix))) {
      if (uncompressedSize <= ZIP_MAX_METADATA_FILE_BYTES) {
        entries.push({
          name,
          method,
          compressedSize,
          uncompressedSize,
          localOffset,
          encrypted: Boolean(flags & 1)
        });
        if (entries.length > ZIP_MAX_METADATA_FILES) {
          throw new Error("ROM ZIP exposes too many metadata files");
        }
      }
    }
    parsed += 1;
    offset = end;
  }
  return entries;
}

async function readMetadataZipEntry(session, entry, sourceSize, signal) {
  if (entry.encrypted) throw new Error("Encrypted ROM metadata is not supported");
  if (entry.compressedSize > ZIP_MAX_RANGE_BYTES) {
    throw new Error(`ROM metadata file is too large: ${entry.name}`);
  }
  // Metadata files are normally tiny. Prefetch the local header and first
  // 64 KiB together so the common case needs one network round-trip.
  const prefetchLength = Math.min(
    ZIP_MAX_RANGE_BYTES,
    zipNumber(Number(sourceSize), "ROM size") - entry.localOffset,
    Math.max(64 * 1024, 30 + entry.compressedSize)
  );
  if (prefetchLength < 30) throw new Error("ROM ZIP local header is truncated");
  const prefetched = await fetchProbeBytes(session, entry.localOffset, prefetchLength, signal);
  const header = prefetched.subarray(0, 30);
  const view = new DataView(header.buffer, header.byteOffset, header.byteLength);
  if (view.getUint32(0, true) !== 0x04034b50) throw new Error("ROM ZIP local header is invalid");
  const nameLength = view.getUint16(26, true);
  const extraLength = view.getUint16(28, true);
  const relativeDataOffset = 30 + nameLength + extraLength;
  let compressed;
  if (relativeDataOffset + entry.compressedSize <= prefetched.byteLength) {
    compressed = prefetched.subarray(relativeDataOffset, relativeDataOffset + entry.compressedSize);
  } else {
    const dataOffset = entry.localOffset + relativeDataOffset;
    compressed = await fetchProbeBytes(session, dataOffset, entry.compressedSize, signal);
  }
  let content;
  if (entry.method === 0) content = compressed;
  else if (entry.method === 8) content = (await import("../lib/vendor/fflate.js")).inflateSync(compressed);
  else throw new Error(`Unsupported ROM metadata compression method: ${entry.method}`);
  if (content.byteLength !== entry.uncompressedSize || content.byteLength > ZIP_MAX_METADATA_FILE_BYTES) {
    throw new Error("ROM ZIP metadata file exceeds the inspection limit");
  }
  return content;
}

function firstMetadata(metadata, ...keys) {
  return keys.map((key) => metadata[key]).find(Boolean) || "";
}

function metadataAndroidVersion(metadata, version) {
  const explicit = firstMetadata(metadata, "android-version", "post-android-version");
  if (explicit) return explicit;
  const sdk = firstMetadata(metadata, "post-sdk-level", "sdk-level");
  const versions = { 36: "16", 35: "15", 34: "14", 33: "13", 32: "12L", 31: "12", 30: "11", 29: "10" };
  return versions[sdk] || String(version || "").match(/(?:^|_)(\d{2})(?:\.|_)/)?.[1] || "";
}

function metadataBuildDate(metadata) {
  const explicit = firstMetadata(metadata, "build-date", "post-build-date", "build-timestamp");
  if (explicit) return explicit.replace("T", " ").replace(/Z$/, "");
  let timestamp = Number(firstMetadata(metadata, "post-timestamp", "timestamp"));
  if (Number.isFinite(timestamp) && timestamp > 0) {
    if (timestamp > 10000000000) timestamp = Math.floor(timestamp / 1000);
    return new Date(timestamp * 1000).toISOString().replace("T", " ").slice(0, 19);
  }
  const otaBuild = firstMetadata(metadata, "ota-build");
  const match = otaBuild.match(/_(\d{12})(?:\D|$)/);
  if (!match) return "";
  const value = match[1];
  return `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)} ${value.slice(8, 10)}:${value.slice(10, 12)}:00`;
}

async function inspectProbeZipMetadata(result, signal) {
  if (
    !result?.rangeSession ||
    !Number.isSafeInteger(Number(result.sizeBytes)) ||
    Number(result.sizeBytes) <= 0 ||
    !String(result.filename || "").toLowerCase().endsWith(".zip")
  ) return result;
  const directory = await zipDirectory(result, signal);
  const entries = metadataZipEntries(directory);
  const metadata = {};
  let totalTextBytes = 0;
  const contents = new Array(entries.length);
  const failures = [];
  let nextEntry = 0;
  const readNext = async () => {
    while (nextEntry < entries.length) {
      const index = nextEntry;
      nextEntry += 1;
      try {
        contents[index] = await readMetadataZipEntry(
          result.rangeSession,
          entries[index],
          result.sizeBytes,
          signal
        );
      } catch (error) {
        if (signal?.aborted) throw error;
        failures.push(entries[index].name);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(3, entries.length) }, readNext));
  for (const content of contents.filter(Boolean)) {
    totalTextBytes += content.byteLength;
    if (totalTextBytes > ZIP_MAX_METADATA_TEXT_BYTES) {
      throw new Error("ROM ZIP metadata exceeds the 4 MiB text limit");
    }
    new TextDecoder("utf-8", { fatal: false }).decode(content).split(/\r?\n/).forEach((line) => {
      const separator = line.indexOf("=");
      if (separator <= 0) return;
      const key = line.slice(0, separator).trim().toLowerCase().replaceAll("_", "-");
      if (!key || key.length > 128) return;
      metadata[key] = line.slice(separator + 1).trim().slice(0, 1024);
      if (Object.keys(metadata).length > ZIP_MAX_METADATA_FIELDS) {
        throw new Error("ROM ZIP metadata contains too many fields");
      }
    });
  }
  if (!Object.keys(metadata).length) {
    return {
      ...result,
      warning: failures.length
        ? "ROM ZIP metadata files could not be read"
        : "ROM ZIP does not expose recognized metadata files"
    };
  }
  const productName = firstMetadata(metadata, "oplus-product-name", "product-name");
  const device = firstMetadata(metadata, "pre-device", "product-name", "oplus-product-name");
  const version = firstMetadata(
    metadata,
    "oplus-version-name",
    "version-name",
    "post-build-incremental",
    "post-build"
  );
  return {
    ...result,
    productName,
    device,
    version,
    androidVersion: metadataAndroidVersion(metadata, version),
    securityPatch: firstMetadata(metadata, "post-security-patch-level"),
    buildDate: metadataBuildDate(metadata),
    otaType: firstMetadata(metadata, "ota-type"),
    deepInspected: true,
    warning: failures.length
      ? `${failures.length} ROM metadata file(s) could not be read`
      : null,
    metadata
  };
}

export { zipNumber, fetchProbeRange, fetchProbeBytes, findZipSignature, zip64Extra, zipDirectory, metadataZipEntries, readMetadataZipEntry, firstMetadata, metadataAndroidVersion, metadataBuildDate, inspectProbeZipMetadata };
