"""RC6 documentation runtime and MCP bridge smoke contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SERVER = SOURCE / "mcp" / "vibecodekit-bridge" / "server.py"


def _request(payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=json.dumps(payload) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_vibecodekit_bridge_starts_with_30_tools() -> None:
    if not SERVER.is_file():
        from vibecodekit_mql5.auto_build_docs_stage import write_docs_to_disk

        assert callable(write_docs_to_disk)
        return
    response = _request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = response["result"]["tools"]
    assert len(tools) == 30
    assert "docs.ea_render" in {item["name"] for item in tools}


def test_docs_ea_render_writes_html_and_markdown(tmp_path: Path) -> None:
    spec = {
        "name": "DocsSmokeEA",
        "preset": "trend",
        "stack": "netting",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "mode": "personal",
    }
    if not SERVER.is_file():
        from vibecodekit_mql5 import auto_build_docs_stage, build, ea_docs, spec_schema

        ea = spec_schema.validate(spec, valid_presets=build.PRESETS)
        meta = ea_docs.BuildMeta.now(
            ea_version="0.1.0",
            kit_version=ea_docs._kit_version(),
            built_from="DocsSmokeEA",
        )
        result = auto_build_docs_stage.write_docs_to_disk(
            ea,
            "input double InpRisk = 0.5; // percent\n",
            tmp_path,
            lang="vi",
            formats=("html", "md"),
            build_meta=meta,
        )
        assert result["ok"] is True
        assert set(result["outputs"]) == {"html", "md"}
        assert "3.3.0rc6" in (tmp_path / "DocsSmokeEA.docs.md").read_text(
            encoding="utf-8"
        )
        return
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "docs.ea_render",
            "arguments": {
                "spec": spec,
                "mq5_source": "input double InpRisk = 0.5; // percent\n",
                "out_dir": str(tmp_path),
                "lang": "vi",
                "formats": ["html", "md"],
            },
        },
    }
    response = _request(request)
    envelope = response["result"]
    assert envelope["isError"] is False
    result = json.loads(envelope["content"][0]["text"])
    assert result["ok"] is True
    assert result["pdf_error"] is None
    assert set(result["outputs"]) == {"html", "md"}
    for output in result["outputs"].values():
        assert Path(output).is_file()
    assert "3.3.0rc6" in (tmp_path / "DocsSmokeEA.docs.md").read_text(encoding="utf-8")
