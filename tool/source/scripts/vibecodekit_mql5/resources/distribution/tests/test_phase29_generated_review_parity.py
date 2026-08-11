from pathlib import Path

from vibecodekit_mql5 import check_all
from vibecodekit_mql5.advanced_codegen import generate
from vibecodekit_mql5.build_planner import plan
from vibecodekit_mql5.intake import parse_text
from vibecodekit_mql5.mq5_symbols import build_symbol_graph
from vibecodekit_mql5.structure_audit import cyclomatic_complexity

from tests.test_phase16_semantic_isolation import generic_ir

PROMPTS = (
    (
        "EA named TrendMatrix account netting EURUSD H1 trend-following EMA cross "
        "base lot 0.01 max lot 1 max spread 2 max positions 4"
    ),
    (
        "EA named BreakMatrix account netting XAUUSD M15 breakout ATR break "
        "base lot 0.01 max lot 1 max spread 2.5 max positions 4"
    ),
    (
        "EA named MeanMatrix account netting GBPUSD M30 mean-reversion Bollinger "
        "base lot 0.01 max lot 1 max spread 2 max positions 3"
    ),
)


def _matrix_irs():
    items = [parse_text(prompt, strict=True) for prompt in PROMPTS]
    hedge = generic_ir()
    hedge.identity["name"] = "HedgeMatrix"
    items.append(hedge)
    return items


def test_four_generic_archetypes_pass_static_release_review(tmp_path: Path):
    for ir in _matrix_irs():
        build = plan(ir)
        assert build.ok, build.blockers
        project = generate(ir, build, tmp_path / ir.identity["name"])

        lint = check_all._stage_lint(project)
        review = check_all._stage_review(project)

        assert lint.status == "PASS", (ir.identity["name"], lint.detail)
        assert review.status == "PASS", (ir.identity["name"], review.detail)


def test_refactored_runtime_functions_stay_below_complexity_warning(tmp_path: Path):
    ir = _matrix_irs()[-1]
    project = generate(ir, plan(ir), tmp_path / "complexity")
    targets = {
        "CaptureLegacyIdentity",
        "ReconcileSlot",
        "OnTransaction",
        "ValidateOperationalInputs",
    }
    found: dict[str, list[int]] = {name: [] for name in targets}

    for path in project.rglob("*"):
        if path.suffix.lower() not in {".mq5", ".mqh"}:
            continue
        source = path.read_text(encoding="utf-8")
        graph = build_symbol_graph(source, source=path.as_posix())
        for function in graph.functions:
            if function.name in targets:
                found[function.name].append(cyclomatic_complexity(function.body))

    assert all(found.values()), found
    assert all(value < 12 for values in found.values() for value in values), found
