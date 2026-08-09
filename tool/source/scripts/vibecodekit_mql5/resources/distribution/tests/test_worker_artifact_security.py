from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from vibecodekit_mql5 import remote_worker_client as client_mod
from vibecodekit_mql5.remote_worker_client import (
    HttpWorkerTransport,
    MockWorkerTransport,
    RemoteWorkerClient,
)
from vibecodekit_mql5.worker_protocol import (
    ArtifactSecurityError,
    ArtifactVerificationError,
    WorkerArtifact,
    WorkerJobRequest,
    WorkerJobResult,
    read_worker_result,
    validate_artifact_filename,
    verify_artifacts,
    write_worker_result,
)


def _artifact(filename: str, content: bytes, *, required: bool = True) -> WorkerArtifact:
    return WorkerArtifact(
        role="evidence",
        filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        required=required,
    )


def _result(artifacts: list[WorkerArtifact], *, status: str = "passed") -> WorkerJobResult:
    return WorkerJobResult(
        job_id="job-1",
        job_type="compile",
        status=status,
        worker_id="worker-1",
        artifacts=artifacts,
    )


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.bin",
        "/absolute.bin",
        "C:\\escape.bin",
        "\\\\server\\share\\escape.bin",
        "nested//file.bin",
        "nested/./file.bin",
        "nested/../file.bin",
        "report.xml:stream",
    ],
)
def test_worker_artifact_filename_rejects_cross_platform_escapes(filename: str):
    with pytest.raises(ArtifactSecurityError):
        validate_artifact_filename(filename)


def test_client_rejects_traversal_before_transport_or_destination_write(tmp_path: Path):
    class NoCallTransport:
        def post_json(self, path, payload):  # pragma: no cover - protocol stub
            raise AssertionError("unexpected post")

        def get_json(self, path):  # pragma: no cover - protocol stub
            raise AssertionError("unexpected get")

        def download(self, path, dest):
            raise AssertionError("unsafe metadata reached transport")

    outside = tmp_path / "escape.bin"
    result = _result([_artifact("../escape.bin", b"owned")])

    with pytest.raises(ArtifactSecurityError):
        RemoteWorkerClient(NoCallTransport()).download_artifacts(result, tmp_path / "out")

    assert not outside.exists()
    assert not (tmp_path / "out").exists()


def test_successful_download_supports_nested_and_url_encoded_names(tmp_path: Path):
    source = tmp_path / "source"
    (source / "reports").mkdir(parents=True)
    content = b"trusted-report"
    (source / "reports" / "test result.xml").write_bytes(content)
    destination = tmp_path / "out"
    (destination / "reports").mkdir(parents=True)
    (destination / "reports" / "test result.xml").write_bytes(b"old")
    artifact = _artifact("reports/test result.xml", content)

    check = RemoteWorkerClient(MockWorkerTransport(artifact_dir=source)).download_artifacts(
        _result([artifact]), destination
    )

    assert check["ok"] is True
    assert check["checks"][0]["match"] is True
    assert (destination / "reports" / "test result.xml").read_bytes() == content


def test_hash_or_size_failure_leaves_all_destination_files_unchanged(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.bin").write_bytes(b"new-first")
    (source / "second.bin").write_bytes(b"new-second")
    first = _artifact("first.bin", b"new-first")
    second = _artifact("second.bin", b"new-second", required=False)
    second.sha256 = "0" * 64
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "first.bin").write_bytes(b"old-first")

    with pytest.raises(ArtifactVerificationError) as exc_info:
        RemoteWorkerClient(MockWorkerTransport(artifact_dir=source)).download_artifacts(
            _result([first, second]), destination
        )

    assert exc_info.value.report["ok"] is False
    assert (destination / "first.bin").read_bytes() == b"old-first"
    assert not (destination / "second.bin").exists()


def test_symlink_parent_cannot_redirect_committed_artifact(tmp_path: Path):
    source = tmp_path / "source"
    (source / "reports").mkdir(parents=True)
    (source / "reports" / "result.xml").write_bytes(b"report")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "reports").symlink_to(outside, target_is_directory=True)
    artifact = _artifact("reports/result.xml", b"report")

    with pytest.raises(ArtifactSecurityError):
        RemoteWorkerClient(MockWorkerTransport(artifact_dir=source)).download_artifacts(
            _result([artifact]), destination
        )

    assert not (outside / "result.xml").exists()


