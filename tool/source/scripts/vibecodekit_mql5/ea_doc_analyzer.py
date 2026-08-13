"""EA documentation analyzer.

Extracts inputs, includes, event handlers and architecture cues from MQL5 project.
Designed for doc generation; not a compiler.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from .mq5_io import read_mq5_text
from pathlib import Path
from typing import Any
import re


_INCLUDE_DIRECTIVE = re.compile(
    r'^\s*#include\s*[<"]([^>"]+)[>"]', re.MULTILINE
)


@dataclass
class InputParam:
    type: str
    name: str
    default: str
    description: str = ""


def read_mql_files(project: str | Path) -> dict[str, str]:
    root = Path(project)
    out: dict[str, str] = {}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".mq5", ".mqh"}:
            out[p.relative_to(root).as_posix()] = read_mq5_text(p, errors="ignore")
    return out


def _local_include_path(
    root: Path,
    current: Path,
    include: str,
    available: dict[str, Path],
) -> Path | None:
    """Resolve one include to a project-local file, or return ``None``."""
    normalized = include.replace("\\", "/").strip().lstrip("/")
    parts = Path(normalized).parts
    if not normalized or ".." in parts:
        return None
    candidates = (
        current.parent / normalized,
        root / normalized,
        root / "Include" / normalized,
    )
    for candidate in candidates:
        try:
            relative = candidate.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            continue
        exact = available.get(relative)
        if exact is not None:
            return exact
        lowered = relative.casefold()
        for key, path in available.items():
            if key.casefold() == lowered:
                return path
    return None


def read_reachable_mql_files(project: str | Path) -> dict[str, str]:
    """Read every MQL entrypoint and its transitive project-local includes.

    Generated projects intentionally carry optional reusable headers. Those
    headers are inventory, not active code, until an entrypoint includes them.
    Header-only projects fall back to all files so library audits still work.
    """
    root = Path(project)
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".mq5", ".mqh"}
    )
    available = {path.relative_to(root).as_posix(): path for path in paths}
    entrypoints = [path for path in paths if path.suffix.lower() == ".mq5"]
    if not entrypoints:
        entrypoints = paths

    pending = list(entrypoints)
    queued = {path.relative_to(root).as_posix() for path in pending}
    selected: dict[str, str] = {}
    while pending:
        path = pending.pop(0)
        relative = path.relative_to(root).as_posix()
        text = read_mq5_text(path, errors="ignore")
        selected[relative] = text
        for match in _INCLUDE_DIRECTIVE.finditer(text):
            target = _local_include_path(root, path, match.group(1), available)
            if target is None:
                continue
            target_relative = target.relative_to(root).as_posix()
            if target_relative not in queued:
                queued.add(target_relative)
                pending.append(target)
    return dict(sorted(selected.items()))


def extract_inputs(text: str) -> list[InputParam]:
    params: list[InputParam] = []
    pattern = re.compile(r"^\s*input\s+([A-Za-z_][\w:<>\s\*&]*)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);", re.M)
    for m in pattern.finditer(text):
        params.append(InputParam(type=m.group(1).strip(), name=m.group(2).strip(), default=m.group(3).strip()))
    return params


def infer_input_description(name: str) -> str:
    n = name.lower()
    if "baselot" in n:
        return "Lot khởi điểm cho lệnh đầu tiên hoặc level 0."
    if "lotmultiplier" in n:
        return "Hệ số nhân lot khi tăng level grid/DCA."
    if "gridstep" in n:
        return "Khoảng cách tối thiểu giữa các level grid, tính theo point."
    if "maxlevels" in n:
        return "Số level tối đa cho mỗi phía; giới hạn rủi ro grid."
    if "virtualtp" in n:
        return "Ngưỡng lợi nhuận ảo để đóng basket, tính quy đổi theo tick value."
    if "baskettrail" in n:
        return "Tham số basket trailing; dùng cho logic trailing basket hoặc placeholder mở rộng."
    if "maxdd" in n:
        return "Ngưỡng drawdown cứng; khi đạt ngưỡng sẽ dừng mở exposure mới."
    if "freezedd" in n:
        return "Ngưỡng drawdown để đóng băng/mở chậm grid, giảm tăng exposure."
    if "breakerboost" in n:
        return "Hệ số boost lot khi phát hiện breaker/trend mode."
    if "swinglookback" in n:
        return "Số bar dùng để tìm swing high/low cho SMC breaker detection."
    if "magic" in n:
        return "Magic number gốc để phân biệt lệnh EA."
    if "hedgegrid" in n:
        return "Bật/tắt chế độ hedge grid hai chiều."
    if "breakeroneway" in n:
        return "Bật/tắt chuyển hướng one-way khi có breaker."
    if "seeddivergence" in n:
        return "Bật/tắt phân kỳ tham số theo account seed."
    if "profile" in n:
        return "Tên profile/nhãn cấu hình EA."
    return "Tham số đầu vào của EA; cần xác nhận trong blueprint/spec trước live."



def infer_strategy_profile(all_text: str, ea_name: str = "") -> dict[str, Any]:
    lower = all_text.lower()
    uses_grid = "grid" in lower
    uses_hedge = "hedge" in lower
    if uses_grid and uses_hedge:
        archetype = "grid-hedge"
        method = "Grid hai chiều có hedge; đối chiếu spec/blueprint để xác nhận chi tiết."
    elif uses_grid:
        archetype = "grid"
        method = "Grid trading có giới hạn level và risk guard."
    elif uses_hedge:
        archetype = "hedge"
        method = "Chiến lược có hedge hai chiều; xác nhận chi tiết từ source."
    else:
        archetype = "custom"
        method = "Chiến lược tùy chỉnh được mô tả từ source."
    return {
        "name": ea_name.strip() or "EA",
        "archetype": archetype,
        "method": method,
        "uses_grid": uses_grid,
        "uses_hedge": uses_hedge,
        "uses_smc_breaker": "smcdetector" in lower or "breaker" in lower or "swing_high" in lower,
        "uses_async_close": "asynctradeexecutor" in lower or "closebasketfast" in lower,
        "uses_virtual_tp": "virtualtp" in lower or "virtual_tp" in lower,
        "uses_account_seed": "accountseed" in lower or "account_login" in lower,
    }


def find_input_usage(files: dict[str, str], input_name: str) -> list[dict[str, Any]]:
    usage: list[dict[str, Any]] = []
    for rel, text in files.items():
        for idx, line in enumerate(text.splitlines(), start=1):
            if input_name in line and not line.strip().startswith("input "):
                usage.append({"file": rel, "line": idx, "snippet": line.strip()[:220]})
    return usage[:20]


def infer_input_risk_level(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["lotmultiplier", "maxlevels", "maxdd", "baselot"]):
        return "high"
    if any(k in n for k in ["gridstep", "breakerboost", "freezedd", "virtualtp"]):
        return "medium"
    return "low"


def infer_input_operator_note(name: str) -> str:
    n = name.lower()
    if "lotmultiplier" in n:
        return "Tăng nhỏ cũng làm rủi ro tăng nhanh theo cấp số nhân."
    if "baselot" in n:
        return "Lot đầu càng lớn thì DD và margin dùng càng lớn."
    if "maxlevels" in n:
        return "Giới hạn số level; tăng quá cao có thể làm tail risk lớn."
    if "gridstep" in n:
        return "Step nhỏ vào lệnh dày hơn; step lớn thưa lệnh hơn."
    if "maxdd" in n:
        return "Ngưỡng bảo vệ quan trọng; cần xác nhận trước live."
    if "freezedd" in n:
        return "Giúp EA ngừng tăng exposure khi DD bắt đầu cao."
    if "virtualtp" in n:
        return "TP nhỏ đóng nhanh hơn nhưng lợi nhuận mỗi vòng thấp hơn."
    if "breakerboost" in n:
        return "Boost càng cao càng tăng rủi ro khi breaker sai."
    if "swinglookback" in n:
        return "Lookback lớn làm breaker ít xuất hiện hơn; lookback nhỏ nhạy hơn."
    return "Giữ mặc định nếu chưa hiểu rõ tác động."

def analyze_project(
    project: str | Path,
    ea: str | Path | None = None,
    *,
    files: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(project)
    files = read_mql_files(root) if files is None else files
    if ea:
        ea_path = Path(ea)
        try:
            ea_rel = ea_path.relative_to(root).as_posix()
        except ValueError:
            ea_rel = ea_path.name
    else:
        candidates = [k for k in files if k.startswith("Experts/") and k.endswith(".mq5")]
        ea_rel = candidates[0] if candidates else next((k for k in files if k.endswith(".mq5")), "")

    all_text = "\n".join(files.values())
    ea_text = files.get(ea_rel, "")

    inputs = extract_inputs(all_text)
    input_usage_map: dict[str, list[dict[str, Any]]] = {}
    input_risk_map: dict[str, str] = {}
    input_note_map: dict[str, str] = {}
    for p in inputs:
        p.description = infer_input_description(p.name)
        input_usage_map[p.name] = find_input_usage(files, p.name)
        input_risk_map[p.name] = infer_input_risk_level(p.name)
        input_note_map[p.name] = infer_input_operator_note(p.name)

    includes = re.findall(r"^\s*#include\s+[<\"]([^>\"]+)[>\"]", ea_text, flags=re.M)
    handlers = [h for h in ["OnInit", "OnTick", "OnDeinit", "OnTradeTransaction", "OnTimer"] if re.search(r"\b" + h + r"\s*\(", all_text)]

    features = {
        "async_execution": "CAsyncTradeExecutor" in all_text and "SetAsyncMode(true)" in all_text,
        "basket_close": "CBasketCloseEngine" in all_text or "CloseBasketFast" in all_text,
        "grid_risk_guard": "CGridRiskGuard" in all_text or "GridRiskGuard" in all_text,
        "persistent_state": "CPersistentStateStore" in all_text or "GlobalVariable" in all_text,
        "structured_logging": "CStructuredLogger" in all_text,
        "smc_breaker": "SMCDetector" in all_text or "BUY_BREAKER" in all_text,
        "account_seed_divergence": "AccountSeed" in all_text or "ACCOUNT_LOGIN" in all_text,
        "raw_position_close_loop": bool(re.search(r"for\s*\([^)]*PositionsTotal\s*\([^)]*\)[\s\S]{0,1500}?\.PositionClose\s*\(", all_text, flags=re.I | re.M)),
    }

    return {
        "project": str(root),
        "ea": ea_rel,
        "files_scanned": sorted(files.keys()),
        "inputs": [dict(asdict(p), where_used=input_usage_map.get(p.name, []), risk_level=input_risk_map.get(p.name, "low"), operator_note=input_note_map.get(p.name, "")) for p in inputs],
        "includes": includes,
        "handlers": handlers,
        "strategy_profile": infer_strategy_profile(all_text, ea_name=Path(ea_rel).stem if ea_rel else ""),
        "features": features,
        "line_counts": {k: v.count("\n") + 1 for k, v in files.items()},
    }
