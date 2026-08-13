"""Behavioural tests for the UX / UI-PERF source detectors.

Every detector is tested in *both* directions: it must fire on a violating
fixture and stay silent on a compliant one. A detector that only ever fires is
noise, and a detector that never fires is theatre; the audit that produced
this suite found examples of the latter shipped as passing checks.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _util import REPO_ROOT  # noqa: F401  (ensures scripts/ is importable)

from vibecodekit_mql5.lint import lint_file

CLEAN_PANEL = '''#include <Trade\\Trade.mqh>
int OnInit(){ EventSetTimer(250); return INIT_SUCCEEDED; }
void OnDeinit(const int r){ EventKillTimer(); ObjectsDeleteAll(0,"VCKP_"); }
void OnTick(){ g_dirty = true; }
void OnTimer(){ if(g_dirty) RenderPanel(); }
void RenderPanel(){ ObjectSetString(0,"VCKP_row",OBJPROP_TEXT,g_snapshot.text); ChartRedraw(); }
'''


def codes_for(source: str) -> set[str]:
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "Panel.mq5"
        path.write_text(source, encoding="utf-8")
        return {f.code for f in lint_file(path)}


class TestUxDetectors(unittest.TestCase):
    def test_ux04_fires_without_cleanup(self) -> None:
        src = 'void OnTick(){ ObjectCreate(0,"x",OBJ_LABEL,0,0,0); }\nvoid OnDeinit(const int r){}\n'
        self.assertIn("UX-04", codes_for(src))

    def test_ux05_fires_on_blocking_call_in_ontick(self) -> None:
        src = 'void OnTick(){ Alert("hi"); }\n'
        self.assertIn("UX-05", codes_for(src))

    def test_ui_perf02_fires_when_renderer_trades(self) -> None:
        src = 'void RenderPanel(){ trade.Buy(0.1); }\n'
        self.assertIn("UI-PERF-02", codes_for(src))

    def test_ui_perf01_fires_on_unthrottled_panel_work_in_ontick(self) -> None:
        src = 'void OnTick(){ RenderPanel(); }\nvoid RenderPanel(){ }\n'
        self.assertIn("UI-PERF-01", codes_for(src))

    def test_ui_perf01_silent_when_dirty_guarded(self) -> None:
        src = 'void OnTick(){ if(g_dirty) RenderPanel(); }\nvoid RenderPanel(){ }\n'
        self.assertNotIn("UI-PERF-01", codes_for(src))

    def test_ui_perf03_fires_on_timer_leak(self) -> None:
        src = 'int OnInit(){ EventSetTimer(1); return 0; }\nvoid OnDeinit(const int r){ }\n'
        self.assertIn("UI-PERF-03", codes_for(src))

    def test_ui_perf03_silent_when_timer_released(self) -> None:
        src = 'int OnInit(){ EventSetTimer(1); return 0; }\nvoid OnDeinit(const int r){ EventKillTimer(); }\n'
        self.assertNotIn("UI-PERF-03", codes_for(src))

    def test_ui_perf04_fires_on_unbacked_perf_claim(self) -> None:
        src = 'void RenderPanel(){ /* render time: 400 us worst case */ }\n'
        self.assertIn("UI-PERF-04", codes_for(src))

    def test_ux09_requires_real_panel_context(self) -> None:
        helper = 'bool CloseAllAsync(){ return true; }\n'
        panel = (
            'void OnChartEvent(const int id,const long &l,const double &d,const string &s){'
            'if(s=="close_all") CloseAllAsync();}\n'
        )
        self.assertNotIn("UX-09", codes_for(helper))
        self.assertIn("UX-09", codes_for(panel))

    def test_compliant_panel_has_no_ux_errors(self) -> None:
        """The reference panel the kit itself scaffolds must lint clean of
        ERROR-severity UX findings, or the kit contradicts its own guidance."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Panel.mq5"
            path.write_text(CLEAN_PANEL, encoding="utf-8")
            errors = [f for f in lint_file(path)
                      if f.severity == "ERROR" and f.code.startswith(("UX-", "UI-PERF"))]
        self.assertEqual(errors, [], f"scaffolded panel trips its own rules: {errors}")


class TestLintExitContract(unittest.TestCase):
    def test_lint_cli_exits_nonzero_on_error(self) -> None:
        """CI gates on this exit code; it must never silently become 0."""
        from vibecodekit_mql5 import lint

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "Bad.mq5"
            path.write_text('void OnTick(){ Alert("x"); }\n', encoding="utf-8")
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                rc = lint.main([str(path)])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
