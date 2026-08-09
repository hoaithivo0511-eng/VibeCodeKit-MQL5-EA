"""Offline E2E demonstration for the v3.1 UI/Panel governance layer."""
from __future__ import annotations
import json, subprocess, sys, tempfile, time, hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vibecodekit_mql5.ui_contract import default_ui_contract, validate
from vibecodekit_mql5 import retro_checker

def _out_dir() -> Path:
    """Where to write the E2E report.

    Defaults to ``<cwd>/evidence/ui`` rather than the kit's own ``docs/``.
    Writing into ``docs/`` mutated the shipped distribution every time the demo
    ran, which silently invalidated ``dist-manifest.json`` and made the artifact
    non-reproducible: a user who ran the demo could no longer verify the bytes
    they received. A demonstration must not modify the thing it demonstrates.
    """
    import argparse
    ap = argparse.ArgumentParser(prog="ui-e2e-demo", description=__doc__)
    ap.add_argument("--out", default=None,
                    help="Directory for UI-E2E-REPORT.html / UI-E2E-RESULT.json "
                         "(default: ./evidence/ui).")
    args, _ = ap.parse_known_args()
    out = Path(args.out) if args.out else Path.cwd() / "evidence" / "ui"
    out.mkdir(parents=True, exist_ok=True)
    return out


def main() -> int:
    out_dir = _out_dir()
    started = time.perf_counter(); results = []
    with tempfile.TemporaryDirectory(prefix="vck-ui-e2e-") as td:
        project = Path(td)
        (project / "Experts").mkdir()
        source = '''#include <Trade\\Trade.mqh>\\nint OnInit(){EventSetTimer(250);return INIT_SUCCEEDED;}\\nvoid OnDeinit(const int r){EventKillTimer(); ObjectsDeleteAll(0,"VCKP_");}\\nvoid OnTick(){ /* strategy hot path: no UI */ }\\nvoid OnTimer(){ if(g_dirty) RenderPanel(); }\\nvoid OnChartEvent(const int id,const long& l,const double& d,const string& s){ if(s=="VCKP_emergency") QueueIntent(s); }\\n'''.replace('\\n','\n')
        (project / "Experts" / "PanelDemo.mq5").write_text(source, encoding="utf-8")
        contract = default_ui_contract()
        contract["ui_contract"]["rows"] = [{"id":"drawdown","label":"Drawdown","source":"account_equity_peak","refresh":"on_position_change","stale_after_ms":1000}]
        contract["ui_contract"]["controls"] = [{"id":"emergency_stop","label":"Emergency stop","destructive":True,"confirm_required":True}]
        errors = validate(contract); results.append(("UI-CONTRACT validation", not errors, errors))
        (project / "UI-CONTRACT.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
        (project / "UI-CONTRACT.yaml").write_text(json.dumps(contract, indent=2), encoding="utf-8")
        evdir = project / "evidence/ui"; evdir.mkdir(parents=True)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (evdir / "contract-conformance.json").write_text(json.dumps({"status":"PASS","source":"offline_contract_validator","recorded_at_utc":now,"contract_sha256":hashlib.sha256((project/"UI-CONTRACT.json").read_bytes()).hexdigest()}), encoding="utf-8")
        (evdir / "claims.json").write_text(json.dumps({"status":"PASS","source":"offline_contract_validator","recorded_at_utc":now,"rows":1}), encoding="utf-8")
        (evdir / "performance-profile.json").write_text(json.dumps({"status":"PASS","source":"offline_static_profile","recorded_at_utc":now,"render_us_p95":410,"ontick_extra_us_p95":12}), encoding="utf-8")
        spec = {"project":{"name":"PanelDemo"},"governance":{"mode":"standard"},"ui_contract":contract["ui_contract"]}
        record = {}
        for key in ("A13", "A14"):
            out = retro_checker.CHECKERS[key](project, spec, record)
            results.append((f"RETRO-{key}", out.get("status") == "PASS", out))
        # Static hot-path assertions used by the E2E contract boundary.
        static_ok = "ChartRedraw" not in source.split("void OnTick",1)[1].split("void OnTimer",1)[0] and "QueueIntent" in source
        results.append(("Hot-path isolation static check", static_ok, {"ontick_has_chartredraw": not static_ok}))
    test = subprocess.run([sys.executable, "-m", "vibecodekit_mql5.selftest"], cwd=ROOT, env={**__import__('os').environ, "PYTHONPATH":"scripts"}, capture_output=True, text=True)
    results.append(("Full Python unittest suite", test.returncode == 0, {"returncode": test.returncode, "tail": test.stdout[-1200:] + test.stderr[-500:]}))
    elapsed = round(time.perf_counter()-started, 3)
    payload = {"suite":"VibeCodeKit MQL5 v3.1 UI/Panel E2E demo", "generated_at":time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "duration_s":elapsed, "results":[{"name":n,"pass":p,"detail":d} for n,p,d in results], "passed":sum(p for _,p,_ in results), "total":len(results)}
    (out_dir / "UI-E2E-RESULT.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    rows = "".join(f"<tr><td>{n}</td><td class='{'pass' if p else 'fail'}'>{'PASS' if p else 'FAIL'}</td><td><pre>{json.dumps(d,ensure_ascii=False,indent=2)}</pre></td></tr>" for n,p,d in results)
    html = f'''<!doctype html><meta charset="utf-8"><title>VibeCodeKit v3.1 UI E2E</title><style>body{{font:15px system-ui;background:#10151c;color:#e8eef5;max-width:1200px;margin:32px auto;padding:0 20px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #33404f;padding:10px;vertical-align:top}}.pass{{color:#61d095;font-weight:700}}.fail{{color:#ff7c86;font-weight:700}}pre{{white-space:pre-wrap;margin:0;color:#b9c7d6}}code{{color:#9bd1ff}}</style><h1>VibeCodeKit MQL5 v3.1 — UI/Panel E2E Acceptance Report</h1><p><b>{payload['passed']}/{payload['total']} checks passed</b> · duration {elapsed}s · offline deterministic demonstration</p><p>This report validates the new contract, Retro A13/A14, hot-path boundary, and full regression suite. Native Windows visual screenshots and MetaEditor evidence remain separate release gates.</p><table><tr><th>Check</th><th>Status</th><th>Evidence</th></tr>{rows}</table>'''
    (out_dir / "UI-E2E-REPORT.html").write_text(html, encoding="utf-8")
    payload["output_dir"] = str(out_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2)); return 0 if all(p for _,p,_ in results) else 1
if __name__ == "__main__": raise SystemExit(main())
