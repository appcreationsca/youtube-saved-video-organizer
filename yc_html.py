"""Offline HTML page generators for the YouTube organizer.

Split out of youtube_cleaner.py to keep the CLI/logic module readable. These
build fully self-contained, client-side review/mapping pages (no network, no
third-party deps) that the `sort` and `map` commands write to disk. Each
function takes plain data, writes ``out_path``, and returns the byte length.
"""

from __future__ import annotations

import html
import json


def render_sort_html(source: dict, plan_by_target: dict[str, list[dict]],
                     owned_titles, out_path: str) -> int:
    """Write a self-contained, OFFLINE interactive review page for a sort plan.

    ``plan_by_target`` is target -> list of item dicts (video_id, title, channel,
    creates), the same per-item shape ``sort --json`` emits. The page lets the
    user reassign any video via a dropdown and Download a corrected plan.json in
    the exact schema ``apply``/``_load_plan`` reads. It makes ZERO network
    requests (system fonts, inline CSS/JS) -- nothing leaves the browser.
    """
    owned = list(owned_titles)
    owned_set = set(owned)
    esc = lambda s: html.escape(s if s is not None else "")
    esc_attr = lambda s: html.escape(s if s is not None else "", quote=True)

    total = sum(len(v) for v in plan_by_target.values())
    # Destination groups, largest first (mirrors the report's ordering).
    groups = sorted(plan_by_target.items(), key=lambda kv: len(kv[1]), reverse=True)

    # Dropdown option set: every owned playlist title UNION every proposed target.
    option_names = sorted(owned_set | set(plan_by_target.keys()), key=str.lower)

    def options_html(selected: str) -> str:
        opts = []
        for name in option_names:
            badge = "" if name in owned_set else "  (would create)"
            sel = " selected" if name == selected else ""
            opts.append(f'<option value="{esc_attr(name)}"{sel}>'
                        f'{esc(name)}{esc(badge)}</option>')
        opts.append('<option value="__skip__">\u2014 skip (leave in source) \u2014</option>')
        opts.append('<option value="__new__">\uff0b new playlist\u2026</option>')
        return "".join(opts)

    # Summary rows (count per destination + would-create badge).
    maxc = max((len(v) for v in plan_by_target.values()), default=1) or 1
    summary_rows = []
    for name, its in groups:
        c = len(its)
        badge = '<span class="new">would create</span>' if name not in owned_set else ""
        pct = round(c / total * 100) if total else 0
        barw = round(c / maxc * 100)
        summary_rows.append(
            f'<tr><td><b>{esc(name)}</b> {badge}</td>'
            f'<td class="num">{c}</td><td class="num dim">{pct}%</td>'
            f'<td><div class="bar"><div class="fill" style="width:{barw}%"></div></div></td></tr>'
        )

    # Collapsible per-destination sections; each row carries its own dropdown +
    # a hidden "new name" input the "＋ new playlist…" option reveals.
    sections = []
    for gi, (name, its) in enumerate(groups):
        open_attr = " open" if gi == 0 else ""
        rows = []
        for it in its:
            vid = it.get("video_id", "")
            title = it.get("title", "")
            channel = it.get("channel", "")
            rows.append(
                f'<li class="vrow" data-video-id="{esc_attr(vid)}" '
                f'data-title="{esc_attr(title)}" data-channel="{esc_attr(channel)}">'
                f'<span class="t">{esc(title)}</span>'
                f'<span class="ch">{esc(channel)}</span>'
                f'<span class="pick"><select class="target" '
                f'onchange="onPick(this)">{options_html(name)}</select>'
                f'<input class="newname" type="text" placeholder="New playlist name" '
                f'oninput="refreshTally()" hidden></span></li>'
            )
        sections.append(
            f'<details{open_attr}><summary><b>{esc(name)}</b>'
            f'<span class="cnt">{len(its)}</span></summary>'
            f'<ol class="vids">{"".join(rows)}</ol></details>'
        )

    # Embed the plan so the download rebuilds source.id/title verbatim. json.dumps
    # already escapes quotes/backslashes/control chars into a valid JS string
    # literal; for safe <script> embedding we ONLY additionally neutralize the
    # characters that could terminate the element or are illegal in a JS string:
    # `<` (so `</script>` in a title can't close the block), `>` and `&` (defense
    # in depth), and U+2028/U+2029 (valid in JSON, but line terminators in JS).
    # NOTE: we must NOT re-escape backslashes here — doubling them corrupts the
    # already-valid JSON and lets a title containing a quote break out (code exec).
    def _embed(obj) -> str:
        s = json.dumps(obj, ensure_ascii=False)
        return (s.replace("<", "\\u003c").replace(">", "\\u003e")
                 .replace("&", "\\u0026")
                 .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))

    plan_json = _embed(
        {"source": {"id": source.get("id", ""), "title": source.get("title", "")},
         "total": total,
         "by_target": plan_by_target})
    owned_json = _embed(owned)

    src_title = esc(source.get("title", ""))
    src_id = esc(source.get("id", ""))
    would_create = sum(1 for n in plan_by_target if n not in owned_set)

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sort Plan \u2014 Review &amp; Correct</title>
<style>
:root{{--bg:#f6f4ee;--surface:#fffdf8;--border:rgba(30,40,60,.14);--text:#1b2430;
  --dim:#5c6672;--navy:#1e3a5f;--gold:#b8860b;--line:#e6e1d6;--ok:#0f8a5f;}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--surface:#181c24;
  --border:rgba(255,255,255,.10);--text:#e8e6df;--dim:#98a0ab;--navy:#7fb0e0;
  --gold:#d4a73a;--line:#242a34;--ok:#3ecf8e;}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);line-height:1.5;
  font-family:ui-serif,Georgia,'Times New Roman',serif;}}
