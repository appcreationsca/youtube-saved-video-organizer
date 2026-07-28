# YouTube Saved-Video Organizer — Prototype

A safety-first prototype with **two parts**, because YouTube's API can do most of
the job but physically cannot touch Watch Later:

### Part 1 — `youtube_cleaner.py` (compliant, official YouTube Data API v3)
1. Sign in with your Google account (OAuth 2.0)
2. List your playlists
3. **Sort** saved videos into topic playlists (auto-creating them) using a
   layered classifier you enable once with the `setup` wizard
4. **Delete** videos older than *N* years from a playlist

> **Every write is DRY-RUN by default.** Nothing changes until you add `--execute`,
> and then only after you type a confirmation word.

### Part 2 — `watchlater-cleaner.user.js` (personal browser userscript)
Clears **Watch Later** (and any open playlist) by automating the logged-in UI —
the *only* way to do it, since no official API can access Watch Later.
**Personal use only; automating the UI is against YouTube's ToS.** See the
[Watch Later section](#watch-later-personal-userscript) below.

Part 1 manages **playlists you created** only. Watch Later / History / Liked are
not reachable by any API, and Instagram / Facebook expose no saved content at all.


---

## 1. Google Cloud setup — per user (one time, ~10 minutes)

This tool is open source with **no backend and no shared credentials**: each user
brings their **own** Google Cloud OAuth client, so you get your **own** daily API
quota (~10,000 units) and nobody else's usage can exhaust it. Nothing you do is
sent to us — auth happens directly between your machine and Google.

1. Go to <https://console.cloud.google.com/> and create a **new project**.
2. **APIs & Services → Library** → search **"YouTube Data API v3"** → **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - Fill in app name + your email, save through the steps.
   - **Test users:** add the Google account(s) you'll use. While the app is in
     "Testing", only these accounts can log in (no Google verification needed).
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Create, then **Download JSON**.
5. Rename the downloaded file to **`client_secret.json`** and place it in this
   `youtube-prototype/` folder (next to `youtube_cleaner.py`).

> `client_secret.json` and `token.json` are git-ignored. Never share them.

---

## 2. Install

```powershell
cd youtube-prototype
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 3. Use

```powershell
# One-time login (opens a browser). Caches token.json.
python youtube_cleaner.py auth

# See your playlists and their IDs / counts
python youtube_cleaner.py playlists

# Choose how videos get sorted (writes config.json). See "Classifier" below.
python youtube_cleaner.py setup

# DRY-RUN: show what WOULD be deleted (older than 2 years) — no changes
python youtube_cleaner.py clean --playlist PLxxxxxxxx --years 2

# Actually delete
python youtube_cleaner.py clean --playlist PLxxxxxxxx --years 2 --execute

# DRY-RUN: sort videos out of a source playlist into topic playlists
python youtube_cleaner.py sort --source PLxxxxxxxx

# Review first: write the FULL proposed plan to a file you can read/edit
python youtube_cleaner.py sort --source PLxxxxxxxx --json plan.json

# Actually move them (creates target playlists as needed)
python youtube_cleaner.py sort --source PLxxxxxxxx --execute

# Fixed a wrong pick in plan.json? Apply the edited plan EXACTLY as written
python youtube_cleaner.py apply --plan plan.json --execute

# Changed your mind? Reverse the last sort/apply run (videos go back)
python youtube_cleaner.py undo            # dry-run: shows what would be restored
python youtube_cleaner.py undo --execute  # actually move them back

# DRY-RUN: age-purge one playlist (older than 2 years) — no changes
python youtube_cleaner.py autopurge --playlist PLxxxxxxxx --years 2

# DRY-RUN: find deleted/private videos across ALL your playlists — no changes
python youtube_cleaner.py remove-unavailable

# Actually remove the dead entries (scan one playlist, type DELETE to confirm)
python youtube_cleaner.py remove-unavailable --playlist PLxxxxxxxx --execute
```

### `clean` options

| Option           | Meaning                                                                 |
|------------------|-------------------------------------------------------------------------|
| `--playlist`     | Playlist ID (get it from the `playlists` command). **Required.**        |
| `--years`        | Age threshold in **whole** years (e.g. `1`, `2`, `3`). **Required.**    |
| `--date-basis`   | `added` (default) = when the video entered the playlist; `published` = when the video was uploaded to YouTube. |
| `--execute`      | Actually delete (asks you to type `DELETE` to confirm). Omit for a safe dry-run. |
| `--yes`          | Skip the typed `DELETE` prompt (for scripts/schedulers). Use with care.  |
| `--max-deletes`  | Safety cap per run (default 150, min 1) to respect the daily API quota.  |

### `autopurge` options

`autopurge` is the **scheduler-friendly, multi-playlist** version of `clean`. It reads
a `purge` block from `config.json` and only ever touches the playlists you list there,
making it safe to run unattended in the daily task. Deletions are **oldest-first** and
capped by a per-run budget.

| Option           | Meaning                                                                 |
|------------------|-------------------------------------------------------------------------|
| `--playlist`     | Purge a single playlist by ID (bypasses the `purge` config list).       |
| `--years`        | Age threshold in **whole** years. Overrides `purge.years`.              |
| `--date-basis`   | `added` (default) or `published`. Overrides `purge.date_basis`.         |
| `--protect`      | Comma-separated playlist titles to skip. Overrides `purge.protect`.     |
| `--daily-budget` | Max deletes this run (~50 units each). Overrides `purge.daily_delete_budget`. |
| `--execute`      | Actually delete. Omit for a safe dry-run.                               |
| `--yes`          | Skip confirmation (for schedulers).                                     |

**Safety:** with **no** `purge` block **and** no `--playlist`, it prints a notice and
deletes nothing. Even with a config list it requires `"enabled": true`. Always dry-run
first (`autopurge --playlist <id> --years N`). Deletions are permanent.

**`purge` config block** (in `config.json`, opt-in):

```jsonc
"purge": {
  "enabled": false,               // must be true to delete anything
  "years": 2,                     // delete items older than N whole years
  "date_basis": "added",          // "added" (saved date) or "published"
  "playlists": ["Watch queue"],   // EXACT titles — only these are ever purged
  "protect": "Music,Podcasts",   // titles to always skip
  "daily_delete_budget": 120      // max deletes per run
}
```

### `sort` options

| Option         | Meaning                                                                    |
|----------------|----------------------------------------------------------------------------|
| `--source`     | Playlist ID to sort videos **out of** (e.g. an "Unsorted" catch-all). **Required.** |
| `--mode`       | Force one classifier layer for this run: `category`, `keyword`, `ai`, or `cascade` (default). Omit to use `config.json`. |
| `--execute`    | Actually move (asks you to type `MOVE` to confirm). Omit for a safe dry-run. |
| `--max-moves`  | Safety cap per run (default 40, min 1). Each move costs ~100 quota units.   |
| `--json PATH`  | Also write the **full** proposed plan (every video, not truncated) to a JSON file you can read, share, or **edit** before applying. |

---

## Accuracy & the review workflow

No automatic classifier is perfect — categories are subjective, and a few videos
per batch will land somewhere you disagree with (in our own testing, ~90–95% of
picks matched expectations). The design assumes this and puts **you** in control:
it **suggests, you approve**. Nothing is ever moved silently.

**The safe loop — review, correct, then approve:**

1. **Preview.** `sort` is **dry-run by default**: it prints every proposed move
   and changes nothing. Add `--json plan.json` to get the full, editable plan.
2. **Correct (optional).** Open `plan.json` and fix any wrong picks — move a
   video's entry under the right `target`, or delete its entry to leave it where
   it is. Then run **`apply --plan plan.json --execute`**, which moves *exactly*
   what the file says (no re-classification — what you reviewed is what happens).
   Prefer to just run it? `sort --execute` classifies and moves in one step.
3. **Undo.** Every `--execute` run writes an **undo journal** to `history/`. If
   you don't like the result, **`undo --execute`** puts every moved video back in
   its original playlist. Run `undo` alone first for a dry-run preview.

**Why this is safe by construction:**

- **Dry-run by default** on every write command (`sort`, `apply`, `undo`,
  `clean`, `autopurge`) — you always see the plan before anything changes.
- **Abstain on uncertainty.** When the AI isn't confident a video belongs in one
  of *your* playlists, it leaves it in place rather than guess. Tune how eager it
  is with `ai.abstain` (`high` / `normal` / `low` — see the config reference).
- **Only your own playlists** are ever used as targets — it can't invent odd
  categories.
- **No data loss.** Moves are insert-before-delete, so an interrupted run (e.g.
  quota) never drops a video, and `undo` fully reverses a completed run.
- A wrong sort is **not destructive** — the video is just in a different
  playlist, and one command moves it back.

> **Known limitation:** if a run is interrupted in the split second *between*
> adding a video to its target and removing it from the source (e.g. the daily
> quota runs out at exactly that moment), the video can end up in **both**
> playlists. Re-running `sort`/`apply` is safe and finishes the rest; just delete
> the stray copy from the source if you spot one. A video is never *lost*.

### `apply` options

Executes a reviewed/edited plan file (from `sort --json`) deterministically.
Idempotent: videos already moved are skipped, so it's safe to re-run if a run
hits the daily quota.

| Option        | Meaning                                                                  |
|---------------|--------------------------------------------------------------------------|
| `--plan PATH` | Plan JSON from `sort --json`, optionally edited to correct picks. **Required.** |
| `--execute`   | Actually move (type `MOVE` to confirm). Omit for a safe dry-run.         |
| `--max-moves` | Safety cap per run (default 40, min 1). ~100 quota units each.           |
| `--yes`       | Skip the typed `MOVE` prompt (for scripts).                             |

### `undo` options

Reverses a previous `sort`/`apply` run from its journal — each video is moved
back into the source playlist it came from. Idempotent and quota-capped.

| Option       | Meaning                                                                   |
|--------------|---------------------------------------------------------------------------|
| `--file PATH`| Journal to reverse (default: the most recent run in `history/`).          |
| `--execute`  | Actually move back (type `UNDO` to confirm). Omit for a safe dry-run.     |
| `--max-moves`| Safety cap per run (default 40, min 1). ~100 quota units each.            |
| `--yes`      | Skip the typed `UNDO` prompt (for scripts).                              |

> Undo journals live in `history/` and contain your video titles/IDs, so they're
> **git-ignored** and never leave your machine.

### `remove-unavailable` options

Removes **deleted** and **private** videos (the "Deleted video" / "Private video"
placeholders YouTube leaves behind) from your playlists to free up space. Scans
**all** your playlists unless `--playlist` is given. Dry-run by default.

| Option           | Meaning                                                                       |
|------------------|-------------------------------------------------------------------------------|
| `--playlist ID`  | Restrict to a single playlist ID. Omit to scan every playlist you own.        |
| `--execute`      | Actually delete (type `DELETE` to confirm). Omit for a safe dry-run.          |
| `--max-deletes`  | Safety cap per run (default 150, min 1). Each delete costs ~50 quota units.    |
| `--protect`      | Comma-separated playlist **titles** to skip when scanning all (ignored with `--playlist`). |
| `--json PATH`    | Also write the full list of dead entries to this file (an audit record).       |
| `--yes`          | Skip the typed `DELETE` prompt (for scripts).                                 |

> **How it detects dead videos:** it batch-checks each video ID against
> `videos.list`. A video that is present in the playlist but **absent** from that
> lookup is either deleted or private-and-not-yours — a reliable signal that
> doesn't depend on the (localizable, spoofable) placeholder title. Region-blocked
> and normal videos still resolve, so they're never flagged.
>
> **Not reversible.** Unlike `sort`/`apply`, this removal has **no `undo`** — a
> deleted video is gone from YouTube and a private video can't be re-added, so
> there is nothing to restore. Use the dry-run (and `--json`) to review first.

---

## Classifier — how videos get sorted (4 tiers)

You **enable layers once** (via `setup`, which writes `config.json`); at sort time
the engine runs the enabled layers as an automatic **first-match cascade** per
video and the first hit wins. You never pick a tier per video.

| Tier | Name | Setup | What it does |
|------|------|-------|--------------|
| **0** | Category (universal) | zero-config | Sorts by YouTube's own `categoryId` (Music, Gaming, Education…) into auto-named playlists. Works for anyone. |
| **1** | Category → **my** playlists | `setup` → `[2]` | Maps each YouTube category to one of **your** existing playlist names. **Recommended.** |
| **2** | Keyword rules | `setup` → `[3]` (maps starter buckets to **your** playlists), then edit `rules.json` | Substring match on title + channel. See `rules.example.json`. Advanced/personal — see note below. |
| **3** | AI classify | `setup` → `[4]` | Reads each title and picks from your playlists. Off by default; **bring your own key** or run local Ollama. |

**Cascade priority:** `keyword rule → AI → category map → leave in place`.
Run `sort --mode keyword|ai|category` to force a single layer for one run.

**Create-on-demand:** a mapped playlist that doesn't exist yet is created the
**first** time a video actually routes to it (idempotent by name — no duplicates
on re-runs). Set `create_missing: false` to skip-and-warn instead. Unmapped
categories are left in place, never auto-created. `playlists.insert` = 50 units.

### `config.json` reference

`setup` writes it for you; copy `config.example.json` to hand-edit. It is
git-ignored (it contains your playlist names). All fields live under `classify`:

| Field | Meaning |
|-------|---------|
| `mode` | `cascade` (default), `category`, `keyword`, or `ai`. `sort --mode` overrides it. |
| `create_missing` | `true` = create a mapped playlist on first use; `false` = skip + warn. |
| `unmatched` | `"leave"` (default) or a playlist name to collect everything unmatched. |
| `category_map` | `{ "<categoryId>": "<your playlist name>" }` — Tier 0/1. |
| `ai.enabled` | `false` by default. `true` turns Tier 3 on. |
| `ai.provider` | `ollama` (free, local, no key) · `openai` · `anthropic` · `gemini`. |
| `ai.model` | Model name for that provider (e.g. `llama3.1`, `gpt-4o-mini`). |
| `ai.endpoint` | Ollama base URL (default `http://localhost:11434`). Ollama only. |
| `ai.api_key_env` | **Name** of the env var holding your API key. The key is read from the environment at runtime and **never** stored in the file. |
| `ai.batch_size` | Videos classified per request (default `50`, 1–200). AI batches titles so it makes a few requests instead of one per video — cheaper and much faster. Smaller = safer; larger saves little extra. |
| `ai.abstain` | Recall vs precision knob: `high` (only files on a clear match — fewest moves), `normal` (best-fit; leaves a video only when no playlist is a reasonable home — **default**), `low` (takes the best match unless truly unrelated — most moves). Turn **up** if you see wrong guesses; turn **down** if too many videos are left unsorted. |

### Keyword rules (Tier 2) — map starter buckets to your playlists

Unlike Tier 0/1 (bound to YouTube's categories) and Tier 3 (grounded on your real
playlists), **keyword rules are inherently manual** — a rule is hand-written human
intent (*"if the title says `django`, file it under Programming"*), so there's
nothing to auto-detect. That's the trade-off: Tier 2 is the **offline, no-API-key,
fully deterministic, free** power-user layer, but you tell it what to do.

To make it usable out of the box, `setup → [3]` runs an **interactive mapper**: it
loads 9 generic starter buckets (Programming, AI & ML, Finance & Investing, Health
& Fitness, Travel, Cooking, Tech & Gadgets, Gaming, Music) from `rules.example.json`
and, showing **your** real playlists, lets you point each bucket at an existing
playlist (`#`), type a new name, keep the suggested name (Enter), or skip (`-`). It
writes a `rules.json` bound to your account (with a `y/N` guard before overwriting
an existing one). Edit `rules.json` afterward to add your own keywords/targets.

**Load-time heads-up:** because rule targets are fixed **names** (not bound to your
account), every keyword/cascade run first prints which targets don't exist yet —
either *"WILL be created on first match"* (`create_missing: true`) or *"will be
SKIPPED"* (`false`) — so a copied `rules.example.json` never surprises you.

### AI (Tier 3) — bring your own key or run local

AI is **optional and off by default**. When enabled it only ever returns one of
**your own** playlist names (or leaves the video alone), and it degrades safely:
a missing key, network error, or bad response prints one warning, disables the AI
layer for that run, and the cascade continues.

- **Local / free / private (recommended):** install [Ollama](https://ollama.com/),
  `ollama pull llama3.1`, then choose provider `ollama` in `setup`. Nothing leaves
  your machine and there's no key or cost.
- **Cloud (OpenAI / Anthropic / Gemini):** choose the provider in `setup`, then set
  the env var it names before running `sort`, e.g. in PowerShell:

  ```powershell
  $env:OPENAI_API_KEY = "sk-..."
  python youtube_cleaner.py sort --source PLxxxxxxxx --mode ai
  ```

  Classifying titles is tiny (~500 videos ≈ a few cents). The key is never written
  to disk by this tool.

**Efficient by default:** the AI layer **batches** titles (50 per request via
`ai.batch_size`), classifying a whole playlist in a handful of requests instead of
one call per video — much cheaper and faster. If a batch reply is malformed it
falls back to per-video calls automatically, so a bad response never derails the run.

**Tuning coverage (`ai.abstain`):** by default the AI files each video into its
best-fitting playlist and leaves it alone only when no playlist is a reasonable home
(`normal`). If it's guessing wrong, set `"abstain": "high"` so it moves only clear
matches. If it's leaving too many videos unsorted — common when a playlist's name is
broad but its existing examples are narrow, or when two playlists overlap — set
`"abstain": "low"` to take the best match unless the video is truly unrelated. The
active mode is printed at the start of every AI run (`[AI] recall mode: abstain=…`).

---

## Watch Later (personal userscript)

**Watch Later cannot be touched by any API** — not listing, not removing. The only
way to bulk-clear it is `watchlater-cleaner.user.js`, which automates the YouTube
web UI on your own machine.

> ⚠️ **Personal use only.** Automating YouTube's UI is against its Terms of Service
> and could put your account at risk. Removals are permanent. Do not ship this.

**Install & use:**
1. Install [Tampermonkey](https://tampermonkey.net/) or Violentmonkey.
2. Add `watchlater-cleaner.user.js`.
3. Open <https://www.youtube.com/playlist?list=WL> (or any playlist).
4. In the panel (top-right), tick any combination of three independent modes and
   press **Start** (hit **Stop** anytime; adjust the delay if YouTube throttles you):
   - **Delete oldest videos** — the N oldest, in batches from the top (sort the
     page "Date added (oldest)" first).
   - **Delete watched videos** — only those watched ≥ your % threshold (partials
     below it are kept). A one-click "Remove watched" shortcut is also provided.
   - **Delete private/deleted (unavailable) videos** — removes only rows titled
     `[Private video]` / `[Deleted video]`, the WL-side parity for the API's
     `remove-unavailable`. Rows whose title can't be read are **kept**, and this
     sweep is separate and **not** counted against the oldest-N number. It matches
     the **English** placeholder titles, so if your YouTube UI is in another
     language, switch it to English before running this sweep.

It removes items one at a time at a human-like pace, re-scanning the list each
step (so it doesn't act on stale elements). Each mode is opt-in, so nothing runs
unless you tick it, and removals are permanent (there is no undo — a deleted or
private video can't be restored).

> **Language note:** the private/deleted sweep matches YouTube's **English**
> placeholder titles (`[Private video]` / `[Deleted video]`). If your YouTube UI
> is set to another language, switch it to English before running that sweep so
> the rows are recognized.

---

## Notes & limits

- **Scope:** uses `youtube.force-ssl` (read + write). Deleting playlist items
  requires a write scope; read-only is not enough.
- **Quota is per-app, not per-user.** The default 10,000 units/day is shared
  across **all** users of this Google Cloud project. `playlistItems.delete` costs
  ~50 units and scanning a 5,000-item playlist costs ~100 list units, so a fresh
  bucket allows only **~198 deletes/day for the entire project**. Moving an item
  between playlists is `insert` (50) + `delete` (50) = **~100 units** (there is no
  atomic move). This is the biggest scaling constraint — see the strategy notes.
- **Confirmation:** `--execute` requires you to type `DELETE` before anything is
  removed. The list printed just above the prompt is exactly what gets deleted.
- **Ownership is verified** before deleting: the playlist must appear in your own
  `playlists.list(mine=True)`.
- **Safety:** items with no usable date are skipped rather than guessed; `--years`
  must be > 0 and `--max-deletes` >= 1.
- **Login is not truly one-time while the app is in "Testing".** Google expires
  refresh tokens after ~7 days for unverified/testing apps, so you'll re-auth
  weekly until the app passes OAuth verification.
- **`token.json` holds a plaintext refresh token.** It is git-ignored, but protect
  the file locally (don't share it).
- **Watch Later and History are not accessible** by any YouTube API — including
  `clean`, `autopurge`, and `remove-unavailable`. If you pass one of the system
  playlist IDs (`WL`, `HL`, `LL`, `FL`, `LM`), the tool prints an honest notice and
  makes **no** changes rather than failing with a confusing error. *Liked videos*
  are readable separately via `videos.list(myRating=like)` but can't be edited as a
  playlist. To clear Watch Later, use the browser userscript below.
- **Removing dead videos is permanent.** `remove-unavailable` deletes deleted/private
  placeholder entries and cannot be undone (the underlying video is gone or private),
  so review the dry-run — and optionally `--json` — before `--execute`.

### Unattended daily task (optional)

`daily_sort.ps1` chains the maintenance steps for a Windows Scheduled Task:
clear dead videos → **opt-in age-purge** → sort each of your configured source
playlists, each capped to stay under the daily quota and resumable if quota runs
out. It's a **template** — edit the `$SOURCES` list at the top to your own source
playlist IDs. The age-purge step is a **safe no-op** until you add an enabled
`purge` block to `config.json`, so existing setups are unaffected. Re-run `auth`
if a run logs an auth error (testing-mode tokens expire ~weekly).

---

## License

MIT — see [`LICENSE`](LICENSE). The compliant CLI is meant for use with your own
Google Cloud credentials and account within YouTube's Terms of Service. The Watch
Later userscript automates the YouTube UI and is provided for **personal use on
your own account only**; do not use it to run a hosted or commercial service.

---

## What this proves for the product

If this works end-to-end on your account, it validates the YouTube half of the
app: OAuth, playlist enumeration, ownership checks, and rule-based bulk deletion.

> **A note on AI sorting & YouTube policy:** YouTube's Developer Policies restrict
> *inferring/estimating* a video's content category via the API. Tier 3 here does
> not use the API for classification — it reads the title/channel text you already
> fetched and asks a model **you** run (local Ollama) or **you** pay for (your own
> key) to pick from **your** playlists. Coarse sorting from the API's own
> `categoryId` (Tier 0/1) and your keyword rules (Tier 2) remain the zero-cost,
> lowest-risk defaults; AI stays optional and off by default.

