from __future__ import annotations

import sys
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
AVBTOOL_DIR = ROOT_DIR / "platform_external_avb-master"
AVBTOOL_PATH = AVBTOOL_DIR / "avbtool.py"
AVB_FOOTER_MAGIC = b"AVBf"


class AvbFooterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvbHashtreeProfile:
    partition_size: int
    partition_name: str
    algorithm: str
    hash_algorithm: str
    salt: str
    fec_num_roots: int
    data_block_size: int
    flags: int
    rollback_index: int
    rollback_index_location: int
    vbmeta_flags: int
    properties: tuple[tuple[str, str], ...]


def _load_avbtool() -> Any:
    avbtool_dir = str(AVBTOOL_DIR)
    if avbtool_dir not in sys.path:
        sys.path.insert(0, avbtool_dir)
    import avbtool

    return avbtool


def has_avb_footer(path: str | Path) -> bool:
    image = Path(path)
    if not image.is_file() or image.stat().st_size < 64:
        return False
    with image.open("rb") as handle:
        handle.seek(-64, 2)
        return handle.read(4) == AVB_FOOTER_MAGIC


def read_avb_hashtree_profile(path: str | Path) -> AvbHashtreeProfile | None:
    image_path = Path(path)
    if not image_path.is_file():
        raise AvbFooterError(f"Missing AVB source image: {image_path}")
    if not has_avb_footer(image_path):
        return None
    avbtool = _load_avbtool()
    image = avbtool.ImageHandler(str(image_path), read_only=True)
    try:
        footer, header, descriptors, _image_size = avbtool.Avb()._parse_image(image)
    finally:
        image._image.close()
    if footer is None or header is None:
        raise AvbFooterError(f"Cannot parse AVB footer: {image_path}")
    algorithms = {
        value.algorithm_type: name for name, value in avbtool.ALGORITHMS.items()
    }
    algorithm = algorithms.get(header.algorithm_type)
    if algorithm is None:
        raise AvbFooterError(
            f"Unsupported AVB algorithm type {header.algorithm_type}: {image_path}"
        )
    hashtrees = [
        descriptor
        for descriptor in descriptors
        if isinstance(descriptor, avbtool.AvbHashtreeDescriptor)
    ]
    if len(hashtrees) != 1:
        raise AvbFooterError(
            f"Expected one AVB hashtree descriptor in {image_path}, got {len(hashtrees)}"
        )
    descriptor = hashtrees[0]
    properties = tuple(
        (item.key, item.value.decode("utf-8"))
        for item in descriptors
        if isinstance(item, avbtool.AvbPropertyDescriptor)
    )
    return AvbHashtreeProfile(
        partition_size=image_path.stat().st_size,
        partition_name=descriptor.partition_name,
        algorithm=algorithm,
        hash_algorithm=descriptor.hash_algorithm,
        salt=descriptor.salt.hex(),
        fec_num_roots=descriptor.fec_num_roots,
        data_block_size=descriptor.data_block_size,
        flags=descriptor.flags,
        rollback_index=header.rollback_index,
        rollback_index_location=header.rollback_index_location,
        vbmeta_flags=header.flags,
        properties=properties,
    )


