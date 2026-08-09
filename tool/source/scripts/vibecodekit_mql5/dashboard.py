"""Render and publish the post-build quality-matrix dashboard.

P2.3 in the auto-build roadmap. Previously the 64-cell RRI matrix HTML
written by ``mql5-rri-matrix`` lived only on disk — useful inside a
developer's machine but invisible to anyone reviewing the Devin session
afterwards. This module adds a thin publish hook so the dashboard URL
shows up directly in the ``auto-build-report.json`` (and therefore in
the chat-driven build playbook output).

The hook is intentionally generic: the publish command is whatever the
caller passes in (or whatever ``MQL5_DASHBOARD_PUBLISH_CMD`` is set to).
The hook runs that command with the rendered HTML path as a positional
argv, captures stdout, and treats the last non-empty stdout line as the
public URL. That covers every realistic backend — Devin's own
``upload_attachment``, ``vercel deploy``, ``aws s3 cp ... && printf
https://...``, ``netlify deploy --json | jq -r .deploy_ssl_url``, or a
home-rolled ``scp + nginx`` script. Nothing about this module is
Devin-specific and nothing assumes a network is available.

If no publish command is configured, ``publish`` returns the local file
path with ``public_url=None`` and ``error=None``. That keeps the path
the same in CI and local dev: the report always contains a dashboard
section, just with a ``file://`` URL instead of an ``https://`` one.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from .rri import matrix as matrix_mod


ENV_PUBLISH_CMD: str = "MQL5_DASHBOARD_PUBLISH_CMD"
"""Environment variable read by :func:`publish` when no explicit command is
passed. Set this in a Devin blueprint to make every auto-build session emit
a public URL without code changes.
"""

PUBLISH_TIMEOUT_SECONDS: int = 90
"""Hard cap on the publish subprocess. Anything that legitimately takes
longer than 90s to upload a small HTML file is a configuration error."""


@dataclass
class DashboardLocation:
    """Where the dashboard ended up after :func:`publish` ran.

    * ``local_path`` is always populated — the rendered HTML on disk.
    * ``public_url`` is populated iff a publish command ran AND emitted a
      URL on its last stdout line. When no publish command is configured,
      we fall back to a ``file://`` URL so the field is always usable.
    * ``error`` carries the publish subprocess stderr (truncated) when the
      command exited non-zero or timed out; ``None`` otherwise.
    """

    local_path: str
    public_url: str | None = None
    error: str | None = None
    command: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _publish_via_command(html_path: Path, cmd: str) -> DashboardLocation:
    argv = shlex.split(cmd) + [str(html_path)]
    # Resolve once so every fallback ``file://`` URI below is well-formed
    # regardless of whether the caller passed a relative ``html_path``
    # (PR-14.1 hotfix — ``Path.as_uri()`` raises ``ValueError`` on
    # relative paths, which leaked through the ``mql5-dashboard`` CLI when
    # the publish command was missing / timed out / exited non-zero).
    fallback_uri = html_path.resolve().as_uri()
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=PUBLISH_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        return DashboardLocation(
            local_path=str(html_path),
            public_url=fallback_uri,
            error=f"publish command not found: {exc}",
            command=cmd,
        )
    except subprocess.TimeoutExpired:
        return DashboardLocation(
            local_path=str(html_path),
            public_url=fallback_uri,
            error=f"publish command timed out after {PUBLISH_TIMEOUT_SECONDS}s",
            command=cmd,
        )

    if result.returncode != 0:
        # Capture last 2 KiB of stderr so the report stays compact.
        err_tail = (result.stderr or "")[-2048:]
        return DashboardLocation(
            local_path=str(html_path),
            public_url=fallback_uri,
            error=f"publish command exited {result.returncode}: {err_tail.strip()}",
            command=cmd,
        )

    url = _last_nonblank_line(result.stdout)
    return DashboardLocation(
        local_path=str(html_path),
        public_url=url,
        error=None,
        command=cmd,
    )


def _last_nonblank_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def publish(
    html_path: Path,
    *,
    publish_cmd: str | None = None,
    env: dict[str, str] | None = None,
) -> DashboardLocation:
    """Publish a rendered dashboard and return its location.

    The resolution order for the publish command is:

    1. ``publish_cmd`` argument, if non-empty.
    2. ``env[ENV_PUBLISH_CMD]`` (defaults to ``os.environ``).
    3. None → no publish, local path only.

    The command receives the HTML path as its last argv, runs with the
    process's cwd, and must print the public URL as its last non-blank
    stdout line.
    """
    if not html_path.is_file():
        return DashboardLocation(
            local_path=str(html_path),
            public_url=None,
            error=f"dashboard html not found: {html_path}",
        )
    cmd = publish_cmd or (env or os.environ).get(ENV_PUBLISH_CMD, "").strip() or None
    if not cmd:
        # ``Path.as_uri()`` raises ``ValueError`` on relative paths. The
        # auto-build pipeline used to crash here when callers passed a
        # relative ``--out-dir``. Resolve to an absolute path first so the
        # ``file://`` URI is always well-formed and the dashboard step
        # stays informational (never raises).
        return DashboardLocation(
            local_path=str(html_path),
            public_url=html_path.resolve().as_uri(),
            error=None,
            command=None,
        )
    return _publish_via_command(html_path, cmd)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering: synthesise a quality matrix HTML directly from a pipeline
# report, so callers don't have to populate the RRI inputs JSON by hand.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PipelineDigest:
    """What :func:`render_from_pipeline` needs to know.

    Decoupled from :class:`auto_build.PipelineReport` so this module
    doesn't import ``auto_build`` (cycle).
    """

    name: str
    ok: bool
    stages: list[dict[str, object]] = field(default_factory=list)
    matrix_inputs: dict[str, dict[str, str]] = field(default_factory=dict)
    # PR-18: relative filenames for the EA docs that the pipeline
    # promises will land in the same directory as quality-matrix.html.
    # Keys are formats ("html", "md", "pdf"); empty dict means the
    # docs stage is being skipped and the dashboard should NOT render
    # an embed card.
    docs_links: dict[str, str] = field(default_factory=dict)


_STAGE_TO_CELL: tuple[tuple[str, tuple[str, str]], ...] = (
    # stage name → (dim, axis) the gate populates in the 64-cell matrix
    ("build",   ("d_correctness", "implement")),
    ("lint",    ("d_correctness", "unit_test")),
    ("compile", ("d_correctness", "integration")),
    ("gate",    ("d_risk",        "design")),
)


def _stage_to_status(ok: bool, skipped: bool) -> str:
    if skipped:
        return "N/A"
    return "PASS" if ok else "FAIL"


def render_from_pipeline(digest: PipelineDigest) -> str:
    """Return the dashboard HTML for ``digest``.

    Cells touched by pipeline stages are filled from the stage results;
    everything else stays N/A (or honours ``digest.matrix_inputs`` when
    the caller has run a fuller RRI evaluation separately).

    When ``digest.docs_links`` is populated, a styled EA Docs card is
    appended after the matrix linking to the sibling ``<EAName>.docs.*``
    files written by the docs stage. The card is purely informational
    (relative ``<a href>`` links opened from disk).
    """
    matrix = matrix_mod.populate_from_inputs(digest.matrix_inputs)
    for stage in digest.stages:
        name = str(stage.get("name", ""))
        axis_dim = dict(_STAGE_TO_CELL).get(name)
        if not axis_dim:
            continue
        dim, axis = axis_dim
        status = _stage_to_status(
            ok=bool(stage.get("ok")),
            skipped=bool(stage.get("skipped")),
        )
        note = name
        matrix.set(dim, axis, status, note)
    body = matrix_mod.render_html(matrix)
    embed = _render_docs_embed(digest.name, digest.docs_links)
    if embed:
        # Inject before </body> so the card shows under the matrix
        # without disturbing the existing markup contract.
        body = body.replace("</body>", f"{embed}</body>", 1)
    return body


_DOCS_FORMAT_LABELS: dict[str, str] = {
    "html": "Open HTML (browser)",
    "pdf": "Download PDF",
    "md": "View Markdown source",
}


def _render_docs_embed(ea_name: str, links: dict[str, str]) -> str:
    """Render the Neo-Retro Dev Deck docs card or empty string.

    ``links`` maps format → relative filename (e.g. ``{'html':
    'MyEA.docs.html'}``). Empty dict (docs skipped) renders nothing
    so the dashboard contract stays back-compat.
    """
    from html import escape

    if not links:
        return ""
    items = []
    for fmt in ("html", "pdf", "md"):
        href = links.get(fmt)
        if not href:
            continue
        label = _DOCS_FORMAT_LABELS.get(fmt, fmt)
        items.append(
            f'<li><a href="{escape(href)}">{escape(label)}</a> '
            f'<small>({escape(fmt)})</small></li>'
        )
    if not items:
        return ""
    return (
        '<section class="ea-docs-embed" style="'
        'margin-top:24px;padding:16px;border:4px solid #000;'
        'background:#FFD600;color:#000;font-family:sans-serif;'
        'max-width:720px">'
        f'<h2 style="margin:0 0 8px 0">{escape(ea_name)} — EA Docs</h2>'
        '<p style="margin:0 0 12px 0;font-size:14px">'
        'Auto-generated user guide for this build. '
        'Open the HTML in a browser, share the PDF, or diff the '
        'Markdown source on git.</p>'
        f'<ul style="margin:0;padding-left:20px">{"".join(items)}</ul>'
        '</section>'
    )


def write_dashboard(digest: PipelineDigest, out_dir: Path) -> Path:
    """Render :func:`render_from_pipeline` and write it to ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "quality-matrix.html"
    html_path.write_text(render_from_pipeline(digest), encoding="utf-8")
    return html_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _digest_from_args(stages: Iterable[str], name: str, ok: bool) -> PipelineDigest:
    parsed_stages: list[dict[str, object]] = []
    for raw in stages:
        # Accept "build=ok", "lint=warn", "compile=fail", "gate=skip".
        if "=" not in raw:
            parsed_stages.append({"name": raw, "ok": True, "skipped": False})
            continue
        stage_name, state = raw.split("=", 1)
        state = state.strip().lower()
        parsed_stages.append({
            "name": stage_name.strip(),
            "ok": state in ("ok", "pass", "true", "1"),
            "skipped": state in ("skip", "skipped", "n/a"),
        })
    return PipelineDigest(name=name, ok=ok, stages=parsed_stages)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="mql5-dashboard",
        description="Render + publish the quality-matrix dashboard.",
    )
    ap.add_argument("--out-dir", type=Path, required=True,
                    help="Directory the HTML + report.json will be written to")
    ap.add_argument("--name", default="ea",
                    help="EA name (used in the heading)")
    ap.add_argument("--stage", action="append", default=[],
                    metavar="name=state",
                    help="Pipeline stage result (e.g. build=ok, gate=skip). "
                         "May be passed multiple times.")
    ap.add_argument("--ok", action="store_true",
                    help="Mark the digest as overall-ok")
    ap.add_argument("--publish-cmd", default=None,
                    help="Override $MQL5_DASHBOARD_PUBLISH_CMD for this run")
    ap.add_argument("--no-publish", action="store_true",
                    help="Render the HTML but do not run the publish hook")
    args = ap.parse_args(argv)

    digest = _digest_from_args(args.stage, args.name, args.ok)
    html_path = write_dashboard(digest, args.out_dir)
    if args.no_publish:
        # ``Path.as_uri()`` raises ``ValueError`` on relative paths; resolve
        # so ``mql5-dashboard --no-publish --out-dir ./relative`` works.
        location = DashboardLocation(
            local_path=str(html_path),
            public_url=html_path.resolve().as_uri(),
            error=None,
            command=None,
        )
    else:
        location = publish(html_path, publish_cmd=args.publish_cmd)
    print(json.dumps(location.to_dict(), indent=2))
    return 0 if location.error is None else 1


if __name__ == "__main__":
    sys.exit(main())
