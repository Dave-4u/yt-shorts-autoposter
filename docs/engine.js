/* Clip Studio engine: a faithful JS port of shorts_bot/analyze.py's offline
   heuristic, so the browser demo picks the same moments as the Python CLI.
   tests/test_engine_parity.py checks both agree on the sample transcript. */
(function (root) {
  const HOOK_WORDS = new Set(("secret mistake never always why how stop urgent shocking truth hack tip warning crazy insane " +
    "nobody everyone proven free easy simple actually wait watch listen remember important key biggest " +
    "worst best first last finally surprising revealed").split(" "));

  const r2 = (x) => Math.round(x * 100) / 100;
  const count = (s, ch) => s.split(ch).length - 1;

  function mergeWindows(segs, target, maxLen) {
    const out = [];
    let i = 0;
    while (i < segs.length) {
      const start = segs[i].start;
      const parts = [];
      let j = i, end = start;
      while (j < segs.length && segs[j].end - start < target) { parts.push(segs[j].text); end = segs[j].end; j++; }
      while (j < segs.length && segs[j].end - start <= maxLen) {
        parts.push(segs[j].text); end = segs[j].end; j++;
        if (end - start >= target) break;
      }
      if (end - start >= 8) out.push([start, end, parts.join(" ").trim()]);
      i += j > i ? Math.max(1, Math.floor((j - i) / 2)) : 1;
    }
    return out;
  }

  // Returns {score, why:[{label, pts}]} so the UI can explain the number.
  function scoreDetail(text, duration) {
    const why = [];
    if (!text) return { score: 0, why };
    const words = (text.toLowerCase().match(/[a-z']+/g) || []);
    if (!words.length) return { score: 0, why };
    let s = 0;
    const add = (pts, label) => { if (pts) { s += pts; why.push({ label, pts }); } };
    const q = count(text, "?"), ex = count(text, "!");
    add(q * 2.5, q === 1 ? "asks a question" : `asks ${q} questions`);
    add(ex * 1.5, "has energy (!)");
    const hooks = words.filter((w) => HOOK_WORDS.has(w));
    add(hooks.length * 1.5, hooks.length ? `hook words: ${[...new Set(hooks)].slice(0, 4).join(", ")}` : "");
    const sentences = text.split(/[.!?]+/).filter((x) => x.trim());
    const avg = sentences.length ? sentences.reduce((a, x) => a + x.split(/\s+/).filter(Boolean).length, 0) / sentences.length : 20;
    if (avg >= 5 && avg <= 18) add(3, "punchy sentences");
    else if (avg < 5) add(1, "very short lines");
    if (duration >= 20 && duration <= 45) add(4, "sweet-spot length");
    else if (duration >= 15 && duration <= 59) add(2, "Shorts-friendly length");
    else add(-1, "awkward length");
    const wpm = words.length / Math.max(duration / 60, 0.1);
    if (wpm >= 100 && wpm <= 200) add(2, `good pace (${Math.round(wpm)} wpm)`);
    return { score: r2(s), why };
  }

  function titleFrom(text, maxWords = 8) {
    const words = text.match(/[A-Za-z0-9']+/g);
    if (!words) return "Clip";
    const chunk = words.slice(0, maxWords).join(" ");
    const t = text.trim();
    if (/^(Why|How|What|When|Stop|Never)/.test(t)) {
      const m = t.match(/^([^.!?]{10,60})/);
      if (m) return m[1].trim().slice(0, 80);
    }
    return chunk.slice(0, 80);
  }

  function analyze(segments, opts = {}) {
    const minS = opts.minClip ?? 15, maxS = opts.maxClip ?? 59, maxShorts = opts.maxShorts ?? 10;
    const segs = segments.map((x) => ({ start: +x.start, duration: +x.duration, text: String(x.text), end: +x.start + +x.duration }));
    const windows = mergeWindows(segs, (minS + maxS) / 2, maxS);
    const scored = [];
    for (let [start, end, text] of windows) {
      let dur = end - start;
      if (dur < minS || dur > maxS + 2) {
        end = Math.min(start + maxS, end); dur = end - start;
        if (dur < minS) continue;
      }
      const d = scoreDetail(text, dur);
      scored.push({ start: r2(start), end: r2(end), title: titleFrom(text), hook: titleFrom(text, 6), score: d.score, text: text.slice(0, 500), why: d.why });
    }
    // stable sort, highest first (matches Python's sorted(reverse=True) stability)
    scored.sort((a, b) => b.score - a.score);
    const picked = [];
    for (const c of scored) {
      if (picked.some((p) => Math.abs(c.start - p.start) < 8)) continue;
      picked.push(c);
      if (picked.length >= maxShorts) break;
    }
    return picked;
  }

  // Accepts youtube-transcript JSON, "0:12 text" lines, SRT, or plain prose.
  function parseTranscript(raw, wpm = 155) {
    raw = (raw || "").trim();
    if (!raw) return [];
    if (raw[0] === "[") {
      const data = JSON.parse(raw);
      return data.map((d) => ({ start: +d.start, duration: +(d.duration ?? (d.end - d.start)), text: String(d.text) })).filter((d) => d.text);
    }
    const ts = (s) => { const p = s.replace(",", ".").split(":").map(Number); return p.reduce((a, x) => a * 60 + x, 0); };
    if (/-->/.test(raw)) {
      const out = [];
      for (const block of raw.split(/\n\s*\n/)) {
        const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
        const k = lines.findIndex((l) => l.includes("-->"));
        if (k < 0) continue;
        const [a, b] = lines[k].split("-->").map((x) => ts(x.trim().split(" ")[0]));
        const text = lines.slice(k + 1).join(" ");
        if (text) out.push({ start: a, duration: Math.max(0.1, b - a), text });
      }
      return out;
    }
    const lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
    const stamped = lines.map((l) => l.match(/^\[?(\d{1,2}(?::\d{2}){1,2}(?:\.\d+)?)\]?\s*[-–|]?\s*(.+)$/));
    if (stamped.filter(Boolean).length >= Math.max(2, lines.length * 0.6)) {
      const rows = stamped.filter(Boolean).map((m) => ({ start: ts(m[1]), text: m[2] }));
      return rows.map((r, i) => {
        const next = rows[i + 1] ? rows[i + 1].start : r.start + r.text.split(/\s+/).length / (wpm / 60);
        return { start: r.start, duration: Math.max(0.5, next - r.start), text: r.text };
      });
    }
    // plain prose: one segment per sentence, timed at a natural speaking pace
    const sentences = raw.replace(/\s+/g, " ").match(/[^.!?]+[.!?]*/g) || [];
    let t = 0;
    return sentences.map((s) => s.trim()).filter(Boolean).map((s) => {
      const d = Math.max(1.2, s.split(" ").length / (wpm / 60));
      const seg = { start: r2(t), duration: r2(d), text: s }; t += d; return seg;
    });
  }

  function chunkWords(text, n = 4) {
    const w = text.split(/\s+/).filter(Boolean), out = [];
    for (let i = 0; i < w.length; i += n) out.push(w.slice(i, i + n).join(" "));
    return out;
  }

  const api = { analyze, parseTranscript, scoreDetail, titleFrom, chunkWords, HOOK_WORDS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.ClipEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