def _round_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def minimum_partition_size(
    image_size: int,
    profile: AvbHashtreeProfile,
    *,
    fec_num_roots: int | None = None,
) -> int:
    avbtool = _load_avbtool()
    digest_size = len(
        avbtool.create_avb_hashtree_hasher(profile.hash_algorithm, b"").digest()
    )
    digest_padding = avbtool.round_to_pow2(digest_size) - digest_size
    block_size = profile.data_block_size
    aligned_image_size = _round_up(image_size, block_size)

    effective_fec_num_roots = (
        (profile.fec_num_roots if shutil.which("fec") else 0)
        if fec_num_roots is None
        else fec_num_roots
    )

    def fits(partition_size: int) -> bool:
        _offsets, tree_size = avbtool.calc_hash_level_offsets(
            partition_size,
            block_size,
            digest_size + digest_padding,
        )
        fec_size = (
            avbtool.calc_fec_data_size(partition_size, effective_fec_num_roots)
            if effective_fec_num_roots
            else 0
        )
        maximum_image_size = (
            partition_size
            - tree_size
            - fec_size
            - avbtool.Avb.MAX_VBMETA_SIZE
            - avbtool.Avb.MAX_FOOTER_SIZE
        )
        return aligned_image_size <= maximum_image_size

    low = _round_up(max(profile.partition_size, aligned_image_size), block_size)
    high = low
    while not fits(high):
        high = _round_up(high * 2, block_size)
    while low < high:
        middle = _round_up((low + high) // 2, block_size)
        if middle >= high:
            break
        if fits(middle):
            high = middle
        else:
            low = middle + block_size
    return high


def restore_avb_footer(
    output_img: str | Path,
    source_img: str | Path,
) -> dict[str, Any]:
    output = Path(output_img)
    source = Path(source_img)
    profile = read_avb_hashtree_profile(source)
    if profile is None:
        return {"mode": "no-source-footer"}
    if not output.is_file() or output.stat().st_size <= 0:
        raise AvbFooterError(f"Missing repacked image: {output}")
    fec_available = shutil.which("fec") is not None
    if profile.fec_num_roots and not fec_available:
        raise AvbFooterError(
            f"{source.name}: source AVB footer uses FEC but the fec binary is unavailable; "
            "cannot safely repack this modified partition"
        )
    effective_fec_num_roots = profile.fec_num_roots if fec_available else 0
    partition_size = minimum_partition_size(
        output.stat().st_size,
        profile,
        fec_num_roots=effective_fec_num_roots,
    )
    avbtool = _load_avbtool()
    do_not_use_ab = bool(
        profile.flags & avbtool.AvbHashtreeDescriptor.FLAGS_DO_NOT_USE_AB
    )
    check_at_most_once = bool(
        profile.flags & avbtool.AvbHashtreeDescriptor.FLAGS_CHECK_AT_MOST_ONCE
    )
    known_flags = (
        avbtool.AvbHashtreeDescriptor.FLAGS_DO_NOT_USE_AB
        | avbtool.AvbHashtreeDescriptor.FLAGS_CHECK_AT_MOST_ONCE
    )
    if profile.flags & ~known_flags:
        raise AvbFooterError(
            f"{source.name}: unsupported AVB hashtree flags: {profile.flags}"
        )
    command = [
        sys.executable,
        str(AVBTOOL_PATH),
        "add_hashtree_footer",
        "--image",
        str(output),
        "--partition_size",
        str(partition_size),
        "--partition_name",
        profile.partition_name,
        "--hash_algorithm",
        profile.hash_algorithm,
        "--salt",
        profile.salt,
        "--algorithm",
        "NONE",
        "--rollback_index",
        str(profile.rollback_index),
        "--rollback_index_location",
        str(profile.rollback_index_location),
        "--flags",
        str(profile.vbmeta_flags),
    ]
    if effective_fec_num_roots:
        command.extend(["--fec_num_roots", str(effective_fec_num_roots)])
    else:
        command.append("--do_not_generate_fec")
    if do_not_use_ab:
        command.append("--do_not_use_ab")
    if check_at_most_once:
        command.append("--check_at_most_once")
    for key, value in profile.properties:
        command.extend(["--prop", f"{key}:{value}"])
    import subprocess

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise AvbFooterError(
            f"{source.name}: cannot restore AVB footer: {details or 'avbtool failed'}"
        )
    if output.stat().st_size != partition_size or not has_avb_footer(output):
        raise AvbFooterError(f"{source.name}: restored AVB footer validation failed")
    rebuilt = read_avb_hashtree_profile(output)
    if rebuilt is None:
        raise AvbFooterError(f"{source.name}: restored AVB footer is missing")
    for field in ("partition_name", "hash_algorithm", "salt"):
        if getattr(rebuilt, field) != getattr(profile, field):
            raise AvbFooterError(f"{source.name}: restored AVB field changed: {field}")
    if rebuilt.fec_num_roots != effective_fec_num_roots:
        raise AvbFooterError(f"{source.name}: restored AVB field changed: fec_num_roots")
    return {
        "mode": "restored",
        "partitionSize": partition_size,
        "partitionName": profile.partition_name,
        "resized": partition_size != profile.partition_size,
        "sourceAlgorithm": profile.algorithm,
        "signatureReplaced": profile.algorithm != "NONE",
        "fecDropped": profile.fec_num_roots != effective_fec_num_roots,
    }
