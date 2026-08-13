import argparse
import bz2
import gc
import hashlib
import lzma
import mmap
import os
import queue
import struct
import threading
import time
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor
from io import (
    SEEK_CUR,
    SEEK_SET,
    BufferedWriter,
)
import zstandard
from queue import Queue
from typing import IO, List

import requests

from . import update_metadata_pb2


class BadPayload(Exception):
    def __init__(self, *args):
        super().__init__("Invalid payload:", *args)


PAYLOAD_MAGIC = b"CrAU"


class PayloadHdr(object):
    _fmtstr = ">4sQQI"
    _payload = []

    def __init__(self, data: bytes):
        (
            self.magic,
            self.version,
            self.manifest_len,
            self.manifest_sig_len,
        ) = struct.unpack(self._fmtstr, data)

    def __len__(self) -> int:
        return struct.calcsize(self._fmtstr)


class OrderedFileWriter(object):
    def __init__(
            self,
            file: BufferedWriter,
            max_workers: int
    ):
        self.file = file
        self.task_queue = Queue(max_workers * 2)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.error = None
        self.writer_thread = threading.Thread(target=self._write_worker, daemon=True)
        self.writer_thread.start()  # Start the thread immediately after creation

    def _write_worker(self):
        while not self.stop_event.is_set() or not self.task_queue.empty():
            try:
                pos, data = self.task_queue.get(timeout=0.1)

                if self.error:
                    self.task_queue.task_done()
                    continue
                with self.lock:
                    self.file.seek(pos, SEEK_SET)
                    self.file.write(data)
                    # self.file.flush()
                del data
                self.task_queue.task_done()

                if self.task_queue.qsize() % 10 == 0:
                    gc.collect()
            except queue.Empty:
                continue
            except BaseException as exc:
                self.error = exc
                self.task_queue.task_done()

    def write(self, pos: int, data: bytes):
        while True:
            if self.error:
                raise self.error
            try:
                self.task_queue.put((pos, data), timeout=0.1)
                return
            except queue.Full:
                continue

    def close(self):
        self.task_queue.join()
        self.stop_event.set()
        self.writer_thread.join()
        if self.error:
            raise self.error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False


def init_payload_info(reader: IO[bytes]) -> update_metadata_pb2.DeltaArchiveManifest:
    hdr = PayloadHdr(reader.read(struct.calcsize(PayloadHdr._fmtstr)))

    if hdr.magic != PAYLOAD_MAGIC:
        raise BadPayload("invalid magic")
    if hdr.version != 2:
        print(f"Warning: payload version is {hdr.version} != 2 may be unsupported")
    if hdr.manifest_len == 0:
        raise BadPayload("manifest length is zero")
    if hdr.manifest_sig_len == 0:
        raise BadPayload("manifest signature length is zero")

    manifest = update_metadata_pb2.DeltaArchiveManifest.FromString(
        reader.read(hdr.manifest_len)
    )
    if manifest.minor_version not in [0, 8, 9]:
        raise BadPayload(
            "delta payloads are not supported, please use a full payload file"
        )
    reader.seek(hdr.manifest_sig_len, SEEK_CUR)

    return manifest


def _write_extents(writer, extents, block_size, data):
    expected = sum(ext.num_blocks for ext in extents) * block_size
    if len(data) != expected:
        raise BadPayload(f"extent data length mismatch: expected {expected}, got {len(data)}")
    offset = 0
    for ext in extents:
        length = ext.num_blocks * block_size
        writer.write(ext.start_block * block_size, data[offset:offset + length])
        offset += length


def _write_zero_extents(writer, extents, block_size):
    chunk_size = 4 * 1024 * 1024
    zero_chunk = b"\0" * chunk_size
    for ext in extents:
        position = ext.start_block * block_size
        remaining = ext.num_blocks * block_size
        while remaining:
            length = min(remaining, chunk_size)
            writer.write(position, zero_chunk[:length])
            position += length
            remaining -= length