.mono{{font-family:ui-monospace,'SFMono-Regular',Menlo,Consolas,monospace}}
.wrap{{max-width:940px;margin:0 auto;padding:40px 24px 80px}}
h1{{font-size:40px;line-height:1.08;margin:0 0 6px;font-weight:600}}
.sub{{font-family:ui-monospace,Consolas,monospace;font-size:12px;letter-spacing:.4px;
  text-transform:uppercase;color:var(--dim);margin-bottom:10px}}
.dry{{display:inline-block;font-family:ui-monospace,Consolas,monospace;font-size:11px;
  font-weight:700;color:var(--gold);border:1px solid var(--gold);border-radius:4px;
  padding:2px 8px;margin-bottom:26px}}
.banner{{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--ok);
  border-radius:10px;padding:14px 18px;margin:0 0 26px;font-size:15px}}
h2{{font-size:24px;margin:30px 0 12px;border-bottom:1px solid var(--line);padding-bottom:7px;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:var(--surface);
  border:1px solid var(--border);border-radius:10px;overflow:hidden}}
th,td{{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{font-family:ui-monospace,Consolas,monospace;font-size:10.5px;text-transform:uppercase;
  letter-spacing:.5px;color:var(--dim);font-weight:600}}
tr:last-child td{{border-bottom:none}}
td.num{{font-family:ui-monospace,Consolas,monospace;font-weight:700;text-align:right;width:60px}}
.dim{{color:var(--dim)}}
.bar{{background:var(--line);border-radius:6px;height:9px;width:100%;min-width:100px}}
.fill{{height:9px;border-radius:6px;background:var(--navy)}}
.new{{font-family:ui-monospace,Consolas,monospace;font-size:9px;font-weight:700;color:var(--gold);
  border:1px solid var(--gold);border-radius:4px;padding:1px 5px;margin-left:6px}}
.toolbar{{position:sticky;top:0;z-index:5;background:var(--bg);padding:14px 0;
  border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}}
button{{font:inherit;font-size:15px;cursor:pointer;border-radius:8px;padding:10px 18px;
  border:1px solid var(--navy);background:var(--navy);color:#fff;font-weight:600}}
button:hover{{opacity:.92}}
.count{{font-family:ui-monospace,Consolas,monospace;font-size:13px;color:var(--dim)}}
details{{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  margin:8px 0;padding:2px 4px}}
summary{{cursor:pointer;padding:11px 13px;font-size:17px;list-style:none;display:flex;align-items:center}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"+";font-family:ui-monospace,Consolas,monospace;color:var(--dim);
  margin-right:11px;font-size:15px}}
details[open] summary::before{{content:"\u2212"}}
.cnt{{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dim);margin-left:auto;
  background:var(--line);border-radius:20px;padding:2px 10px}}
ol.vids{{margin:0 6px 12px;padding:4px 0;list-style:none;border-top:1px solid var(--line)}}
ol.vids li{{display:flex;gap:10px;padding:8px 10px;border-bottom:1px solid var(--line);
  font-size:14.5px;align-items:center;flex-wrap:wrap}}
ol.vids li:last-child{{border-bottom:none}}
.vrow .t{{flex:1;min-width:180px;overflow-wrap:anywhere}}
.vrow .ch{{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--dim);
  white-space:nowrap;max-width:150px;overflow:hidden;text-overflow:ellipsis}}
.vrow .pick{{display:flex;gap:6px;align-items:center}}
select,.newname{{font:inherit;font-size:13px;padding:5px 7px;border-radius:6px;
  border:1px solid var(--border);background:var(--surface);color:var(--text);max-width:210px}}
.vrow.changed{{background:rgba(15,138,95,.08)}}
.vrow.skip .t{{text-decoration:line-through;color:var(--dim)}}
code.cmd{{display:block;font-family:ui-monospace,Consolas,monospace;font-size:13px;
  background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:12px 14px;margin:10px 0;overflow-wrap:anywhere}}
</style></head><body><div class="wrap">
<h1>Sort Plan \u2014 Review &amp; Correct</h1>
<div class="sub">Source: {src_title} &middot; {src_id}</div>
<span class="dry">DRY-RUN \u2014 review page, no changes made</span>
<div class="banner"><b>{total}</b> proposed move(s) into <b>{len(groups)}</b> destination(s)
({would_create} would be created). Reassign any wrong pick with its dropdown, then
<b>Download corrected plan.json</b>. This page runs <b>offline</b> \u2014 nothing leaves your browser.</div>

<div class="toolbar">
  <button id="dl" onclick="downloadPlan()">Download corrected plan.json</button>
  <span class="count" id="tally"></span>
</div>

<h2>Destinations</h2>
<table><thead><tr><th>Playlist</th><th class="num">Videos</th><th class="num">Share</th>
<th style="width:38%">&nbsp;</th></tr></thead><tbody id="destBody">{"".join(summary_rows)}</tbody></table>

