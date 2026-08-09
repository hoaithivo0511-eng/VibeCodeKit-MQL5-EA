"""Static, conservative UX and panel-performance lint detectors."""
from __future__ import annotations
import re
from .lint import Finding, _line_col

_FUNC = re.compile(r"\b(OnTick|OnTimer|OnDeinit|OnChartEvent)\s*\([^)]*\)\s*\{(?P<body>.*?)\n?\}", re.S)

def _bodies(src: str):
    return [(m.group(1), m.group("body"), m.start("body")) for m in _FUNC.finditer(src)]

def detect_ux04(path, raw, src):
    if not re.search(r"\bObjectCreate\s*\(", src): return []
    deinit = " ".join(body for name, body, _ in _bodies(src) if name == "OnDeinit")
    has_prefix = bool(re.search(r"(?:prefix|VCKP_|PanelPrefix|UI_PREFIX)", src))
    cleanup = bool(re.search(r"\b(?:ObjectsDeleteAll|ObjectDelete)\s*\(", deinit))
    if has_prefix and cleanup: return []
    m = re.search(r"\bObjectCreate\s*\(", src); line,col=_line_col(src,m.start())
    return [Finding(path,line,col,"ERROR","UX-04","Panel objects need a stable prefix and deterministic OnDeinit cleanup")]

def detect_ux05(path, raw, src):
    out=[]
    blocked=re.compile(r"\b(?:Alert|MessageBox|Sleep|WebRequest|FileOpen|ChartRedraw|iCustom|iMA|iRSI|iATR)\s*\(")
    for name,body,start in _bodies(src):
        if name not in {"OnTick","OnChartEvent"}: continue
        for m in blocked.finditer(body):
            line,col=_line_col(src,start+m.start())
            out.append(Finding(path,line,col,"ERROR","UX-05",f"{m.group(0).split('(')[0]} in {name} may block the EA event queue"))
    return out

def detect_ux06(path, raw, src):
    if not re.search(r"\bObjectCreate\s*\(",src): return []
    if re.search(r"(?:CORNER_|anchor|dpi|CHART_WIDTH_IN_PIXELS|CHART_HEIGHT_IN_PIXELS|OBJPROP_CORNER)",src,re.I): return []
    m=re.search(r"\bObjectCreate\s*\(",src); line,col=_line_col(src,m.start())
    return [Finding(path,line,col,"WARN","UX-06","Panel layout lacks an explicit anchor/resize/DPI strategy")]

def detect_ux07(path, raw, src):
    if not re.search(r"\bObjectSetInteger\s*\([^;]*(?:OBJPROP_COLOR|OBJPROP_TEXT_COLOR)",src): return []
    if re.search(r"OBJPROP_BGCOLOR|OBJPROP_BACK|OBJ_RECTANGLE_LABEL|panel_bg",src,re.I): return []
    m=re.search(r"OBJPROP_COLOR",src); line,col=_line_col(src,m.start())
    return [Finding(path,line,col,"WARN","UX-07","Panel text color has no owned contrast surface")]

def detect_ux08(path, raw, src):
    if "ChartRedraw" not in src: return []
    if re.search(r"dirty|redraw.*(?:timer|interval|elapsed)|last_redraw",src,re.I): return []
    m=re.search(r"ChartRedraw",src); line,col=_line_col(src,m.start())
    return [Finding(path,line,col,"WARN","UX-08","ChartRedraw is not visibly guarded by dirty state and cadence")]

def detect_ux09(path, raw, src):
    if not re.search(r"(?:close.?all|emergency|disable.?strategy|modify.?order|destructive)",src,re.I): return []
    if re.search(r"(?:confirm|nonce|armed|two.?step|risk.?guard)",src,re.I): return []
    m=re.search(r"(?:close.?all|emergency|disable.?strategy|modify.?order|destructive)",src,re.I); line,col=_line_col(src,m.start())
    return [Finding(path,line,col,"ERROR","UX-09","Destructive panel action lacks confirmation/risk gate")]

def detect_ux10(path, raw, src):
    # Inspect each actual double-quoted literal independently.  The previous
    # regex could start at one literal and run across single-quoted MQL5
    # delimiters until a later literal, falsely treating identifiers such as
    # INVALID_HANDLE as user-facing panel text.
    for m in re.finditer(r'"(?:\\.|[^"\\\n])*"', raw):
        literal = m.group(0)
        if not re.search(r"(?:error|failed|invalid)", literal, re.I):
            continue
        if re.search(r"retry|check|enable|disable|contact|reduce|increase|reconnect", literal, re.I):
            continue
        line,col=_line_col(raw,m.start())
        return [Finding(path,line,col,"WARN","UX-10","Panel error text lacks an actionable remediation")]
    return []

def detect_ux11(path, raw, src):
    m=re.search(r'[\U0001F300-\U0001FAFF]|[╔╗╚╝═║]',raw)
    if not m: return []
    line,col=_line_col(raw,m.start()); return [Finding(path,line,col,"WARN","UX-11","Decorative glyph/emoji in panel label can reduce terminal portability")]

