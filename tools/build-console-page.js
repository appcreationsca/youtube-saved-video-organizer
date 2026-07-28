#!/usr/bin/env node
/*
 * build-console-page.js — generate the offline "console-paste" delivery page.
 *
 * WHY
 * ---
 * The Watch Later userscript (`watchlater-cleaner.user.js`) is the only way to
 * clean Watch Later, since no official API can touch it. Most users install it
 * via Tampermonkey/Violentmonkey, but some just want to paste it into the
 * browser Console once and be done. This generator produces a self-contained
 * HTML page — `watchlater-console.html` — with a big "Copy script" button and
 * step-by-step instructions, so a one-time user never touches a file manager or
 * an extension store.
 *
 * SINGLE SOURCE OF TRUTH
 * ----------------------
 * The script text is read verbatim from the .user.js — never hand-duplicated.
 * The `// ==UserScript== ... // ==/UserScript==` metadata block is stripped
 * (the Console does not need @grant/@match), leaving the plain IIFE, which
 * pastes cleanly because the script is `@grant none` (localStorage + DOM only).
 *
 * SAFETY / OFFLINE
 * ----------------
 * - The script is embedded as DATA, injected as the .value of a <textarea> via a
 *   JSON-escaped string. It is NEVER placed as live HTML and NEVER executes when
 *   the page is opened — opening the page shows the copy UI, it does not run the
 *   cleaner.
 * - The page makes ZERO network requests: a system-font stack, no CDN, no fonts,
 *   no analytics. Nothing leaves the browser.
 *
 * USAGE
 * -----
 *   node tools/build-console-page.js
 *   node tools/build-console-page.js watchlater-cleaner.user.js watchlater-console.html
 *
 * The generated HTML only contains the shipped script (no user data) but is a
 * build artifact, so it is .gitignored; run this to (re)create it.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const srcPath = process.argv[2] || path.join(__dirname, '..', 'watchlater-cleaner.user.js');
const outPath = process.argv[3] || path.join(__dirname, '..', 'watchlater-console.html');

let raw;
try {
  raw = fs.readFileSync(srcPath, 'utf8');
} catch (e) {
  console.error('Could not read source script: ' + srcPath);
  console.error(e.message);
  process.exit(1);
}

// Strip the // ==UserScript== ... // ==/UserScript== metadata block (Console
// does not need it). Match at start-of-line to avoid touching the prose that
// mentions those markers. If not found, fall back to the whole file.
const metaRe = /^\/\/ ==UserScript==[\s\S]*?^\/\/ ==\/UserScript==\r?\n/m;
let body = raw.replace(metaRe, '');
// Record the version for the page header (from the stripped block).
const verMatch = raw.match(/^\/\/ @version\s+(.+)$/m);
const version = verMatch ? verMatch[1].trim() : '';
body = body.replace(/^\s+/, '');

// JSON.stringify safely escapes quotes, backslashes and control chars so the
// script can be assigned as a JS string with no way to break out. We additionally
// neutralise "</script" (case-insensitive) so the string literal cannot close the
// surrounding <script> element, and escape the line/paragraph separators that are
// valid in JSON but illegal in JS string literals.
const scriptLiteral = JSON.stringify(body)
  .replace(/<\/script/gi, '<\\/script')
  .replace(/\u2028/g, '\\u2028')
  .replace(/\u2029/g, '\\u2029');

const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watch Later Cleaner — console paste${version ? ' (v' + version + ')' : ''}</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    margin: 0; padding: 24px; line-height: 1.5;
    color: #1a1a1a; background: #f6f7f9;
  }
  main { max-width: 860px; margin: 0 auto; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #555; margin: 0 0 20px; font-size: 14px; }
  .card { background: #fff; border: 1px solid #e2e4e8; border-radius: 10px; padding: 18px 20px; margin: 0 0 18px; }
  .privacy { background: #eef7ee; border-color: #cfe6cf; font-size: 13px; color: #24631f; }
  ol { padding-left: 22px; margin: 8px 0 0; }
  li { margin: 6px 0; }
  code, kbd { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  kbd { background: #eceef1; border: 1px solid #d4d7dc; border-bottom-width: 2px; border-radius: 4px; padding: 1px 6px; font-size: 12px; }
  button {
    font: inherit; font-weight: 600; cursor: pointer;
    background: #cc0000; color: #fff; border: 0; border-radius: 8px;
    padding: 11px 20px; font-size: 15px;
  }
  button:hover { background: #a30000; }
  #copied { margin-left: 12px; color: #24631f; font-weight: 600; font-size: 14px; visibility: hidden; }
  #copied.show { visibility: visible; }
  textarea {
    width: 100%; min-height: 220px; margin-top: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; line-height: 1.4; white-space: pre; overflow: auto;
    border: 1px solid #d4d7dc; border-radius: 8px; padding: 12px; background: #fbfbfc; color: #222;
  }
  .warn { color: #8a5300; font-size: 13px; }
  .muted { color: #666; font-size: 13px; }
</style>
</head>
<body>
<main>
  <h1>Watch Later Cleaner${version ? ' <span class="muted">v' + version + '</span>' : ''}</h1>
  <p class="sub">One-time console paste — no install required.</p>

  <div class="card privacy">
    <strong>Runs entirely in your browser.</strong> This page makes no network
    requests and nothing you do here leaves your machine. The script below is
    shown as text for you to copy — opening this page does <em>not</em> run it.
  </div>

  <div class="card">
    <button id="copy" type="button">Copy script</button>
    <span id="copied">Copied ✓</span>
    <p class="muted" style="margin:12px 0 0;">Prefer a permanent install? Add
      <code>watchlater-cleaner.user.js</code> to Tampermonkey/Violentmonkey instead —
      same three modes, installed once.</p>
  </div>

  <div class="card">
    <h1 style="font-size:16px;margin:0 0 6px;">How to run it once</h1>
    <ol>
      <li>Open your <strong>Watch Later</strong> playlist (or any playlist page).</li>
      <li>Set the list sort to <strong>“Date added (oldest)”</strong> so oldest-first removal works.</li>
      <li>Press <kbd>F12</kbd> (or <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>J</kbd>) and open the <strong>Console</strong> tab.</li>
      <li>First time only: the console may require you to type <code>allow pasting</code> and press <kbd>Enter</kbd>.</li>
      <li>Click <strong>Copy script</strong> above, click into the console, paste (<kbd>Ctrl</kbd>+<kbd>V</kbd>), and press <kbd>Enter</kbd>.</li>
      <li>Use the on-page panel that appears (top-right) to pick a mode and run it.</li>
    </ol>
    <p class="warn" style="margin:12px 0 0;">Removals are permanent — there is no undo.
      Re-pasting is safe: it replaces the panel instead of stacking a second one.</p>
    <p class="muted" style="margin:8px 0 0;">Bookmarklets are not supported — YouTube’s
      Content-Security-Policy blocks <code>javascript:</code> URLs. Console paste (or the
      extension) is the way.</p>
  </div>

  <div class="card">
    <p class="muted" style="margin:0 0 4px;">The script (read-only — copy it, don’t edit here):</p>
    <textarea id="src" readonly spellcheck="false" aria-label="Watch Later cleaner script"></textarea>
  </div>
</main>

<script>
  // The script text is DATA, not code: assigned as a string and placed into a
  // <textarea> value. It never runs on this page.
  var SCRIPT = ${scriptLiteral};
  var ta = document.getElementById('src');
  ta.value = SCRIPT;

  var copied = document.getElementById('copied');
  function flash() {
    copied.classList.add('show');
    setTimeout(function () { copied.classList.remove('show'); }, 1600);
  }
  document.getElementById('copy').addEventListener('click', function () {
    // Clipboard API where available; fall back to selecting the textarea.
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(SCRIPT).then(flash, selectFallback);
    } else {
      selectFallback();
    }
  });
  function selectFallback() {
    ta.focus();
    ta.select();
    try { document.execCommand('copy'); flash(); } catch (e) {}
  }
</script>
</body>
</html>
`;

fs.writeFileSync(outPath, html, 'utf8');
console.log('Wrote ' + outPath + ' (' + html.length + ' bytes' + (version ? ', script v' + version : '') + ').');