<h2>Videos (reassign any target)</h2>
<p class="dim mono" style="font-size:12px">Grouped by proposed target. Each dropdown can send a
video to ANY playlist, &ldquo;skip&rdquo; to leave it in the source, or &ldquo;\uff0b new playlist\u2026&rdquo; to type a name.</p>
{"".join(sections)}

<h2>Then apply it</h2>
<p class="dim" style="font-size:14px">Run this against the file you just downloaded
(add <span class="mono">--execute</span> once it looks right). It moves exactly what the
file says \u2014 no re-classification.</p>
<code class="cmd">python youtube_cleaner.py apply --plan corrected-plan.json --execute</code>

<script>
const PLAN = {plan_json};
const OWNED = {owned_json};

function onPick(sel) {{
  const row = sel.closest('.vrow');
  const newname = row.querySelector('.newname');
  newname.hidden = (sel.value !== '__new__');
  if (sel.value === '__new__') newname.focus();
  row.classList.toggle('skip', sel.value === '__skip__');
  refreshTally();
}}

function currentTarget(row) {{
  const v = row.querySelector('select.target').value;
  if (v === '__skip__') return null;
  if (v === '__new__') {{
    const name = (row.querySelector('.newname').value || '').trim();
    return name || null;   // empty typed name -> treat as skip
  }}
  return v;
}}

function buildPlan() {{
  const by_target = {{}};
  document.querySelectorAll('.vrow').forEach(row => {{
    const target = currentTarget(row);
    if (!target) return;              // skipped rows are omitted entirely
    (by_target[target] = by_target[target] || []).push({{
      video_id: row.dataset.videoId,
      title: row.dataset.title,
      channel: row.dataset.channel,
      creates: !OWNED.includes(target),
    }});
  }});
  let total = 0;
  Object.values(by_target).forEach(l => total += l.length);
  return {{ source: PLAN.source, total, by_target }};
}}

function refreshTally() {{
  const p = buildPlan();
  const dests = Object.keys(p.by_target).length;
  document.getElementById('tally').textContent =
    p.total + ' move(s) into ' + dests + ' destination(s) \u00b7 ' +
    (document.querySelectorAll('.vrow').length - p.total) + ' skipped';
  renderDestinations(p);
}}

// Escape for safe innerHTML (playlist names can contain <, &, quotes, and a
// user-typed new name is arbitrary text).
function escapeHtml(s) {{
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}}

// Rebuild the Destinations table from the CURRENT picks so it stays in sync with
// the dropdowns / typed new-playlist names (mirrors the server-side summary_rows).
function renderDestinations(p) {{
  const entries = Object.entries(p.by_target);
  entries.sort((a, b) => b[1].length - a[1].length);   // largest first
  const total = p.total || 0;
  let maxc = 1;
  entries.forEach(e => {{ if (e[1].length > maxc) maxc = e[1].length; }});
  const rows = entries.map(e => {{
    const name = e[0], c = e[1].length;
    const badge = OWNED.includes(name) ? '' : '<span class="new">would create</span>';
    const pct = total ? Math.round(c / total * 100) : 0;
    const barw = Math.round(c / maxc * 100);
    return '<tr><td><b>' + escapeHtml(name) + '</b> ' + badge + '</td>' +
      '<td class="num">' + c + '</td><td class="num dim">' + pct + '%</td>' +
      '<td><div class="bar"><div class="fill" style="width:' + barw + '%"></div></div></td></tr>';
  }});
  document.getElementById('destBody').innerHTML = rows.join('') ||
    '<tr><td class="dim" colspan="4">No destinations \u2014 every video skipped.</td></tr>';
}}

