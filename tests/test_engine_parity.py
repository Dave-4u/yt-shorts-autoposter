"""The browser demo (docs/engine.js) must pick the same clips as the Python heuristic."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from shorts_bot.analyze import analyze_heuristic
from shorts_bot.config import Config
from shorts_bot.fetch import load_transcript_json

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("mn,mx,n", [(15, 59, 10), (20, 40, 5), (10, 30, 3)])
def test_js_engine_matches_python(mn, mx, n):
    segs = load_transcript_json(ROOT / "samples" / "sample_transcript.json")
    cfg = Config(min_clip_seconds=mn, max_clip_seconds=mx, max_shorts=n)
    py = [[c.start, c.end, c.title, c.score] for c in analyze_heuristic(segs, cfg)]
    js_src = (
        "const e=require('./docs/engine.js');const d=require('./samples/sample_transcript.json');"
        f"console.log(JSON.stringify(e.analyze(d,{{minClip:{mn},maxClip:{mx},maxShorts:{n}}})"
        ".map(c=>[c.start,c.end,c.title,c.score])))"
    )
    js = json.loads(subprocess.check_output(["node", "-e", js_src], cwd=ROOT))
    assert py == js
