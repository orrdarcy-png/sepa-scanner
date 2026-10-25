"""Inject scan data + the fundamental prompt pack into the single-file web page."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "scanner" / "template.html"
PROMPTS = ROOT / "prompts" / "prompts.yaml"


HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}'
        '[hidden]{display:none!important}img{max-width:100%}</style></head><body>')


def build(data: dict, out: Path, fragment: bool = False) -> None:
    """fragment=True skips the html/head wrapper (for publishing as a claude.ai artifact)."""
    html = TEMPLATE.read_text(encoding="utf-8")
    import yaml
    prompts = yaml.safe_load(PROMPTS.read_text(encoding="utf-8")) if PROMPTS.exists() else {}
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload).replace("/*__PROMPTS__*/{}", json.dumps(prompts).replace("</", "<\\/"))
    if not fragment:
        html = HEAD + html + "</body></html>"
    out.write_text(html, encoding="utf-8")