function downloadPlan() {{
  const data = JSON.stringify(buildPlan(), null, 2);
  const blob = new Blob([data], {{ type: 'application/json' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'corrected-plan.json';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}}

refreshTally();
</script>
</div></body></html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return len(page)



def render_map_html(source: dict, groups: dict[str, list[dict]],
                    cat_names: dict, owned_titles, uncategorized: int,
                    out_path: str, keyword_candidates: dict | None = None,
                    tier: str = "both") -> int:
    """Write a self-contained, OFFLINE interactive mapping page.

    ``groups`` is categoryId -> list of {video_id, title, channel} for the
    videos ACTUALLY saved in the source playlist (only categories present in the
    user's own videos appear).

    ``tier`` selects what the page configures:

      "both" (DEFAULT, the combined page): category cards + per-video overrides
        AND an OPTIONAL keyword section (auto-derived candidates + a manual
        "add keyword -> playlist" row). "Download config.json" writes a single
        self-contained config.json: mode "cascade", category_map,
        video_overrides (optional) and keyword_rules (optional, embedded). The
        engine treats embedded keyword_rules as authoritative, so there is no
        separate rules.json to leave stale. Priority at sort time is
        per-video override > keyword > category.

      "category" (advanced single-tier): only the category cards; config.json
        pinned to mode "category" (keyword rules never consulted).

      "keyword" (advanced single-tier): only the keyword-candidate section;
        writes rules.json plus a config.json pinned to mode "keyword".

    Makes ZERO network requests (system fonts, inline CSS/JS).
    """
    owned = list(owned_titles)
    owned_set = set(owned)
    esc = lambda s: html.escape(s if s is not None else "")
    esc_attr = lambda s: html.escape(s if s is not None else "", quote=True)

    total = sum(len(v) for v in groups.values())
    # Categories present in the user's videos, largest first.
    cats_sorted = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    owned_opts_sorted = sorted(owned_set, key=str.lower)

    def options_html() -> str:
        opts = ['<option value="__skip__" selected>\u2014 skip (leave in place) \u2014</option>']
        for name in owned_opts_sorted:
            opts.append(f'<option value="{esc_attr(name)}">{esc(name)}</option>')
        opts.append('<option value="__new__">\uff0b new playlist\u2026</option>')
        return "".join(opts)

    def voptions_html() -> str:
        opts = ['<option value="__same__" selected>same as category</option>']
        for name in owned_opts_sorted:
            opts.append(f'<option value="{esc_attr(name)}">{esc(name)}</option>')
        opts.append('<option value="__new__">\uff0b new\u2026</option>')
        opts.append('<option value="__leave__">leave in place</option>')
        return "".join(opts)

    cat_counts: dict[str, int] = {}
    cards = []
    if tier in ("category", "both"):
        for cid, vids in cats_sorted:
            cat_counts[cid] = len(vids)
            name = cat_names.get(str(cid)) or cat_names.get(cid) or f"Category {cid}"
            rows = []
            for v in vids:  # ALL videos, so any one can be overridden
                ch = (f' <span class="ch">{esc(v.get("channel",""))}</span>'
                      if v.get("channel") else "")
                rows.append(
                    f'<li data-vid="{esc_attr(v.get("video_id",""))}">'
                    f'<a href="https://www.youtube.com/watch?v='
                    f'{esc_attr(v.get("video_id",""))}" target="_blank" rel="noopener">'
                    f'{esc(v.get("title","(unknown)"))}</a>{ch}'
                    f'<span class="vov"><select class="vpick" onchange="onVPick(this)">'
                    f'{voptions_html()}</select>'
                    f'<input class="vnew" type="text" placeholder="New playlist name" '
                    f'oninput="refreshTally()" hidden></span></li>')
            cards.append(
                f'<section class="cat" data-cat="{esc_attr(str(cid))}">'
                f'<div class="cathead"><div class="catname">{esc(name)}'
                f'<span class="cnt">{len(vids)}</span></div>'
                f'<div class="pickwrap"><label>Send these to:</label>'
                f'<select class="pick" onchange="onPick(this)">{options_html()}</select>'
                f'<input class="newname" type="text" placeholder="New playlist name" '
                f'oninput="refreshTally()" hidden></div></div>'
                f'<div class="status">skipped (left in place)</div>'
                f'<details><summary>{len(vids)} video(s) \u2014 expand to override '
                f'individual videos</summary><ol class="vids">{"".join(rows)}</ol>'
                f'</details></section>')

    def _embed(obj) -> str:
        s = json.dumps(obj, ensure_ascii=False)
        return (s.replace("<", "\\u003c").replace(">", "\\u003e")
                 .replace("&", "\\u0026")
                 .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))

    # --- keyword-rule candidates (keyword tier + combined "both") ---
    kc = keyword_candidates or {}
    kw_channels = kc.get("channels", []) if tier in ("keyword", "both") else []
    kw_terms = kc.get("terms", []) if tier in ("keyword", "both") else []

    def _kw_card(kind: str, cand: dict) -> str:
        key = cand.get("key", "")
        cnt = int(cand.get("count", 0))
        ex_rows = "".join(
            f'<li>{esc(t)}</li>' for t in cand.get("examples", [])[:3])
        examples = (f'<details><summary>examples</summary>'
                    f'<ol class="vids">{ex_rows}</ol></details>' if ex_rows else "")
        tag = "channel" if kind == "channel" else "word"
        return (
            f'<section class="kw" data-kw="{esc_attr(key)}" data-count="{cnt}">'
            f'<div class="cathead"><div class="catname">'
            f'<span class="kwtag">{tag}</span> {esc(key)}'
            f'<span class="cnt">{cnt}</span></div>'
            f'<div class="pickwrap"><label>Videos matching &rarr;</label>'
            f'<select class="pick" onchange="onPick(this)">{options_html()}</select>'
            f'<input class="newname" type="text" placeholder="New playlist name" '
            f'oninput="refreshTally()" hidden></div></div>'
            f'<div class="status">skipped (no rule)</div>'
            f'{examples}</section>')

    kw_section = ""
    if tier in ("keyword", "both") and (kw_channels or kw_terms or tier == "both"):
        if tier == "both":
            head = ('<h2 class="kwh">Keyword rules '
                    '<span class="kwh-sub">optional &middot; higher priority than the category map</span></h2>'
                    '<p class="lead">Keywords are optional but win over the category map when they '
                    'match: any video whose <b>title or channel</b> contains the word/phrase goes '
                    'straight to that playlist. Handy when one category holds different topics, or '
                    'to catch <b>future</b> saves. Leave them all skipped to sort by category only.</p>'
                    '<div class="addkw"><input id="mkw" type="text" '
                    'placeholder="keyword or phrase (matches title or channel)" '
                    'oninput="refreshTally()">'
                    f'<select id="mkwt" onchange="onManualTarget()">{options_html()}</select>'
                    '<input id="mkwnew" type="text" placeholder="New playlist name" hidden>'
                    '<button type="button" class="addbtn" onclick="addKeyword()">'
                    '\uff0b Add keyword</button></div>')
        else:
            head = ('<h2 class="kwh">Keyword rules '
                    '<span class="kwh-sub">Tier 1 &middot; a rule matches every video whose title/channel contains it</span></h2>'
                    '<p class="lead">These channels and title words come from <b>your own</b> saved '
                    'videos. Mapping one writes a keyword rule: every video whose title or channel '
                    'contains it goes to that playlist. Leave any you don\u2019t want as \u201cskip\u201d.</p>')
        parts = [head, '<div id="kwlist">']
        if kw_channels:
            parts.append('<h3 class="kwsub">Channels you saved 2+ videos from</h3>')
            parts.extend(_kw_card("channel", c) for c in kw_channels)
        if kw_terms:
            parts.append('<h3 class="kwsub">Frequent words in your titles</h3>')
            parts.extend(_kw_card("term", t) for t in kw_terms)
        if tier == "both" and not (kw_channels or kw_terms):
            parts.append('<p class="lead" style="font-size:13px">No repeated channels or '
                         'title words were found \u2014 add your own above if you want keyword rules.</p>')
        parts.append('</div>')
        kw_section = "".join(parts)

    counts_json = _embed(cat_counts)
    owned_json = _embed(owned)
    src_title = esc(source.get("title", ""))
    src_id = esc(source.get("id", ""))
    uncat_note = (f'<p class="uncat">{uncategorized} video(s) had no YouTube '
                  "category (deleted/private/unavailable) and can\u2019t be "
                  "category-sorted \u2014 they\u2019re left out of this map.</p>"
                  if uncategorized and tier in ("category", "both") else "")

    n_cats = len(cats_sorted)
    n_kw = len(kw_channels) + len(kw_terms)
    if tier == "keyword":
        page_title = f"Keyword rules \u2014 {src_title}"
        h1_text = "Keyword rules"
        sub_line = (f"SOURCE: {src_title} \u00b7 {src_id} \u00b7 "
                    f"{n_kw} keyword candidate(s)")
        intro_lead = ("These channels and title words come from <b>your own</b> saved "
                      "videos. Map any to a playlist to write a keyword rule (Tier 1): "
                      "every video whose title or channel contains it goes there. Then "
                      "<b>Download</b> \u2014 you get <b>rules.json</b> plus a "
                      "<b>config.json</b> pinned to keyword mode \u2014 and run a sort.")
        bar_button = "Download rules.json + config.json"
        bar_hint = ("Nothing is changed on YouTube. This writes <b>rules.json</b> + "
                    "<b>config.json</b> (mode: keyword \u2014 the category map is not used). "
                    f'Run <span class="mono">sort --source {src_id}</span> to preview.')
        tally_init = "0 keyword rules"
    elif tier == "both":
        page_title = f"Sort map \u2014 {src_title}"
        h1_text = "Sort map"
        sub_line = (f"SOURCE: {src_title} \u00b7 {src_id} \u00b7 {total} categorized "
                    f"video(s) \u00b7 {n_cats} categor{'y' if n_cats == 1 else 'ies'}"
                    + (f" \u00b7 {n_kw} keyword candidate(s)" if n_kw else ""))
        intro_lead = ("Map each YouTube category your saved videos <b>actually</b> fall into "
                      "to one of your playlists (or a new name, or leave it skipped). "
                      "<b>Expand a category</b> to override individual videos when it holds "
                      "different topics. Keywords below are <b>optional</b> \u2014 add them to "
                      "override the category map or catch future saves. Then <b>Download "
                      "config.json</b> (one self-contained file) and run a sort.")
        bar_button = "Download config.json"
        bar_hint = ("Nothing is changed on YouTube. This writes one self-contained "
                    "<b>config.json</b> (mode: cascade \u2014 override &gt; keyword &gt; "
                    "category; keyword rules are embedded, no separate file). Run "
                    f'<span class="mono">sort --source {src_id}</span> to preview the moves.')
        tally_init = "0 categories mapped"
    else:
        page_title = f"Category map \u2014 {src_title}"
        h1_text = "Category map"
        sub_line = (f"SOURCE: {src_title} \u00b7 {src_id} \u00b7 {total} categorized "
                    f"video(s) \u00b7 {n_cats} categor{'y' if n_cats == 1 else 'ies'}")
        intro_lead = ("These are the YouTube categories your saved videos <b>actually</b> "
                      "fall into. Map each to one of your playlists (or a new name, or leave "
                      "it skipped). Need finer control? <b>Expand a category</b> and override "
                      "individual videos \u2014 handy when one category holds different topics "
                      "(e.g. some pregnancy, one recipe). Then <b>Download config.json</b> and "
                      "run a sort.")
        bar_button = "Download config.json"
        bar_hint = ("Nothing is changed on YouTube. This writes <b>config.json</b> "
                    "(mode: category \u2014 keyword rules are never used). Run "
                    f'<span class="mono">sort --source {src_id}</span> to preview the moves.')
        tally_init = "0 categories mapped"

    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<style>
:root{{--bg:#0f1218;--surface:#171b22;--card:#1c2029;--border:rgba(255,255,255,.09);
  --text:#e9ecf1;--dim:#9aa3b0;--accent:#5b9dd9;--accent2:#7ee0b8;--line:#252a34;
  --ok:#3ecf8e;--warn:#e0b23a;}}
@media (prefers-color-scheme:light){{:root{{--bg:#eef1f5;--surface:#ffffff;
  --card:#fbfcfe;--border:rgba(20,30,50,.14);--text:#1a2230;--dim:#5a6472;
  --accent:#2563a8;--accent2:#0f8a5f;--line:#e3e7ee;--ok:#0f8a5f;--warn:#a9791a;}}}}
*{{box-sizing:border-box;min-width:0}}
body{{margin:0;background:var(--bg);color:var(--text);line-height:1.5;
  font-family:'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:900px;margin:0 auto;padding:32px 20px 120px}}
h1{{font-size:30px;line-height:1.12;margin:0 0 6px;font-weight:650}}
.sub{{font-family:ui-monospace,Consolas,monospace;font-size:12px;letter-spacing:.3px;
  color:var(--dim);margin-bottom:14px;overflow-wrap:break-word}}
.lead{{color:var(--dim);font-size:15px;margin:0 0 8px}}
.uncat{{color:var(--warn);font-size:13px;margin:6px 0 0}}
.cat{{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:16px 18px;margin:14px 0}}
.cathead{{display:flex;flex-wrap:wrap;gap:12px;align-items:center;
  justify-content:space-between}}
.catname{{font-size:18px;font-weight:640;display:flex;align-items:center;gap:10px}}
.cnt{{font-family:ui-monospace,Consolas,monospace;font-size:12px;font-weight:700;
  color:var(--accent);background:color-mix(in srgb,var(--accent) 16%,transparent);
  border-radius:20px;padding:2px 10px}}
.pickwrap{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.pickwrap label{{font-size:13px;color:var(--dim)}}
select,.newname{{font:inherit;font-size:14px;padding:7px 10px;border-radius:8px;
  border:1px solid var(--border);background:var(--surface);color:var(--text);
  max-width:230px}}
.status{{font-size:13px;color:var(--dim);margin-top:10px}}
.status.ok{{color:var(--ok);font-weight:600}}
details{{margin-top:10px}}
summary{{cursor:pointer;color:var(--dim);font-size:13px}}
ol.vids{{margin:8px 0 0;padding-left:22px}}
ol.vids li{{margin:3px 0;font-size:14px;overflow-wrap:break-word}}
ol.vids a{{color:var(--accent);text-decoration:none}}
ol.vids a:hover{{text-decoration:underline}}
.ch{{color:var(--dim);font-size:12px}}
.more{{color:var(--dim);list-style:none;margin-left:-14px}}
.vov{{display:inline-flex;gap:6px;align-items:center;margin-left:8px;vertical-align:middle}}
select.vpick,.vnew{{font:inherit;font-size:12px;padding:3px 6px;border-radius:6px;
  border:1px solid var(--border);background:var(--surface);color:var(--text);max-width:170px}}
.bar{{position:fixed;left:0;right:0;bottom:0;background:var(--surface);
  border-top:1px solid var(--border);padding:12px 20px;display:flex;gap:14px;
  align-items:center;justify-content:center;flex-wrap:wrap}}
#tally{{font-size:14px;color:var(--dim)}}
button{{font:inherit;font-size:15px;font-weight:600;padding:10px 20px;border-radius:9px;
  border:0;background:var(--accent);color:#fff;cursor:pointer}}
button:hover{{filter:brightness(1.08)}}
.hint{{color:var(--dim);font-size:12px;max-width:640px;margin:2px auto 0;text-align:center}}
.kwh{{font-size:22px;font-weight:640;margin:36px 0 4px;padding-top:22px;
  border-top:1px solid var(--line)}}
.kwh-sub{{font-size:13px;font-weight:400;color:var(--dim)}}
.kwsub{{font-size:13px;color:var(--dim);margin:18px 0 2px;font-weight:600;
  text-transform:uppercase;letter-spacing:.4px}}
.kw{{background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:13px 18px;margin:10px 0}}
.kwtag{{font-family:ui-monospace,Consolas,monospace;font-size:10px;
  text-transform:uppercase;letter-spacing:.5px;color:var(--accent2);
  background:color-mix(in srgb,var(--accent2) 18%,transparent);border-radius:6px;
  padding:2px 7px;margin-right:2px}}
.addkw{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0 4px;
  padding:12px 14px;background:var(--card);border:1px dashed var(--border);
  border-radius:10px}}
.addkw input[type=text]{{font:inherit;font-size:14px;padding:7px 10px;border-radius:8px;
  border:1px solid var(--border);background:var(--surface);color:var(--text);
  flex:1 1 240px;min-width:160px}}
.addbtn{{background:var(--accent2);color:#06231a}}
.kw.manual{{border-left:3px solid var(--accent2)}}
.rmkw{{font:inherit;font-size:12px;font-weight:600;padding:4px 10px;border-radius:7px;
  border:1px solid var(--border);background:var(--surface);color:var(--dim);cursor:pointer}}
.rmkw:hover{{color:var(--text)}}
</style></head><body><div class="wrap">
<h1>{h1_text}</h1>
<div class="sub">{sub_line}</div>
<p class="lead">{intro_lead}</p>
{uncat_note}
{"".join(cards)}
{kw_section}
<div class="bar">
  <span id="tally">{tally_init}</span>
  <button onclick="downloadAll()">{bar_button}</button>
  <div class="hint">{bar_hint}</div>
</div>
<script>
const CATCOUNT = {counts_json};
const OWNED = {owned_json};
const OWNED_SET = new Set(OWNED);
const TIER = '{tier}';

function onPick(sel){{
  const nn = sel.parentNode.querySelector('input.newname');
  if (sel.value === '__new__') {{ nn.hidden = false; nn.focus(); }}
  else {{ nn.hidden = true; }}
  refreshTally();
}}

function onVPick(sel){{
  const nn = sel.parentNode.querySelector('input.vnew');
  if (sel.value === '__new__') {{ nn.hidden = false; nn.focus(); }}
  else if (nn) {{ nn.hidden = true; }}
  refreshTally();
}}

// Per-video overrides for one category card.
// Returns {{overrides:{{vid:target}}, count:<# non-default picks>}} where target
// is a playlist name or the '__leave__' marker (skip that one video).
function catOverrides(sec){{
  const overrides = {{}}; let count = 0;
  sec.querySelectorAll('li[data-vid]').forEach(function(li){{
    const vp = li.querySelector('select.vpick'); if (!vp) return;
    let v = vp.value;
    if (v === '__same__') return;
    if (v === '__new__') {{
      v = li.querySelector('input.vnew').value.trim();
      if (!v) return;
    }}
    overrides[li.getAttribute('data-vid')] = v;
    count++;
  }});
  return {{ overrides: overrides, count: count }};
}}

// Collect category map + per-video overrides from the category cards.
function buildCategory(){{
  const cmap = {{}}, overrides = {{}};
  document.querySelectorAll('section.cat').forEach(function(sec){{
    const cid = sec.getAttribute('data-cat');
    const sel = sec.querySelector('select.pick');
    let target = sel.value;
    if (target === '__new__') target = sec.querySelector('input.newname').value.trim();
    if (target && target !== '__skip__') cmap[cid] = target;
    const ov = catOverrides(sec).overrides;
    for (const k in ov) overrides[k] = ov[k];
  }});
  return {{ cmap: cmap, overrides: overrides }};
}}

function buildConfig(){{
  if (TIER === 'keyword')
    return {{classify: {{mode: 'keyword', create_missing: true, unmatched: 'leave'}}}};
  const cat = buildCategory();
  const mode = (TIER === 'both') ? 'cascade' : 'category';
  const classify = {{mode: mode, create_missing: true,
                     unmatched: 'leave', category_map: cat.cmap}};
  if (Object.keys(cat.overrides).length) classify.video_overrides = cat.overrides;
  // Always embed keyword_rules for the combined page (even []), so the config is
  // fully self-contained and a leftover rules.json can never fire in cascade.
  if (TIER === 'both') classify.keyword_rules = buildRules().keyword_rules;
  return {{classify: classify}};
}}

function buildRules(){{
  const rules = [];
  document.querySelectorAll('section.kw').forEach(function(sec){{
    const sel = sec.querySelector('select.pick');
    let target = sel.value;
    if (target === '__skip__') return;
    if (target === '__new__') {{
      target = sec.querySelector('input.newname').value.trim();
      if (!target) return;
    }}
    rules.push({{ any: [sec.getAttribute('data-kw')], playlist: target }});
  }});
  return {{ keyword_rules: rules }};
}}

// --- manual keyword entry (combined "both" page) ---
function _pickSelect(){{
  const sel = document.createElement('select');
  sel.className = 'pick';
  sel.addEventListener('change', function(){{ onPick(sel); }});
  function opt(val, txt){{ const o = document.createElement('option');
    if (val !== null) o.value = val; o.textContent = txt; return o; }}
  sel.appendChild(opt('__skip__', '\u2014 skip (remove rule) \u2014'));
  OWNED.forEach(function(n){{ sel.appendChild(opt(null, n)); }});
  sel.appendChild(opt('__new__', '\uff0b new playlist\u2026'));
  return sel;
}}

function onManualTarget(){{
  const t = document.getElementById('mkwt');
  const nn = document.getElementById('mkwnew');
  nn.hidden = (t.value !== '__new__');
  if (!nn.hidden) nn.focus();
}}

function addKeyword(){{
  const kwIn = document.getElementById('mkw');
  const tSel = document.getElementById('mkwt');
  const nIn = document.getElementById('mkwnew');
  const kw = kwIn.value.trim();
  let target = tSel.value;
  if (target === '__new__') target = nIn.value.trim();
  if (!kw) {{ alert('Type a keyword or phrase first.'); return; }}
  if (!target || target === '__skip__') {{ alert('Pick a playlist for this keyword.'); return; }}

  const sec = document.createElement('section');
  sec.className = 'kw manual';
  sec.setAttribute('data-kw', kw);
  sec.setAttribute('data-count', '0');
  sec.setAttribute('data-manual', '1');

  const head = document.createElement('div'); head.className = 'cathead';
  const nameWrap = document.createElement('div'); nameWrap.className = 'catname';
  const tag = document.createElement('span'); tag.className = 'kwtag'; tag.textContent = 'manual';
  nameWrap.appendChild(tag);
  nameWrap.appendChild(document.createTextNode(' ' + kw));
  head.appendChild(nameWrap);

  const pw = document.createElement('div'); pw.className = 'pickwrap';
  const lbl = document.createElement('label'); lbl.innerHTML = 'Videos matching &rarr;';
  const sel = _pickSelect();
  const nn = document.createElement('input'); nn.type = 'text'; nn.className = 'newname';
  nn.placeholder = 'New playlist name'; nn.hidden = true;
  nn.addEventListener('input', refreshTally);
  // preset the picked target
  if (OWNED_SET.has(target)) {{ sel.value = target; }}
  else {{ sel.value = '__new__'; nn.hidden = false; nn.value = target; }}
  pw.appendChild(lbl); pw.appendChild(sel); pw.appendChild(nn);
  head.appendChild(pw);

  const rm = document.createElement('button'); rm.type = 'button'; rm.className = 'rmkw';
  rm.textContent = '\u00d7 remove';
  rm.addEventListener('click', function(){{ sec.remove(); refreshTally(); }});
  head.appendChild(rm);

  const st = document.createElement('div'); st.className = 'status';
  sec.appendChild(head); sec.appendChild(st);
  document.getElementById('kwlist').appendChild(sec);

  kwIn.value = ''; nIn.value = ''; nIn.hidden = true; tSel.value = '__skip__';
  refreshTally();
}}

// Update every keyword card's status; returns the number of active rules.
function kwTally(creates){{
  const kmap = {{}};
  buildRules().keyword_rules.forEach(function(r){{ kmap[r.any[0]] = r.playlist; }});
  let kws = 0;
  document.querySelectorAll('section.kw').forEach(function(sec){{
    const kw = sec.getAttribute('data-kw');
    const st = sec.querySelector('.status');
    const cnt = parseInt(sec.getAttribute('data-count'), 10) || 0;
    const manual = sec.getAttribute('data-manual') === '1';
    if (Object.prototype.hasOwnProperty.call(kmap, kw)) {{
      const name = kmap[kw]; kws++;
      const willCreate = !OWNED_SET.has(name);
      if (willCreate) creates.add(name);
      st.textContent = (manual
          ? '\u2192 "' + name + '" (manual rule)'
          : '\u2192 ~' + cnt + ' match(es) into "' + name + '"') +
        (willCreate ? '  (would create)' : '');
      st.className = 'status ok';
    }} else {{
      st.textContent = manual ? 'no playlist (removed)' : 'skipped (no rule)';
      st.className = 'status';
    }}
  }});
  return kws;
}}

// Update every category card's status; returns {{cats, vids, ovTotal}}.
function catTally(creates){{
  const cmap = buildCategory().cmap;
  let cats = 0, vids = 0, ovTotal = 0;
  document.querySelectorAll('section.cat').forEach(function(sec){{
    const cid = sec.getAttribute('data-cat');
    const st = sec.querySelector('.status');
    const cnt = CATCOUNT[cid] || 0;
    const co = catOverrides(sec);
    ovTotal += co.count;
    for (const k in co.overrides) {{
      const t = co.overrides[k];
      if (t !== '__leave__' && !OWNED_SET.has(t)) creates.add(t);
    }}
    if (Object.prototype.hasOwnProperty.call(cmap, cid)) {{
      const name = cmap[cid];
      const following = Math.max(cnt - co.count, 0);
      cats++; vids += following;
      const willCreate = !OWNED_SET.has(name);
      if (willCreate) creates.add(name);
      st.textContent = '\u2192 ' + following + ' video(s) into "' + name + '"' +
        (willCreate ? '  (would create)' : '') +
        (co.count ? '  \u00b7 ' + co.count + ' overridden' : '');
      st.className = 'status ok';
    }} else {{
      st.textContent = co.count
        ? (co.count + ' video(s) overridden (rest left in place)')
        : 'skipped (left in place)';
      st.className = co.count ? 'status ok' : 'status';
    }}
  }});
  return {{ cats: cats, vids: vids, ovTotal: ovTotal }};
}}

function refreshTally(){{
  const creates = new Set();
  if (TIER === 'keyword') {{
    const kws = kwTally(creates);
    document.getElementById('tally').textContent =
      kws + ' keyword rule' + (kws === 1 ? '' : 's') + ' \u00b7 ' +
      creates.size + ' new playlist(s)';
    return;
  }}
  const c = catTally(creates);
  let msg = c.cats + ' categor' + (c.cats === 1 ? 'y' : 'ies') + ' mapped';
  if (c.ovTotal) msg += ' \u00b7 ' + c.ovTotal + ' video override' + (c.ovTotal === 1 ? '' : 's');
  if (TIER === 'both') {{
    const kws = kwTally(creates);
    if (kws) msg += ' \u00b7 ' + kws + ' keyword rule' + (kws === 1 ? '' : 's');
  }}
  msg += ' \u00b7 ' + c.vids + ' categorized video(s) \u00b7 ' +
    creates.size + ' new playlist(s)';
  document.getElementById('tally').textContent = msg;
}}

function _dl(name, obj){{
  const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: 'application/json' }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}}

function downloadAll(){{
  if (TIER === 'keyword') {{
    const rules = buildRules();
    if (!rules.keyword_rules.length) {{
      alert('Map at least one channel or word to a playlist first.');
      return;
    }}
    _dl('rules.json', rules);
    setTimeout(function(){{ _dl('config.json', buildConfig()); }}, 400);
    return;
  }}
  const cfg = buildConfig();
  const cl = cfg.classify;
  const hasCats = Object.keys(cl.category_map).length > 0;
  const hasOv = cl.video_overrides && Object.keys(cl.video_overrides).length > 0;
  const hasKw = cl.keyword_rules && cl.keyword_rules.length > 0;
  if (!hasCats && !hasOv && !hasKw) {{
    alert(TIER === 'both'
      ? 'Map at least one category, video, or keyword to a playlist first.'
      : 'Map at least one category or video to a playlist first.');
    return;
  }}
  _dl('config.json', cfg);
}}

refreshTally();
</script>
</div></body></html>"""

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return len(page)

