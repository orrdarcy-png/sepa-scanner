"""Checks the pattern logic on synthetic charts with known answers. Run: python -m pytest -q"""
import numpy as np
import pandas as pd
import yaml
from pathlib import Path

from scanner import technical as tech
from scanner.synthetic import _ohlc, _path, _vcp

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())


def make(seg, seed=1):
    rng = np.random.default_rng(seed)
    c, v = _path(seg, 10.0, rng)
    o, h, l = _ohlc(c, rng, 0.01)
    return o, h, l, c, v * 1e6


def run(seg, rs=90, seed=1):
    o, h, l, c, v = make(seg, seed)
    idx = np.linspace(100, 120, len(c))
    return tech.analyze(o, h, l, c, v, rs, idx, CFG["trend_template"], CFG["vcp"])


def test_vcp_buy_ready():
    r = run(_vcp(np.random.default_rng(0)), seed=5)
    assert r["tt"]["pass"]
    assert r["base"]["valid"]
    assert 2 <= r["base"]["count"] <= 6
    c = r["base"]["contractions"]
    assert c[0] > c[-1]                       # contractions shrink left to right
    assert r["status"] in ("Buy-ready", "Setting up")


def test_breakout_detected():
    r = run(_vcp(np.random.default_rng(0), breakout=True))
    assert r["status"] == "Breaking out"
    assert r["breakout"]["strong_volume"]


def test_downtrend_fails_template():
    r = run([(250, 0.6, 0.012, 1.0), (250, -0.5, 0.015, 1.0)])
    assert not r["tt"]["pass"]
    assert r["stage"] in ("4", "1", "3")


def test_power_play():
    r = run([(420, 0.1, 0.01, 1.0), (30, 1.4, 0.015, 4.0), (20, -0.06, 0.006, 1.0)])
    assert r.get("power_play") is not None
    assert r["power_play"]["gain"] >= 100


def test_rs_rating_range():
    close = pd.DataFrame(np.cumprod(1 + np.random.default_rng(3).normal(0, 0.02, (300, 50)), axis=0))
    rs = tech.rs_rating(tech.rs_raw(close))
    assert rs.min() >= 1 and rs.max() <= 99
