"""Deterministic wheel normalization and RECORD verification."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

WHEEL_EPOCH = (1980, 1, 1, 0, 0, 0)


class WheelIntegrityError(ValueError):
    """Raised when a wheel cannot be normalized or verified safely."""


def _member_payloads(path: Path) -> dict[str, tuple[zipfile.ZipInfo, bytes]]:
    payloads: dict[str, tuple[zipfile.ZipInfo, bytes]] = {}
    with zipfile.ZipFile(path) as archive:
        bad_crc = archive.testzip()
        if bad_crc:
            raise WheelIntegrityError(f"wheel CRC failure: {bad_crc}")
        for info in archive.infolist():
            name = info.filename
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise WheelIntegrityError(f"unsafe wheel path: {name}")
            if name in payloads:
                raise WheelIntegrityError(f"duplicate wheel member: {name}")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise WheelIntegrityError(f"wheel symlink forbidden: {name}")
            payloads[name] = (info, archive.read(name))
    return payloads


def _record_hash(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
    return "sha256=" + encoded.decode("ascii")


def verify_wheel(path: Path, *, require_normalized: bool = True) -> None:
    payloads = _member_payloads(Path(path))
    record_names = [name for name in payloads if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise WheelIntegrityError("wheel must contain exactly one dist-info/RECORD")
    if require_normalized:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.date_time != WHEEL_EPOCH:
                    raise WheelIntegrityError(f"non-deterministic timestamp: {info.filename}")

    record_name = record_names[0]
    record_text = payloads[record_name][1].decode("utf-8")
    rows = list(csv.reader(io.StringIO(record_text)))
    records = {row[0]: row for row in rows if len(row) == 3}
    if set(records) != set(payloads):
        raise WheelIntegrityError("wheel RECORD member inventory mismatch")
    for name, (_, payload) in payloads.items():
        row = records[name]
        if name == record_name:
            if row[1] or row[2]:
                raise WheelIntegrityError("wheel RECORD must not hash itself")
            continue
        if row[1] != _record_hash(payload) or row[2] != str(len(payload)):
            raise WheelIntegrityError(f"wheel RECORD hash/size mismatch: {name}")


def normalize_wheel(source: Path, destination: Path) -> None:
    source = Path(source)
    destination = Path(destination)
    payloads = _member_payloads(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="normalized-wheel-", suffix=".whl", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name in sorted(payloads):
                original, payload = payloads[name]
                info = zipfile.ZipInfo(name, WHEEL_EPOCH)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                mode = original.external_attr >> 16
                if not mode:
                    mode = 0o100644
                info.external_attr = mode << 16
                info.flag_bits = original.flag_bits & 0x800
                archive.writestr(info, payload)
        verify_wheel(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "WHEEL_EPOCH",
    "WheelIntegrityError",
    "normalize_wheel",
    "verify_wheel",
]
