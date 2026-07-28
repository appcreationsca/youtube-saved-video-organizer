// ==UserScript==
// @name         Watch Later & Playlist Cleaner (personal)
// @namespace    https://github.com/your-name/yt-saved-organizer
// @version      2.6.1
// @description  Bulk-remove videos from your YouTube "Watch Later" (or any open playlist) via the UI, oldest-first, in batches of 100, at 5,000+ scale. This is the ONLY way to clear Watch Later, since no official API can touch it.
// @match        https://www.youtube.com/playlist?list=*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

/*
 * WHY THIS EXISTS
 * ---------------
 * YouTube's "Watch Later" (WL) and "Liked" (LL) playlists are completely
 * inaccessible to the official YouTube Data API. The ONLY way to bulk-clear
 * Watch Later is to automate the logged-in web UI, which is what this does.
 *
 * IMPORTANT — READ BEFORE USING
 * -----------------------------
 * Automating the YouTube UI is against YouTube's Terms of Service and could,
 * in principle, put your Google account at risk. Strictly a PERSONAL tool that
 * YOU run on YOUR OWN session, at a human-like pace. Do NOT ship it. Removals
 * are IRREVERSIBLE.
 *
 * OLDEST-FIRST DELETION
 * ---------------------
 * There is no API/DOM date to filter by "older than N years". BUT the WL page
 * supports sorting by "Date added (oldest)". This script always removes from
 * the TOP, so:  Sort "Date added (oldest)" + remove from top = delete oldest first.
 *
 * TWO INDEPENDENT OPTIONS (v2.2)
 * ------------------------------
 *   (A) Delete the N OLDEST videos — processed in BATCHES OF 100 (500 = 5 batches).
 *   (B) Delete WATCHED videos — a SEPARATE action that is NOT counted against N.
 *       "Watched" is DEFINED BY A THRESHOLD you set (default 90%): the script
 *       reads each video's red resume-progress bar and only deletes videos
 *       watched >= your %. A 1-min-of-20 (~5%) video is therefore KEPT.
 * You may pick either one or both. If both are selected, (A) runs first for
 * exactly N, then (B) removes qualifying watched videos on top of that.
 * (A separate button also exposes YouTube's own 1-click "Remove watched",
 *  which uses Google's hidden rule and IGNORES your %.)
 *
 * Memory: it removes the loaded ~100 rows, THEN loads the next ~100, so the DOM
 * never holds more than ~100 rows — that's what lets it clear a maxed-out 5,000
 * WL without freezing the tab. A lifetime counter in localStorage makes runs
 * resumable across reloads (the new top is still the oldest remaining).
 *
 * HOW TO USE
 * ----------
 * 1. Add this script (Tampermonkey/Violentmonkey) OR just paste the whole file
 *    into the browser Console (F12) while on the playlist page — no extension needed.
 * 2. Open https://www.youtube.com/playlist?list=WL
 * 3. Sort the page: "Date added (oldest)".
 * 4. In the panel: tick the option(s), set the oldest count, click Start.
 */

