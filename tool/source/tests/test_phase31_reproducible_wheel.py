import base64
import csv
import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from vibecodekit_mql5.wheel_repro import (
    WHEEL_EPOCH,
    WheelIntegrityError,
    normalize_wheel,
    verify_wheel,
)


def _hash(payload: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
    return "sha256=" + digest.decode("ascii")


def _write_fixture_wheel(path: Path, timestamp: tuple[int, int, int, int, int, int]):
    files = {
        "demo/__init__.py": b'VERSION = "1"\n',
        "demo-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        "demo-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: py3-none-any\n",
    }
    record_name = "demo-1.0.dist-info/RECORD"
    rows = [[name, _hash(payload), str(len(payload))] for name, payload in files.items()]
    rows.append([record_name, "", ""])
    stream = io.StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    files[record_name] = stream.getvalue().encode("utf-8")
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in reversed(tuple(files.items())):
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)


def test_wheel_normalization_is_byte_reproducible(tmp_path: Path):
    first_source = tmp_path / "first-source.whl"
    second_source = tmp_path / "second-source.whl"
    first = tmp_path / "first.whl"
    second = tmp_path / "second.whl"
    _write_fixture_wheel(first_source, (2025, 1, 2, 3, 4, 6))
    _write_fixture_wheel(second_source, (2026, 7, 8, 9, 10, 12))

    normalize_wheel(first_source, first)
    normalize_wheel(second_source, second)

    assert first.read_bytes() == second.read_bytes()
    verify_wheel(first)
    with zipfile.ZipFile(first) as archive:
        assert {info.date_time for info in archive.infolist()} == {WHEEL_EPOCH}


@pytest.mark.parametrize("member", ("../escape.py", "/absolute.py"))
def test_wheel_normalization_rejects_unsafe_paths(tmp_path: Path, member: str):
    source = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(member, b"bad")
    with pytest.raises(WheelIntegrityError, match="unsafe wheel path"):
        normalize_wheel(source, tmp_path / "out.whl")