def detect_ux12(path, raw, src):
    # Eight-digit hex values are also used as uint/ulong masks and split-ID
    # sentinels. Treat them as colors only in an actual color/UI context.
    m=re.search(r"\bARGB\s*\([^)]*\)|(?:color|OBJPROP_(?:COLOR|BGCOLOR|BORDER_COLOR))[^;\n]{0,120}0x[0-9A-Fa-f]{8}",src,re.I)
    if not m or re.search(r"ui_token|panel_(?:bg|text|status)|VCK_COLOR",src,re.I): return []
    line,col=_line_col(src,m.start()); return [Finding(path,line,col,"WARN","UX-12","Raw ARGB color is not visibly bound to a UI token")]

def detect_ui_perf02(path, raw, src):
    for m in re.finditer(r"\b(?:RenderPanel|Render|DrawPanel)\s*\([^)]*\)\s*\{(?P<body>.*?)\n?\}",src,re.S):
        bad=re.search(r"\b(?:OrderSend|Buy|Sell|PositionClose|WebRequest|FileOpen|iCustom|iMA|iRSI|iATR|PositionsTotal|AccountInfoDouble)\s*\(",m.group("body"))
        if bad:
            line,col=_line_col(src,m.start("body")+bad.start()); return [Finding(path,line,col,"ERROR","UI-PERF-02","Renderer calls execution/network/heavy data API instead of consuming a snapshot")]
    return []

def detect_ui_perf01(path, raw, src):
    """UI-PERF-01 -- panel work in OnTick must be budget-bounded.

    R2 argued this rule could not be enforced from source regex. That is true
    for the *numeric* budget (which needs a real profile), but the structural
    precondition is checkable: if OnTick performs panel work at all, there must
    be visible evidence of a cadence or budget guard. An unthrottled render
    call inside the tick handler is a defect regardless of measured latency.
    """
    panel_call = re.compile(r"\b(?:RenderPanel|DrawPanel|UpdatePanel|ObjectSetString|ObjectSetInteger|ObjectCreate)\s*\(")
    for name, body, start in _bodies(src):
        if name != "OnTick":
            continue
        m = panel_call.search(body)
        if not m:
            continue
        guarded = re.search(r"dirty|budget|throttle|last_(?:render|update|redraw)|GetTickCount|elapsed|max_render", body, re.I)
        if guarded:
            continue
        line, col = _line_col(src, start + m.start())
        return [Finding(path, line, col, "WARN", "UI-PERF-01",
                        "Panel work in OnTick has no visible cadence or budget guard")]
    return []

def detect_ui_perf03(path, raw, src):
    """UI-PERF-03 -- every acquired panel resource must be released on deinit.

    Checks resource *pairing*, which is orthogonal to UX-04's object-prefix
    rule: timers, canvases and indicator handles each need their own teardown.
    A panel that leaks an EventSetTimer or a CCanvas across reinitialisation
    degrades the terminal even though its chart objects are cleaned up.
    """
    deinit = " ".join(body for name, body, _ in _bodies(src) if name == "OnDeinit")
    pairs = (
        (r"\bEventSetTimer\s*\(", r"\bEventKillTimer\s*\(", "EventSetTimer without EventKillTimer"),
        (r"\bCCanvas\b|\bCreateBitmapLabel\s*\(", r"\b(?:Destroy|Delete)\s*\(", "canvas created without Destroy"),
        (r"\biCustom\s*\(", r"\bIndicatorRelease\s*\(", "indicator handle without IndicatorRelease"),
    )
    for acquire, release, message in pairs:
        m = re.search(acquire, src)
        if not m:
            continue
        release_scope = src if "IndicatorRelease" in message else deinit
        if re.search(release, release_scope):
            continue
        line, col = _line_col(src, m.start())
        return [Finding(path, line, col, "WARN", "UI-PERF-03",
                        f"Panel resource lifecycle incomplete: {message}")]
    return []

def detect_ui_perf04(path, raw, src):
    """UI-PERF-04 -- a performance claim in source must not be self-asserted.

    Catches the exact anti-pattern this kit was audited for: a comment or
    string asserting a latency/FPS number with no provenance sidecar. Numbers
    belong in evidence/ui/performance-profile.json, not in a code comment that
    no gate can verify.
    """
    claim = re.search(
        r"(?:[^\n]{0,60})\b(?:\d+\s*(?:us|ms|fps|FPS)|render(?:_| )?(?:time|budget)\s*[:=]\s*\d+)",
        raw)
    if not claim:
        return []
    context = claim.group(0)
    if not re.search(r"//|/\*|\"", context):
        return []
    if re.search(r"performance-profile|evidence/ui|measured_by|provenance", raw, re.I):
        return []
    line, col = _line_col(raw, claim.start())
    return [Finding(path, line, col, "WARN", "UI-PERF-04",
                    "Performance claim has no evidence/ui/performance-profile.json provenance sidecar")]

BEST_UI_DETECTORS = [("UX-04",detect_ux04),("UX-05",detect_ux05),("UX-06",detect_ux06),("UX-07",detect_ux07),("UX-08",detect_ux08),("UX-09",detect_ux09),("UX-10",detect_ux10),("UX-11",detect_ux11),("UX-12",detect_ux12),("UI-PERF-01",detect_ui_perf01),("UI-PERF-02",detect_ui_perf02),("UI-PERF-03",detect_ui_perf03),("UI-PERF-04",detect_ui_perf04)]