(function () {
  'use strict';

  const DEFAULT_DELAY_MS = 700;   // human-like pace; raise if YouTube throttles you
  const BATCH_SIZE = 100;         // videos per batch (per user's workflow)
  const INTER_BATCH_PAUSE_MS = 1200;
  const MAX_EMPTY_SCROLLS = 4;    // give up loading more after this many idle scrolls
  const MAX_CONSEC_FAILS = 10;    // pause if the UI stops responding to removals
  const MAX_SCAN = 1500;          // watched-scan safety cap per pass (bounds DOM/memory)

  let stopRequested = false;
  let running = false;        // guards a single remove loop
  let orchestrating = false;  // guards the Start button

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const listId = new URLSearchParams(location.search).get('list') || 'unknown';
  const LS_KEY = `wlcRemoved:${listId}`;

  const lifetime = {
    get: () => parseInt(localStorage.getItem(LS_KEY) || '0', 10) || 0,
    add: (n) => localStorage.setItem(LS_KEY, String(lifetime.get() + n)),
    reset: () => localStorage.setItem(LS_KEY, '0'),
  };

  function videoRows() {
    return Array.from(document.querySelectorAll('ytd-playlist-video-renderer'));
  }

  // Watch progress as a percentage read from the red resume bar on the thumbnail.
  //   -1     = no overlay at all (never started)
  //   0..100 = how far it was watched (bar width); 0 if the overlay exists but the
  //            width can't be read (conservative: 0 stays below any positive threshold,
  //            so an unreadable video is KEPT, never deleted).
  function watchedPercent(row) {
    const ov = row.querySelector('ytd-thumbnail-overlay-resume-playback-renderer');
    if (!ov) return -1;
    const bar = ov.querySelector('#progress, [style*="width"]');
    if (bar) {
      const css = bar.getAttribute('style') || (bar.style && bar.style.cssText) || '';
      const m = /width:\s*([\d.]+)%/i.exec(css);
      if (m) return Math.max(0, Math.min(100, parseFloat(m[1])));
      try {
        const iw = bar.getBoundingClientRect().width;
        const ow = ov.getBoundingClientRect().width;
        if (ow > 0) return Math.max(0, Math.min(100, Math.round((iw / ow) * 100)));
      } catch (e) { /* ignore */ }
    }
    return 0;
  }

  function scroller() {
    return document.scrollingElement || document.documentElement;
  }

  // Scroll to the bottom to lazy-load the next batch, then back to the top so
  // removals keep happening at the top (and YouTube doesn't keep loading MORE
  // while we sit at the bottom -> bounded memory).
  async function loadNextBatch(delay) {
    const before = videoRows().length;
    scroller().scrollTo(0, scroller().scrollHeight);
    await sleep(Math.max(1000, delay));
    scroller().scrollTo(0, 0);
    await sleep(300);
    return videoRows().length - before; // >0 means new rows appeared
  }

  // Remove a single row via its "⋮" menu -> "Remove from …".
  async function removeRow(row, delay) {
    const menuBtn = row.querySelector(
      'ytd-menu-renderer button, #button.yt-icon-button, button[aria-label="Action menu"]'
    );
    if (!menuBtn) return false;
    menuBtn.click();
    await sleep(delay);

    const items = document.querySelectorAll(
      'ytd-menu-service-item-renderer, tp-yt-paper-item, yt-list-item-view-model'
    );
    // Matches "Remove from Watch later" and "Remove from <playlist name>".
    const target = Array.from(items).find((el) => /remove from /i.test(el.textContent || ''));
    if (!target) {
      document.body.click(); // close the menu so we don't get stuck
      return false;
    }
    target.click();
    await sleep(delay);
    return true;
  }

  function fmtETA(ms) {
    if (!isFinite(ms) || ms < 0) return '—';
    const s = Math.round(ms / 1000);
    const m = Math.floor(s / 60);
    if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
    return m ? `${m}m ${s % 60}s` : `${s % 60}s`;
  }

  // Core remove loop. Returns the number removed this run.
  // - watchedOnly=false + target=N  -> delete N oldest (batched).
  // - watchedOnly=true  + target=0  -> delete all watched (fallback path).
  async function removeLoop({ watchedOnly, watchedThreshold = 90, target, delay, status, progress, batched }) {
    if (running) return 0;
    running = true;

    let done = 0;
    let emptyScrolls = 0;
    let consecFails = 0;
    let curDelay = delay;
    const startedAt = Date.now();
    const totalBatches = target ? Math.ceil(target / BATCH_SIZE) : 0;

    const report = (extra) => {
      const perMs = done > 0 ? (Date.now() - startedAt) / done : 0;
      let msg = watchedOnly ? `Watched removed ${done}` : `Removed ${done}`;
      if (target) {
        const batch = done >= target ? totalBatches : Math.floor(done / BATCH_SIZE) + 1;
        const pct = Math.min(100, Math.round((done / target) * 100));
        msg += ` / ${target} (${pct}%) · batch ${batch}/${totalBatches} · ETA ${fmtETA(perMs * (target - done))}`;
      }
      msg += ` · lifetime ${lifetime.get()}`;
      if (extra) msg += ` · ${extra}`;
      status(msg);
      if (progress) progress({ done, target, watchedOnly });
    };

    while (!stopRequested) {
      if (target && done >= target) break;

      const rows = videoRows().filter((r) => (watchedOnly ? watchedPercent(r) >= watchedThreshold : true));

      if (rows.length === 0) {
        if (watchedOnly && videoRows().length >= MAX_SCAN) {
          status(`Scanned ${videoRows().length} rows; removed ${done} watched \u2265${watchedThreshold}% this pass. Reload the page and Start again to continue (progress saved, lifetime ${lifetime.get()}).`);
          break;
        }
        report('loading more…');
        const gained = await loadNextBatch(curDelay);
        if (gained <= 0) {
          if (++emptyScrolls >= MAX_EMPTY_SCROLLS) break; // genuinely empty
        } else {
          emptyScrolls = 0;
        }
        continue;
      }
      emptyScrolls = 0;

      const ok = await removeRow(rows[0], curDelay);
      if (ok) {
        done++;
        lifetime.add(1);
        consecFails = 0;
        if (curDelay > delay) curDelay = Math.max(delay, curDelay - 100); // recover pace
        report();

        // Pause between batches so the run is observable and gently paced.
        if (batched && done % BATCH_SIZE === 0 && done < target && !stopRequested) {
          status(`Batch ${done / BATCH_SIZE}/${totalBatches} complete (removed ${done}/${target}). Pausing…`);
          await sleep(INTER_BATCH_PAUSE_MS);
        }
      } else {
        consecFails++;
        if (consecFails >= MAX_CONSEC_FAILS) {
          status(`Paused after ${consecFails} failures — YouTube may be throttling. Wait, then Start again. (Removed ${done} this run.)`);
          break;
        }
        curDelay = Math.min(4000, curDelay + 400); // adaptive back-off
        report(`retry (backoff ${curDelay}ms)`);
        await sleep(curDelay);
      }
      await sleep(curDelay);
    }

    running = false;
    return done;
  }

  // Preferred watched-video removal: trigger YouTube's own "Remove watched
  // videos" playlist action (one shot, official, clears ALL watched, no
  // scrolling). Returns true if the action was requested.
  async function removeWatchedNative(delay, status) {
    // Find the playlist-level ⋮ menu (header), NOT a video row's menu.
    let menuBtn = null;
    const header = document.querySelector(
      'ytd-playlist-header-renderer, ytd-playlist-header, ytd-page-header-renderer, .metadata-buttons-wrapper'
    );
    if (header) {
      menuBtn = header.querySelector(
        'ytd-menu-renderer button, button[aria-label="Action menu"], yt-button-shape button'
      );
    }
    if (!menuBtn) {
      const headerMenu = Array.from(document.querySelectorAll('ytd-menu-renderer'))
        .find((m) => !m.closest('ytd-playlist-video-renderer'));
      if (headerMenu) menuBtn = headerMenu.querySelector('button');
    }
    if (!menuBtn) {
      status('Could not open the playlist menu for "Remove watched videos".');
      return false;
    }

    menuBtn.click();
    await sleep(delay + 200);

    const items = document.querySelectorAll(
      'ytd-menu-service-item-renderer, tp-yt-paper-item, yt-list-item-view-model'
    );
    const rw = Array.from(items).find((el) => /remove watched/i.test(el.textContent || ''));
    if (!rw) {
      document.body.click();
      status('No "Remove watched videos" item found (maybe none are watched).');
      return false;
    }
    rw.click();
    await sleep(delay + 300);

    // Confirm dialog, if YouTube shows one.
    let confirmBtn = document.querySelector(
      'yt-confirm-dialog-renderer #confirm-button, tp-yt-paper-dialog #confirm-button'
    );
    if (!confirmBtn) {
      confirmBtn = Array.from(
        document.querySelectorAll('tp-yt-paper-dialog button, yt-confirm-dialog-renderer button, yt-button-renderer button')
      ).find((b) => /remove/i.test(b.textContent || ''));
    }
    if (confirmBtn) { confirmBtn.click(); await sleep(delay + 300); }

    status('Requested YouTube "Remove watched videos" — all watched cleared.');
    return true;
  }

  // Orchestrates the user's selection: oldest (batched) and/or watched (separate).
  async function runSelected({ doOldest, oldestCount, doWatched, watchedThreshold, delay, status, progress }) {
    if (orchestrating) return;
    orchestrating = true;
    stopRequested = false;

    let oldestDone = 0;
    let watchedDone = 0;
    try {
      if (doOldest && oldestCount > 0) {
        status(`Deleting ${oldestCount} oldest in batches of ${BATCH_SIZE}…`);
        oldestDone = await removeLoop({ watchedOnly: false, target: oldestCount, delay, status, progress, batched: true });
      }

      if (doWatched && !stopRequested) {
        status(`Now deleting watched videos (only \u2265${watchedThreshold}% watched) — separate, not counted…`);
        watchedDone = await removeLoop({ watchedOnly: true, watchedThreshold, target: 0, delay, status, progress, batched: false });
      }
    } finally {
      orchestrating = false;
    }

    const bits = [];
    if (doOldest) bits.push(`${oldestDone} oldest`);
    if (doWatched) bits.push(`${watchedDone} watched (\u2265${watchedThreshold}%)`);
    status(`All done — ${bits.join(' + ') || 'nothing selected'}. ${stopRequested ? '(stopped) ' : ''}Lifetime: ${lifetime.get()}.`);
  }

  // ---- UI panel -----------------------------------------------------------

  function buildPanel() {
    if (document.getElementById('wl-cleaner-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'wl-cleaner-panel';
    panel.style.cssText = [
      'position:fixed', 'top:80px', 'right:20px', 'z-index:99999',
      'background:#212121', 'color:#fff', 'padding:14px', 'border-radius:10px',
      'font:13px/1.4 Roboto, Arial, sans-serif', 'width:262px',
      'box-shadow:0 4px 16px rgba(0,0,0,.5)',
    ].join(';');

    const isWL = listId === 'WL';
    // Build the panel with DOM APIs (YouTube enforces Trusted Types, which
    // blocks assigning a raw HTML string to innerHTML).
    const el = (tag, style, opts) => {
      const n = document.createElement(tag);
      if (style) n.style.cssText = style;
      if (opts) {
        if (opts.id) n.id = opts.id;
        if (opts.type) n.type = opts.type;
        if (opts.text != null) n.textContent = opts.text;
        if (opts.checked) n.checked = true;
        if (opts.attrs) for (const k in opts.attrs) n.setAttribute(k, opts.attrs[k]);
        if (opts.kids) opts.kids.forEach((k) => {
          if (k) n.appendChild(typeof k === 'string' ? document.createTextNode(k) : k);
        });
      }
      return n;
    };
    const b = (t) => el('b', '', { text: t });
    const br = () => document.createElement('br');
    const IN = 'background:#333;color:#fff;border:1px solid #555;border-radius:4px;padding:2px 4px';

    panel.appendChild(el('div', 'font-weight:600;margin-bottom:6px;cursor:move;user-select:none;display:flex;justify-content:space-between;align-items:center;gap:8px', {
      id: 'wlc-titlebar',
      attrs: { title: 'Drag to move \u00b7 double-click to reset position' },
      kids: [
        el('span', 'display:flex;align-items:baseline;gap:8px;min-width:0', {
          kids: [
            el('span', 'white-space:nowrap', { text: '\uD83E\uDDF9 Playlist Cleaner v2.6.1' }),
            el('span', 'font-size:11px;color:#69f0ae;font-weight:600;white-space:nowrap', { id: 'wlc-tbprog', text: '' }),
          ],
        }),
        el('span', 'display:flex;align-items:center;gap:8px', {
          kids: [
            el('span', 'color:#607d8b;font-size:13px;letter-spacing:1px', { text: '\u2807' }),
            el('button', 'cursor:pointer;background:#37474f;color:#cfd8dc;border:1px solid #555;border-radius:4px;width:22px;height:20px;font-size:14px;line-height:1;padding:0', {
              id: 'wlc-min', text: '\u2212', attrs: { title: 'Minimize / expand' },
            }),
          ],
        }),
      ],
    }));
    panel.appendChild(el('div', 'font-size:11px;color:#ff8a80;margin-bottom:8px', { text: 'Personal use only. Removals are permanent.' }));
    panel.appendChild(el('div', 'font-size:11px;background:#33372e;color:#ffe082;border-radius:6px;padding:6px 8px;margin-bottom:10px', {
      kids: ['\u2460 Sort the page to ', b('Date added (oldest)'), ' first.', br(), '\u2461 Removals go top-down = ', b('oldest first'), '.'],
    }));

    const delayInput = el('input', 'width:70px;' + IN, { id: 'wlc-delay', type: 'number', attrs: { min: '300' } });
    panel.appendChild(el('label', 'display:flex;align-items:center;gap:6px;margin-bottom:10px', { kids: ['Delay (ms): ', delayInput] }));

    const optOldest = el('input', '', { id: 'wlc-opt-oldest', type: 'checkbox', checked: true });
    const countInput = el('input', 'width:74px;' + IN, { id: 'wlc-count', type: 'number', attrs: { min: '0', step: '100' } });
    panel.appendChild(el('div', 'border:1px solid #444;border-radius:7px;padding:8px;margin-bottom:8px', {
      kids: [
        el('label', 'display:flex;align-items:center;gap:7px;margin-bottom:4px;cursor:pointer', {
          kids: [optOldest, el('span', 'font-weight:600', { text: 'Delete oldest videos' })],
        }),
        el('label', 'display:flex;align-items:center;gap:6px;margin-left:22px', { kids: ['How many:', countInput] }),
        el('div', 'font-size:10.5px;color:#90a4ae;margin:3px 0 0 22px', { id: 'wlc-batchhint', text: '= 5 batches of 100' }),
      ],
    }));

    const optWatched = el('input', '', { id: 'wlc-opt-watched', type: 'checkbox' });
    const thrInput = el('input', 'width:56px;' + IN, { id: 'wlc-threshold', type: 'number', attrs: { min: '1', max: '100' } });
    const nativeBtn = el('button', 'width:calc(100% - 22px);margin:7px 0 0 22px;padding:5px;cursor:pointer;background:#37474f;color:#cfd8dc;border:1px solid #555;border-radius:5px;font-size:10.5px', {
      id: 'wlc-native', text: 'or: YouTube 1-click \u201CRemove watched\u201D (ignores %)',
    });
    panel.appendChild(el('div', 'border:1px solid #444;border-radius:7px;padding:8px;margin-bottom:10px', {
      kids: [
        el('label', 'display:flex;align-items:center;gap:7px;cursor:pointer', {
          kids: [optWatched, el('span', 'font-weight:600', { text: 'Delete watched videos' })],
        }),
        el('label', 'display:flex;align-items:center;gap:6px;margin:6px 0 0 22px', { kids: ['only if watched \u2265 ', thrInput, ' %'] }),
        el('div', 'font-size:10.5px;color:#90a4ae;margin:4px 0 0 22px', {
          kids: ['Separate action \u2014 ', b('NOT'), ' counted above. Reads each video\u2019s progress bar; partials below your % are ', b('kept'), '.'],
        }),
        nativeBtn,
      ],
    }));

    panel.appendChild(el('button', 'width:100%;margin:2px 0;padding:8px;cursor:pointer;background:#c62828;color:#fff;border:none;border-radius:5px;font-weight:600', { id: 'wlc-start', text: 'Start' }));
    panel.appendChild(el('button', 'width:100%;margin:4px 0;padding:6px;cursor:pointer;background:#616161;color:#fff;border:none;border-radius:5px', { id: 'wlc-stop', text: 'Stop' }));
    panel.appendChild(el('button', 'width:100%;margin:4px 0;padding:5px;cursor:pointer;background:#455a64;color:#fff;border:none;border-radius:5px;font-size:12px', { id: 'wlc-loaded', text: 'Count loaded' }));

    const lifeSpan = el('span', 'font-size:11px;color:#90a4ae', { kids: ['Lifetime removed: ', el('b', '', { id: 'wlc-life', text: '0' })] });
    const resetBtn = el('button', 'font-size:10px;cursor:pointer;background:transparent;color:#90a4ae;border:1px solid #555;border-radius:4px;padding:1px 6px', { id: 'wlc-reset', text: 'reset' });
    panel.appendChild(el('div', 'display:flex;justify-content:space-between;align-items:center;margin-top:6px', { kids: [lifeSpan, resetBtn] }));

    panel.appendChild(el('div', 'margin-top:8px;font-size:12px;color:#b0bec5', { id: 'wlc-status', text: 'Ready' + (isWL ? ' \u2014 Watch Later' : '') + '.' }));

    document.body.appendChild(panel);

    // Draggable: grab the title bar, move the whole panel. Position persists
    // across the page reloads that batching requires (localStorage.wlcPos).
    (function makeDraggable() {
      const bar = panel.querySelector('#wlc-titlebar');
      const DEFAULT = { top: 80, right: 20 };
      const applyPos = (p) => {
        if (!p) return;
        panel.style.top = p.top + 'px';
        panel.style.left = p.left + 'px';
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
      };
      const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
      const savePos = (p) => { try { localStorage.setItem('wlcPos', JSON.stringify(p)); } catch (e) {} };
      try {
        const saved = JSON.parse(localStorage.getItem('wlcPos'));
        if (saved && typeof saved.left === 'number') {
          const r = panel.getBoundingClientRect();
          saved.left = clamp(saved.left, 0, innerWidth - r.width);
          saved.top = clamp(saved.top, 0, innerHeight - 40);
          applyPos(saved);
        }
      } catch (e) {}

      let dragging = false, offX = 0, offY = 0;
      bar.addEventListener('mousedown', (e) => {
        dragging = true;
        const r = panel.getBoundingClientRect();
        offX = e.clientX - r.left;
        offY = e.clientY - r.top;
        panel.style.transition = 'none';
        document.body.style.userSelect = 'none';
        e.preventDefault();
      });
      window.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const w = panel.getBoundingClientRect().width;
        const left = clamp(e.clientX - offX, 0, innerWidth - w);
        const top = clamp(e.clientY - offY, 0, innerHeight - 40);
        panel.style.left = left + 'px';
        panel.style.top = top + 'px';
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
      });
      window.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        document.body.style.userSelect = '';
        const r = panel.getBoundingClientRect();
        savePos({ left: Math.round(r.left), top: Math.round(r.top) });
      });
      // Double-click the title bar snaps it back to the default corner.
      bar.addEventListener('dblclick', () => {
        panel.style.left = 'auto';
        panel.style.right = DEFAULT.right + 'px';
        panel.style.top = DEFAULT.top + 'px';
        panel.style.bottom = 'auto';
        try { localStorage.removeItem('wlcPos'); } catch (e) {}
      });
    })();

    // Minimize / expand: collapse to just the title bar. State persists so the
    // panel stays minimized across the reloads batching requires.
    (function makeCollapsible() {
      const bar = panel.querySelector('#wlc-titlebar');
      const minBtn = panel.querySelector('#wlc-min');
      const bodyKids = Array.from(panel.children).filter((c) => c !== bar);
      const apply = (collapsed) => {
        bodyKids.forEach((c) => { c.style.display = collapsed ? 'none' : ''; });
        bar.style.marginBottom = collapsed ? '0' : '6px';
        minBtn.textContent = collapsed ? '\u002B' : '\u2212'; // + when collapsed, \u2212 when open
      };
      // don't start a drag when clicking the button
      minBtn.addEventListener('mousedown', (e) => e.stopPropagation());
      let collapsed = false;
      try { collapsed = localStorage.getItem('wlcCollapsed') === '1'; } catch (e) {}
      apply(collapsed);
      minBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        collapsed = !collapsed;
        apply(collapsed);
        try { localStorage.setItem('wlcCollapsed', collapsed ? '1' : '0'); } catch (e2) {}
      });
    })();

    const $ = (sel) => panel.querySelector(sel);
    const status = (msg) => { $('#wlc-status').textContent = msg; };
    const refreshLife = () => { $('#wlc-life').textContent = lifetime.get(); };
    // Live counter shown in the title bar — visible even when minimized.
    const prog = (p) => {
      const t = $('#wlc-tbprog');
      if (!t || !p || p.done == null) { if (t) t.textContent = ''; return; }
      if (p.watchedOnly) t.textContent = `\u25B6 watched ${p.done}`;
      else if (p.target) t.textContent = `\u25B6 ${p.done}/${p.target} \u00b7 ${Math.min(100, Math.round((p.done / p.target) * 100))}%`;
      else t.textContent = `\u25B6 ${p.done}`;
    };

    // Restore saved settings.
    $('#wlc-delay').value = localStorage.getItem('wlcDelay') || DEFAULT_DELAY_MS;
    $('#wlc-count').value = localStorage.getItem('wlcCount') || '500';
    $('#wlc-threshold').value = localStorage.getItem('wlcThreshold') || '90';
    refreshLife();

    const delay = () => {
      const v = Math.max(300, parseInt($('#wlc-delay').value, 10) || DEFAULT_DELAY_MS);
      localStorage.setItem('wlcDelay', String(v));
      return v;
    };
    const oldestCount = () => {
      const v = Math.max(0, parseInt($('#wlc-count').value, 10) || 0);
      localStorage.setItem('wlcCount', String(v));
      return v;
    };
    const watchedThreshold = () => {
      const v = Math.max(1, Math.min(100, parseInt($('#wlc-threshold').value, 10) || 90));
      localStorage.setItem('wlcThreshold', String(v));
      return v;
    };

    const updateHint = () => {
      const n = oldestCount();
      const batches = Math.ceil(n / BATCH_SIZE);
      const rem = n % BATCH_SIZE;
      $('#wlc-batchhint').textContent = n === 0
        ? 'enter a number (multiples of 100 are cleanest)'
        : `= ${batches} batch${batches === 1 ? '' : 'es'} of 100${rem ? ` (last batch ${rem})` : ''}`;
    };
    $('#wlc-count').oninput = updateHint;
    updateHint();

    $('#wlc-start').onclick = () => {
      const doOldest = $('#wlc-opt-oldest').checked;
      const doWatched = $('#wlc-opt-watched').checked;
      const n = oldestCount();
      const thr = watchedThreshold();

      if (!doOldest && !doWatched) { status('Select at least one option.'); return; }
      if (doOldest && n <= 0) { status('Enter how many oldest videos to delete.'); return; }

      const lines = ['This cannot be undone.', ''];
      if (doOldest) {
        const batches = Math.ceil(n / BATCH_SIZE);
        lines.push(`• Delete the ${n} OLDEST videos — ${batches} batch(es) of ${BATCH_SIZE}, from the top.`);
        lines.push('  (Make sure the page is sorted "Date added (oldest)".)');
      }
      if (doWatched) {
        lines.push(`• Delete WATCHED videos (only those watched ≥ ${thr}%) — separate action, NOT counted in the ${doOldest ? n : 'oldest'} number.`);
      }
      lines.push('', 'Proceed?');

      if (confirm(lines.join('\n'))) {
        $('#wlc-tbprog').textContent = '\u25B6 starting\u2026';
        runSelected({ doOldest, oldestCount: n, doWatched, watchedThreshold: thr, delay: delay(), status, progress: prog })
          .then(() => { $('#wlc-tbprog').textContent = stopRequested ? '\u23F9 stopped' : '\u2713 done'; });
      }
    };

    $('#wlc-native').onclick = async () => {
      if (orchestrating) { status('Already running — Stop first.'); return; }
      if (!confirm('Use YouTube\'s built-in "Remove watched videos"?\n\nThis ignores your % threshold and uses Google\'s own hidden rule (any progress may count). This cannot be undone. Proceed?')) return;
      orchestrating = true; stopRequested = false;
      try {
        const ok = await removeWatchedNative(delay(), status);
        if (!ok) status('Native "Remove watched videos" not available on this page.');
      } finally { orchestrating = false; }
    };

    $('#wlc-stop').onclick = () => { stopRequested = true; status('Stopping…'); };
    $('#wlc-loaded').onclick = () => {
      const rows = videoRows();
      const total = rows.length;
      const pcts = rows.map(watchedPercent).filter((p) => p >= 0);
      const started = pcts.length;
      const thr = watchedThreshold();
      const atThr = pcts.filter((p) => p >= thr).length;
      const readable = pcts.filter((p) => p > 0).length;
      status(`${total} rows loaded (${started} have progress; ${readable} with a readable %; ${atThr} are ≥ ${thr}%). Large lists load ~100 at a time.`);
    };
    $('#wlc-reset').onclick = () => {
      if (confirm('Reset the lifetime-removed counter to 0?')) { lifetime.reset(); refreshLife(); }
    };

    setInterval(refreshLife, 1500);
  }

  // YouTube is a single-page app; (re)build the panel on playlist pages.
  function maybeBuild() {
    if (location.pathname === '/playlist') buildPanel();
  }
  maybeBuild();
  window.addEventListener('yt-navigate-finish', maybeBuild);
  setTimeout(maybeBuild, 2000);
})();
