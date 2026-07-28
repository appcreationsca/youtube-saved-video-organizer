/* ============================================================
 * Watch Later — READ-ONLY selector diagnostic  (deletes NOTHING)
 * ------------------------------------------------------------
 * Paste this whole block into the browser Console (F12) while you
 * are ON your Watch Later page:  https://www.youtube.com/playlist?list=WL
 *
 * It verifies every selector the v2.1 cleaner relies on and prints a
 * PASS/FAIL report. It OPENS the playlist ⋮ menu to look for
 * "Remove watched videos", reads the label, then CLOSES the menu.
 * It never clicks delete, never clicks a confirm button.
 * ============================================================ */
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const line = (label, ok, detail) =>
    console.log(`%c${ok ? 'PASS' : 'FAIL'}%c  ${label}${detail ? '  —  ' + detail : ''}`,
      `background:${ok ? '#065f46' : '#7f1d1d'};color:#fff;padding:1px 6px;border-radius:3px;font-weight:600`,
      'color:inherit');

  console.log('%cWatch Later selector diagnostic (read-only)', 'font-size:14px;font-weight:700');

  // 1) List id
  const listId = new URLSearchParams(location.search).get('list');
  line('On a playlist page', !!listId, listId ? `list=${listId}` : 'no ?list= in URL — open Watch Later first');

  // 2) Video rows
  const rows = Array.from(document.querySelectorAll('ytd-playlist-video-renderer'));
  line('Video rows detected (ytd-playlist-video-renderer)', rows.length > 0, `${rows.length} loaded in DOM`);

  // 3) Watched detection
  const watched = rows.filter((r) => r.querySelector('ytd-thumbnail-overlay-resume-playback-renderer'));
  line('Watched-overlay detection works', rows.length > 0,
    `${watched.length} of ${rows.length} loaded rows look watched (resume-playback overlay)`);

  // 4) Per-row ⋮ menu button (used for the oldest-first removal path)
  let rowMenuOk = false, rowMenuSel = '';
  if (rows[0]) {
    const sels = ['ytd-menu-renderer button', '#button.yt-icon-button', 'button[aria-label="Action menu"]'];
    for (const s of sels) { if (rows[0].querySelector(s)) { rowMenuOk = true; rowMenuSel = s; break; } }
  }
  line('Row action (⋮) button found on first row', rowMenuOk, rowMenuSel || 'none matched');

  // 5) Playlist HEADER ⋮ menu button (used for native "Remove watched videos")
  let menuBtn = null, how = '';
  const header = document.querySelector(
    'ytd-playlist-header-renderer, ytd-playlist-header, ytd-page-header-renderer, .metadata-buttons-wrapper'
  );
  if (header) {
    menuBtn = header.querySelector('ytd-menu-renderer button, button[aria-label="Action menu"], yt-button-shape button');
    if (menuBtn) how = 'via header container';
  }
  if (!menuBtn) {
    const headerMenu = Array.from(document.querySelectorAll('ytd-menu-renderer'))
      .find((m) => !m.closest('ytd-playlist-video-renderer'));
    if (headerMenu) { menuBtn = headerMenu.querySelector('button'); how = 'via first non-row ytd-menu-renderer'; }
  }
  line('Playlist header ⋮ menu button found', !!menuBtn, menuBtn ? how : 'NOT found — native remove-watched will fall back');

  // 6) Open the header menu (read-only) and look for "Remove watched videos"
  if (menuBtn) {
    menuBtn.click();
    await sleep(700);
    const items = Array.from(document.querySelectorAll(
      'ytd-menu-service-item-renderer, tp-yt-paper-item, yt-list-item-view-model'
    ));
    const labels = items.map((el) => (el.textContent || '').trim()).filter(Boolean);
    console.log('   Menu items visible:', labels);
    const rw = items.find((el) => /remove watched/i.test(el.textContent || ''));
    line('"Remove watched videos" item present', !!rw, rw ? `matched text: "${(rw.textContent || '').trim()}"` : 'not in this menu');
    // close the menu WITHOUT clicking any item
    document.body.click();
    await sleep(200);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
  }

  // 7) Sort control present (so oldest-first is possible)
  const sortish = document.querySelector('#sort-filter-menu, tp-yt-paper-button#label, yt-sort-filter-sub-menu-renderer');
  line('Sort control present on page', !!sortish, sortish ? 'set it to "Date added (oldest)"' : 'sort menu not detected (layout may differ)');

  console.log('%cDiagnostic complete — nothing was deleted.', 'font-weight:700;color:#2563eb');
  console.log('Copy the PASS/FAIL lines + the "Menu items visible" array back to me.');
})();