def test_mock_transport_rejects_source_symlink_escape(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"secret")
    (source / "linked.bin").symlink_to(secret)
    transport = MockWorkerTransport(artifact_dir=source)

    with pytest.raises(ArtifactSecurityError):
        transport.download("/jobs/j/artifacts/linked.bin", tmp_path / "copy.bin")
    with pytest.raises(ArtifactSecurityError):
        transport.download("/jobs/j/not-artifacts/file.bin", tmp_path / "copy.bin")


def test_duplicate_normalized_filenames_are_rejected(tmp_path: Path):
    artifacts = [_artifact("nested/file.bin", b"x"), _artifact("nested\\file.bin", b"x")]
    client = RemoteWorkerClient(MockWorkerTransport(artifact_dir=tmp_path))

    with pytest.raises(ArtifactSecurityError, match="duplicate"):
        client.download_artifacts(_result(artifacts), tmp_path / "out")


def test_commit_failure_rolls_back_every_replaced_file(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    destination = tmp_path / "out"
    source.mkdir()
    destination.mkdir()
    for name in ("a.bin", "b.bin"):
        (source / name).write_bytes(f"new-{name}".encode())
        (destination / name).write_bytes(f"old-{name}".encode())
    artifacts = [
        _artifact(name, f"new-{name}".encode()) for name in ("a.bin", "b.bin")
    ]
    real_replace = client_mod.os.replace
    calls = 0

    def flaky_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("simulated commit fault")
        return real_replace(src, dst)

    monkeypatch.setattr(client_mod.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="simulated commit fault"):
        RemoteWorkerClient(MockWorkerTransport(artifact_dir=source)).download_artifacts(
            _result(artifacts), destination
        )

    assert (destination / "a.bin").read_bytes() == b"old-a.bin"
    assert (destination / "b.bin").read_bytes() == b"old-b.bin"


def test_protocol_round_trip_and_structured_invalid_path_check(tmp_path: Path):
    request = WorkerJobRequest(job_type="compile", payload={"name": "EA"})
    assert request.to_dict()["job_id"] == request.job_id
    artifact = _artifact("result.bin", b"payload")
    result = _result([artifact])
    path = tmp_path / "worker-result.json"
    write_worker_result(path, result)

    loaded = read_worker_result(path)
    assert loaded.to_dict() == result.to_dict()
    invalid = verify_artifacts(tmp_path, [_artifact("../bad.bin", b"bad")])
    assert invalid["ok"] is False
    assert "unsafe segment" in invalid["checks"][0]["error"]


def test_submit_poll_timeout_and_terminal_result(monkeypatch):
    result = _result([])
    transport = MockWorkerTransport(result=result)
    client = RemoteWorkerClient(transport)
    request = WorkerJobRequest(job_type="compile", payload={})
    assert client.submit(request) == result.job_id
    assert client.poll(result.job_id, interval_sec=0).status == "passed"

    monkeypatch.setattr(
        transport,
        "get_json",
        lambda _path: {
            "job_id": "missing",
            "job_type": "compile",
            "status": "queued",
            "worker_id": "mock",
        },
    )
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)
    with pytest.raises(TimeoutError):
        client.poll("missing", timeout_sec=-1, interval_sec=0)


def test_http_transport_json_download_and_overwrite_guard(tmp_path: Path, monkeypatch):
    responses = [io.BytesIO(b'{"job_id":"j"}'), io.BytesIO(b'{"status":"passed"}'), io.BytesIO(b"artifact")]
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return responses.pop(0)

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    transport = HttpWorkerTransport("https://worker.invalid/", token="token", timeout=9)
    assert transport.post_json("/jobs", {"x": 1}) == {"job_id": "j"}
    assert transport.get_json("/jobs/j") == {"status": "passed"}
    destination = tmp_path / "artifact.bin"
    transport.download("/jobs/j/artifacts/a", destination)
    assert destination.read_bytes() == b"artifact"
    assert requests[0][0].get_header("Authorization") == "Bearer token"
    assert requests[0][1] == 9
    with pytest.raises(ArtifactSecurityError):
        transport.download("/jobs/j/artifacts/a", destination)