def _extract_operation_to_file(
        operation: update_metadata_pb2.InstallOperation,
        writer: OrderedFileWriter,
        block_size: int,
        data: bytes,
):
    if operation.data_sha256_hash and hashlib.sha256(data).digest() != operation.data_sha256_hash:
        raise BadPayload("operation data hash mismatch")
    match operation.type:
        case update_metadata_pb2.InstallOperation.REPLACE:
            _write_extents(writer, operation.dst_extents, block_size, data)
        case update_metadata_pb2.InstallOperation.ZERO:
            _write_zero_extents(writer, operation.dst_extents, block_size)
        case (
        update_metadata_pb2.InstallOperation.REPLACE_BZ
        | update_metadata_pb2.InstallOperation.REPLACE_XZ
        | update_metadata_pb2.InstallOperation.REPLACE_ZSTD
        ):
            if operation.type == update_metadata_pb2.InstallOperation.REPLACE_BZ:
                decompressed_data = bz2.decompress(data)
            elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_XZ:
                decompressed_data = lzma.decompress(data)
            elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_ZSTD:
                decompressed_data = zstandard.decompress(data)

            _write_extents(writer, operation.dst_extents, block_size, decompressed_data)

        case _:
            raise BadPayload("unexpected data type")
    del data


def _extract_partition_from_payload(
        reader: IO[bytes],
        block_size: int,
        partition: update_metadata_pb2.PartitionUpdate,
        out_path: str,
        total_size: int,
        executor: ThreadPoolExecutor,
):
    with (
        open(out_path, "wb") as out_file,
        OrderedFileWriter(out_file, executor._max_workers) as writer,
    ):
        out_file.truncate(total_size)  # pre set memory

        curr_data_offset = 0

        futures: List[Future] = []

        for operation in sorted(partition.operations, key=lambda o: o.data_offset):
            data_len = operation.data_length
            data_offset = operation.data_offset

            reader.seek(data_offset - curr_data_offset, SEEK_CUR)

            data = reader.read(data_len)
            if len(data) != data_len:
                raise BadPayload(f"short operation data: expected {data_len}, got {len(data)}")

            curr_data_offset = data_offset + data_len
            if writer:
                futures.append(
                    executor.submit(
                        _extract_operation_to_file,
                        # _extract_operation_to_file(
                        operation,
                        writer,
                        block_size,
                        data,
                    )
                )
            del data

        for future in futures:
            future.result()
        futures.clear()

        print(f"Extract partition: {partition.partition_name:<16} size: {total_size:<10} ... Done!")

    if partition.new_partition_info.hash:
        hasher = hashlib.sha256()
        with open(out_path, "rb") as out_file:
            for chunk in iter(lambda: out_file.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.digest() != partition.new_partition_info.hash:
            raise BadPayload(f"partition hash mismatch: {partition.partition_name}")


def extract_partitions_from_payload(
        reader: IO[bytes],
        partitions_name: List[str] = [],
        out_dir: str = "out",
        max_workers: int = 32,
):
    reader.seek(0, SEEK_SET)

    os.makedirs(out_dir, exist_ok=True)

    manifest = init_payload_info(reader)
    baseoff = reader.tell()

    if len(partitions_name) == 0:
        all_parts = manifest.partitions
    else:
        all_parts = list(
            filter(lambda x: x.partition_name in partitions_name, manifest.partitions)
        )

    block_size = manifest.block_size
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for p in all_parts:
            if not p.partition_name or os.path.basename(p.partition_name) != p.partition_name:
                raise BadPayload("invalid partition name")
            reader.seek(baseoff, SEEK_SET)
            # print(f"Extracting output size: {data_size}")

            total_length = max(
                ext.start_block + ext.num_blocks
                for operation in p.operations
                for ext in operation.dst_extents
            ) * block_size
            # total_length = len(p.operations)
            print(f"Extracting {p.partition_name} ...")
            _extract_partition_from_payload(
                reader,
                block_size,
                p,
                os.path.join(out_dir, p.partition_name + ".img"),
                total_length,
                executor,
            )

            # if progress:
            #    progress.stop_task(task_id)


class SeekableMmap(mmap.mmap):
    def seekable(self) -> bool:  # stub
        return True


class UrlFileReader(IO[bytes]):
    UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        self.total = 0
        self._closed = False

        resp = requests.head(self.url, headers={"User-Agent": self.UA})
        try:
            if resp.status_code == 200:
                if resp.headers.get("Accept-Ranges") != "bytes":
                    raise Exception("URL does not support range requests")
                self.total = int(resp.headers.get("Content-Length", 0))
            else:
                raise Exception(f"HTTP request failed with status {resp.status_code}")
        finally:
            resp.close()

        if self.total == 0:
            raise Exception("Could not determine content length")

        self.stream = None
        self.stream_start = 0
        self.stream_pos = 0

    def seekable(self) -> bool:
        return not self.closed

    def readable(self) -> bool:
        return not self.closed

    @property
    def closed(self) -> bool:
        return self._closed

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file")

        if whence == os.SEEK_SET:
            self.pos = offset
        elif whence == os.SEEK_CUR:
            self.pos += offset
        elif whence == os.SEEK_END:
            self.pos = self.total + offset
        else:
            raise ValueError("Invalid whence value")

        self.pos = max(0, min(self.total, self.pos))
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            raise ValueError("I/O operation on closed file")

        if self.pos >= self.total:
            return b""

        # 初始化或重新定位流
        if self.stream is None or self.stream_start + self.stream_pos != self.pos:
            if self.stream is not None:
                self.stream.close()

            headers = {"User-Agent": self.UA, "Range": f"bytes={self.pos}-"}
            self.stream = requests.get(self.url, headers=headers, stream=True)

            # 检查Range请求是否成功
            if self.stream.status_code not in (200, 206):
                self.stream.close()
                raise Exception(
                    f"Range request failed with status {self.stream.status_code}"
                )

            self.stream_start = self.pos
            self.stream_pos = 0

        # 确定要读取的大小
        if size < 0:
            size = self.total - self.pos
        else:
            size = min(size, self.total - self.pos)

        data = b""
        remaining = size
        while remaining > 0 and not self.stream.raw.closed:
            chunk_size = min(8192, remaining)
            chunk = self.stream.raw.read(chunk_size)
            if not chunk:
                break
            data += chunk
            read_len = len(chunk)
            self.stream_pos += read_len
            self.pos += read_len
            remaining -= read_len

        return data

    def close(self) -> None:
        if not self._closed:
            if self.stream is not None:
                self.stream.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        prog="payload_extract",
        description="extract zip/bin/url payload.bin",
    )

    parser.add_argument(
        "-t",
        "--type",
        choices=["zip", "bin", "url"],
        default="bin",
        dest="type",
        help="type of input",
    )
    parser.add_argument(
        "-T",
        "--thread",
        type=int,
        default=os.cpu_count() or 2,
        metavar="thread",
        dest="workers",
        help="workers",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        metavar="input",
        dest="input",
        help="input file path",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--outdir",
        type=str,
        metavar="outdir",
        default="out",
        dest="out",
        help="output directory",
    )
    # parser.add_argument(
    #    "-v", "--verbose", default=False, action=argparse._StoreTrueAction
    # )
    parser.add_argument(
        "-X",
        "--extract-partitions",
        type=str,
        help="extract partitions, split with ','",
        metavar="boot,system,vendor...",
        dest="extract_partitions",
        default=None,
    )

    args = parser.parse_args()

    print("Extracting payload ...")
    now = time.time()

    match args.type:
        case "zip":
            with open(args.input, "rb") as f:
                with zipfile.ZipFile(f, "r") as zip:
                    for file in zip.filelist:
                        if file.filename.endswith("payload.bin"):
                            with zip.open(file, "r") as zf:
                                extract_partitions_from_payload(
                                    zf,
                                    (
                                        args.extract_partitions.split(",")
                                        if args.extract_partitions
                                        else []
                                    ),
                                    args.out,
                                    args.workers,
                                )
        case "bin":
            with open(args.input, "rb") as f:
                extract_partitions_from_payload(
                    f,
                    (
                        args.extract_partitions.split(",")
                        if args.extract_partitions
                        else []
                    ),
                    args.out,
                    args.workers,
                )
        case "url":
            with UrlFileReader(args.input) as r:
                with zipfile.ZipFile(r, "r") as zip:
                    for file in zip.filelist:
                        if file.filename.endswith("payload.bin"):
                            with zip.open(file, "r") as zf:
                                extract_partitions_from_payload(
                                    zf,
                                    (
                                        args.extract_partitions.split(",")
                                        if args.extract_partitions
                                        else []
                                    ),
                                    args.out,
                                    args.workers,
                                )
        case _:
            raise Exception("type not support")
    tooks = time.time() - now

    print("Done! tooks: %.2f" % tooks)
