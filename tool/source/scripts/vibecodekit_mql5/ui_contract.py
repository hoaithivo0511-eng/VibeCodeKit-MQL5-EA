"""UI-CONTRACT validation and bounded performance policy for EA panels."""

from __future__ import annotations
from typing import Any

DEFAULT_PERFORMANCE = {
    "update_policy": "hybrid",
    "timer_ms": 250,
    "max_render_hz": 4,
    "dirty_only": True,
    "chart_redraw_policy": "on_change_only",
    "budgets": {
        "max_render_us_p95": 2000,
        "max_render_us_p99": 5000,
        "max_ontick_extra_us_p95": 100,
        "max_ontick_overhead_pct": 5,
    },
    "limits": {"max_dynamic_objects": 32, "max_rows": 16, "max_canvas_pixels": 500000},
    "tester": {"skip_ui_when_non_visual": True, "visual_mode_required_for_full_panel": True},
}


def default_ui_contract(surface: str = "chart_objects") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "ui_contract": {
            "surface": surface,
            "hero_metric": "current_drawdown_pct",
            "hero_source": "account_equity_peak",
            "hero_refresh": "on_position_change",
            "tokens": {
                "colors": ["panel_bg", "text_primary", "text_muted", "status_ok", "status_warn"],
                "type_roles": ["metric", "label", "status"],
                "spacing_base": 4,
            },
            "layout": {
                "anchor": "CORNER_RIGHT_UPPER",
                "width_mode": "fixed",
                "dpi_strategy": "scale",
                "resize_strategy": "preserve_anchor",
                "survives_chart_theme": ["dark", "light"],
            },
            "performance": DEFAULT_PERFORMANCE.copy(),
            "rows": [],
            "controls": [],
            "forbidden": ["render_from_ontick", "trade_from_renderer", "per_tick_chart_redraw"],
        },
    }


def validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    root = contract.get("ui_contract", contract)
    if root.get("schema_version", contract.get("schema_version")) != 1:
        errors.append("schema_version must be 1")
    if root.get("surface") not in {"chart_objects", "canvas", "inputs_only", "none"}:
        errors.append("surface is invalid")
    if root.get("surface") not in {"none", "inputs_only"} and (
        not root.get("hero_metric") or not root.get("hero_source") or not root.get("hero_refresh")
    ):
        errors.append("hero metric/source/refresh are required for a panel")
    colors = root.get("tokens", {}).get("colors", [])
    if (
        not isinstance(colors, list)
        or not 4 <= len(colors) <= 6
        or not all(isinstance(c, str) and c for c in colors)
    ):
        errors.append("tokens.colors must contain 4-6 named colors")
    roles = root.get("tokens", {}).get("type_roles", [])
    if roles != ["metric", "label", "status"]:
        errors.append("type_roles must be exactly metric/label/status")
    if root.get("tokens", {}).get("spacing_base") != 4:
        errors.append("spacing_base must be 4")
    perf = root.get("performance", {})
    if perf.get("timer_ms", 0) < 100:
        errors.append("timer_ms below safe floor of 100ms")
    if perf.get("dirty_only") is not True:
        errors.append("dirty_only must be true")
    if perf.get("chart_redraw_policy") != "on_change_only":
        errors.append("ChartRedraw must be on_change_only")
    budgets = perf.get("budgets", {})
    if (
        int(budgets.get("max_render_us_p95", 0) or 0) <= 0
        or int(budgets.get("max_ontick_extra_us_p95", 0) or 0) <= 0
    ):
        errors.append("performance budgets must declare positive render and OnTick limits")
    layout = root.get("layout", {})
    for key in ("anchor", "width_mode", "dpi_strategy", "resize_strategy"):
        if not layout.get(key):
            errors.append(f"layout.{key} is required")
    for row in root.get("rows", []):
        if not row.get("id") or not row.get("source") or not row.get("refresh"):
            errors.append("every row needs id, source and refresh")
    for control in root.get("controls", []):
        if control.get("destructive") and not control.get("confirm_required"):
            errors.append(f"destructive control {control.get('id')} needs confirmation")
    return errors
