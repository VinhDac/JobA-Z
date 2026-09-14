/* The runtime bridge: the machine pushes, the screen redraws. No libraries.
 *
 * The contract with the HTML — a view only has to set the right attributes,
 * and needs to know nothing more:
 *
 *   [data-journal="search"]   the journal frame, filtered by stream ("" = all)
 *   [data-progress="search"]  the progress frame, filtered by stream
 *   [data-state]              where running / paused / waiting is shown
 *   [data-act="run"|"pause"]  the master buttons
 *   [data-nav]                the sidebar collapse button
 *   [data-tags]               a tag box: type + Enter to add, × to remove
 *   [data-post]               a button calling a background job; [data-arg] is
 *                             its parameter
 *   [data-settings]           opens the right-hand panel; the value is the URL
 *                             of the HTML fragment to load
 *   [data-appset]             opens the whole-app Settings box (mid-screen)
 *   [data-widget]             one widget; [data-expand] inside is its enlarge
 *                             button
 *
 * No polling: one SSE connection is opened and left alone. Running 24/7 and
 * asking once a second is 86,400 requests a day, mostly answering "nothing
 * new".
 */
(() => {
  'use strict';

  const MAX_LINES = 200;          // a DOM ceiling — running 24/7 must not bloat
  const $ = (sel, root) => (root || document).querySelectorAll(sel);

  // ---------------------------------------------------------------- journal
  const timeOf = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toTimeString().slice(0, 8);
  };

  // Where the real SCROLL frame is. Journal lines live inside .journal, but
  // the thing with a scrollbar is the .jfeed around it — set scrollTop on the
  // wrong element and nothing happens, with no error to trace either. Stops at
  // [data-widget] so it never climbs out to the whole page.
  function scroller(el) {
    for (let n = el; n; n = n.parentElement) {
      const how = getComputedStyle(n).overflowY;
      if (how === 'auto' || how === 'scroll') return n;
      if (n.matches('[data-widget]')) return null;
    }
    return null;
  }

  const STICK = 24;               // within this many px of the top = following the newest

  function addLine(box, ev) {
    const want = box.dataset.journal;
    if (want && want !== ev.stream) return;

    const row = document.createElement('div');
    row.className = 'jline ' + (ev.level || 'info');
    row.innerHTML =
      '<span class=jtime></span>' +
      (want ? '' : '<span class=jstream></span>') +
      '<span class=jtext></span>';
    row.querySelector('.jtime').textContent = timeOf(ev.at);
    if (!want) row.querySelector('.jstream').textContent = ev.stream;
    row.querySelector('.jtext').textContent = ev.text;

    // A new line goes to THE TOP. Inserting above what is being read leaves
    // scrollTop unchanged, which means every new line pushes the view one
    // notch further down — the longer it runs the further it drifts from the
    // newest line, until the newest line is off screen. Exactly what was just
    // seen: an apply run in progress while the journal sat on old lines.
    const sc = scroller(box);
    const dang_bam = !sc || sc.scrollTop <= STICK;
    box.insertBefore(row, box.firstChild);
    while (box.childElementCount > MAX_LINES) box.removeChild(box.lastChild);
    if (!sc) return;
    if (dang_bam) sc.scrollTop = 0;              // follow the newest line
    else sc.scrollTop += row.offsetHeight;       // reading an old line -> keep the place
  }

  const journal = (ev) => $('[data-journal]').forEach((b) => addLine(b, ev));

  // -------------------------------------------------------------- progress
  function drawProgress(box, all) {
    const want = box.dataset.progress;
    const rows = Object.entries(all).filter(([s]) => !want || s === want);
    if (!rows.length) { box.innerHTML = '<div class=pidle>nothing is running</div>'; return; }

    box.innerHTML = rows.map(([stream, p]) => {
      const width = p.total ? p.percent : 100;
      // The "time left" line is only built when there IS a figure. Built
      // up front and left empty it still takes space, and the bar jumps up
      // and down every time the machine changes job.
      return '<div class="prow' + (p.total ? '' : ' spin') + '">' +
             '<div class=phead><b></b><span></span></div>' +
             '<div class=ptrack><i style="width:' + width + '%"></i></div>' +
             (p.eta_text ? '<div class=peta></div>' : '') + '</div>';
    }).join('');

    // Text is set with textContent, NEVER concatenated into an HTML string:
    // source names and posting titles are scraped data, and joining them
    // straight into innerHTML opens the door to foreign tags.
    box.querySelectorAll('.prow').forEach((el, i) => {
      const [stream, p] = rows[i];
      el.querySelector('b').textContent = want ? p.what : stream + ' — ' + p.what;
      el.querySelector('span').textContent = p.total ? p.done + '/' + p.total : '';
      const eta = el.querySelector('.peta');
      // The wording is computed BY THE SERVER (journal.remain_text) — the
      // journal line and this bar have to state the same figure, so there is
      // only one place that formats it.
      if (eta) eta.textContent = p.eta_text + ' left';
    });
  }

  const progress = (all) => $('[data-progress]').forEach((b) => drawProgress(b, all));

  // ------------------------------------------------------------------ state
  // 'paused' on a freshly opened app reads as something being broken. Say
  // outright that THE WATCH STATION is off, and that the Start session button
  // on the Overview tab is where it goes on.
  //
  // "Watch station", not "auto-scan": the background loop now runs THE WHOLE
  // line (Search → Make CV → Manage mail), not just a scan. Call it
  // "auto-scan" and the user turns it off to stop scanning, losing the other
  // two stages without knowing it.
  function label(state, mins) {
    if (state === 'running') return 'session running';
    if (state === 'paused') return 'watch station: OFF';
    return mins > 0 ? 'on watch · next round in ' + mins + ' min' : 'on watch';
  }

  // The most recent job, shown on the app's bottom status bar. Stored
  // nowhere — this is NEWS, not state; a new line simply replaces the old.
  function setLastMessage(text) {
    if (!text) return;
    $('[data-lastmsg]').forEach((el) => { el.textContent = text; });
  }

  function setState(state, mins) {
    document.body.dataset.run = state;
    $('[data-state]').forEach((el) => { el.textContent = label(state, mins); });
    $('[data-act="pause"]').forEach((b) => {
      b.textContent = state === 'paused'
        ? 'Start the watch station' : 'Stop the watch station';
      b.title = state === 'paused'
        ? 'Run the whole line on schedule. The choice is remembered next time the app opens.'
        : 'Stop running on schedule. The manual buttons still work.';
    });
    $('[data-act="run"]').forEach((b) => { b.disabled = state === 'running'; });

    // A STAGE's run button (Search…). The idle wording is computed by the
    // server from the situation — Start / Resume / Update — and sits ready in
    // data-run. While it runs there is only one right word, and that is a
    // temporary state, so the browser handles it and the server never has to
    // guess what the screen is showing.
    $('[data-post="/api/stage/start"]').forEach((b) => {
      const ranh = b.dataset.run || b.textContent;
      b.disabled = state === 'running';
      b.textContent = state === 'running' ? 'Scanning…' : ranh;
    });
  }

  // ------------------------------------------------------------ connection
  // Reload the page, UNLESS doing so would steal work the user is in the
  // middle of.
  //
  // Three things count as "in the middle of", the third newly added: a detail
  // row being OPEN. The Track table opens a row to read an email; a run
  // finishes, the page jumps, the row slams shut, and the reader loses their
  // place with no idea why.
  //
  // A deferral has to be REMEMBERED, never swallowed: `choLamMoi` keeps the
  // intent, and the next time the user closes the row (or leaves the field)
  // it redraws at once. Drop it instead and the page freezes forever —
  // exactly the silent kind of failure.
  let choLamMoi = false;

  function dangBan() {
    const here = document.activeElement;
    if (here && here.matches('input, textarea, select')) return true;  // typing
    const sheet = document.querySelector('[data-sheet]');
    if (sheet && !sheet.hidden) return true;                           // a menu is open
    if (document.querySelector('main details[open]')) return true;      // a row is open
    return false;
  }

  function refreshIfIdle() {
    if (dangBan()) { choLamMoi = true; return; }
    location.reload();
  }

  // Just finished what was in progress -> pay back the deferred redraw.
  document.addEventListener('toggle', () => {
    if (choLamMoi && !dangBan()) location.reload();
  }, true);
  document.addEventListener('focusout', () => {
    setTimeout(() => { if (choLamMoi && !dangBan()) location.reload(); }, 0);
  });

  let live = null;

  function connect() {
    live = new EventSource('/events');

    live.onmessage = (msg) => {
      let m;
      try { m = JSON.parse(msg.data); } catch (e) { return; }
      if (m.type === 'hello') {
        $('[data-journal]').forEach((b) => { b.innerHTML = ''; });
        (m.events || []).forEach((e) => journal(e));
        progress(m.running || {});
        setState(m.state, m.next_in);
        const last = (m.events || [])[(m.events || []).length - 1];
        if (last) setLastMessage(last.text);
      } else if (m.type === 'event') {
        journal(m);
        setLastMessage(m.text);
      } else if (m.type === 'progress') {
        // A stage OF THIS PAGE just finished -> redraw the page. Each tab's
        // contents (the job list, the brief store) are built into HTML by the
        // server; SSE can only push the journal and progress. Without a
        // reload the machine finishes its work while the screen stays exactly
        // as it was — which the user reads as broken.
        //
        // WHICH STAGE FINISHING REDRAWS THIS PAGE is declared by the page
        // itself at <body data-reload>. The journal panel is NO LONGER asked:
        // `data-journal` answers "show lines from which stream", a quite
        // different question. Fold the two together and Home (`journal=""`)
        // never redraws, while Track (`journal="search"`) jumps every time a
        // scan finishes.
        const muon = document.body.dataset.reload || '';
        const hop = muon === '*' || muon.split(' ').indexOf(m.stream) >= 0;
        if (!m.what && muon && hop) { refreshIfIdle(); return; }
        // Otherwise: ask for the whole picture again, because the progress
        // frame draws EVERY running stream, not only the one that reported.
        fetch('/api/state').then((r) => r.json()).then((s) => {
          progress(s.running); setState(s.state, s.next_in);
        }).catch(() => {});
      }
    };

    // Dropped, it reconnects itself. The machine runs 24/7, and waking up to
    // it has to mean finding it already there.
    live.onerror = () => { live.close(); setTimeout(connect, 3000); };
  }

  // --------------------------------------------------------------- tag box
  // Type a job title and press Enter to add it. Each tag carries an <input
  // hidden>, so the form posts a list of values and the server never has to
  // split lines.
  //
  // The tag box is shared by EVERY list-shaped question. The field name comes
  // from that box's own data-tags — it used to be hardcoded to 'job_titles',
  // so moving the widget to another field silently saved every tag into the
  // job titles.
  function addTag(box, text) {
    const name = text.trim().replace(/\s+/g, ' ');
    if (!name) return false;
    const have = [...box.querySelectorAll('.tag > input')].map(
      (i) => i.value.toLowerCase());
    if (have.includes(name.toLowerCase())) return false;   // already there, never twice

    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = name;                                 // textContent: words a
    const hidden = document.createElement('input');         // person typed, not HTML
    hidden.type = 'hidden';
    hidden.name = box.dataset.tags || 'job_titles';
    hidden.value = name;
    const kill = document.createElement('button');
    kill.type = 'button';                                   // without this line,
    kill.className = 'untag';                               // × submits the whole form
    kill.dataset.untag = '';
    kill.title = 'remove';
    kill.textContent = '×';
    tag.append(hidden, kill);
    box.insertBefore(tag, box.querySelector('.taginput'));
    dongBo(box.closest('[data-tagfield]'));
    return true;
  }

  function wireTags() {
    document.addEventListener('keydown', (e) => {
      const input = e.target.closest('.taginput');
      if (!input) return;
      const box = input.closest('[data-tags]');
      if (e.key === 'Enter') {
        // Stop Enter from submitting the form: the user is adding a tag,
        // not asking to Apply yet.
        e.preventDefault();
        // With a matching suggestion showing, Enter takes THAT rather than
        // the half-typed text. Type "quant", press Enter, get a "quant" tag,
        // and it finds no posting at all — a job title has to be word for
        // word what the posting says.
        const khoi = input.closest('[data-tagfield]');
        const dau = khoi && input.value.trim()
          ? khoi.querySelector('[data-sugdrop] [data-addtag]:not([hidden])')
          : null;
        const chu = dau ? dau.dataset.addtag : input.value;
        if (addTag(box, chu)) {
          input.value = '';
          if (dau) dau.remove();
          if (khoi) loc(khoi, '');
        }
      } else if (e.key === 'Backspace' && !input.value) {
        const last = [...box.querySelectorAll('.tag')].pop();
        if (last) last.remove();
      }
    });
    // Leaving the field with text still in it adds it anyway — typing and
    // then pressing Apply straight away is normal, and it must not be
    // silently swallowed.
    document.addEventListener('blur', (e) => {
      const input = e.target.closest && e.target.closest('.taginput');
      if (input && addTag(input.closest('[data-tags]'), input.value)) {
        input.value = '';
      }
    }, true);
  }

  // --------------------------------------------------------- Settings menu
  // The content is loaded AT PRESS TIME, never embedded in every page:
  // settings get opened a few times a week, and embedding them makes every
  // page carry data it does not use.
  //
  // kind='stage' -> the right-hand panel (a stage's ⚟ adjust)
  // kind='app'   -> the mid-screen box (whole-app Settings). The same
  //                 open/close machinery in a different place, so one glance
  //                 says whether this belongs to a stage or to the app.
  function openSheet(url, kind, tab) {
    const sheet = document.querySelector('[data-sheet]');
    if (!sheet) return;
    sheet.classList.toggle('mid', kind === 'app');
    const box = sheet.querySelector('.sheetbox');
    box.innerHTML = '<div class=sheetwait>opening…</div>';
    sheet.hidden = false;
    fetch(url || '/settings')
      .then((r) => r.text())
      .then((html) => {
        box.innerHTML = html;
        // Open THE TAB that was named. Clicked here rather than on a timer:
        // the content arrives by fetch, and a setTimeout would be guessing
        // whether the network is fast or slow — on a slow machine the button
        // does not exist yet when the timer fires.
        if (tab) {
          const nut = box.querySelector(`[data-stab="${tab}"]`);
          if (nut) nut.click();
        }
      })
      .catch(() => { box.innerHTML = '<div class=sheetwait>could not open it</div>'; });
  }

  function closeSheet() {
    const sheet = document.querySelector('[data-sheet]');
    if (sheet) { sheet.hidden = true; sheet.querySelector('.sheetbox').innerHTML = ''; }
  }

  // A destructive button only unlocks once THE RIGHT WORD IS TYPED. The
  // listener sits on document because the Settings block is loaded into the
  // overlay after the page is built — attach it to the button and the button
  // does not exist at attach time.
  //
  // This is only a SCREEN-side lock against a mis-press. The server checks
  // again (arg has to be "xoa"); never trust the browser side alone.
  //
  // Switching tabs inside the Settings panel. On document for the same
  // reason. It never reloads from the server on a tab change: all the tabs
  // are already in the fragment, and switching only changes which one shows.
  function wireSheetTabs() {
    document.addEventListener('click', (e) => {
      const tab = e.target.closest('[data-stab]');
      if (!tab) return;
      const box = tab.closest('.sheetbox');
      if (!box) return;
      $('[data-stab]', box).forEach((b) => b.classList.toggle('on', b === tab));
      $('[data-pane]', box).forEach((p) => {
        p.classList.toggle('on', p.dataset.pane === tab.dataset.stab);
      });
    });
  }

  // TYPE TO SEARCH, inside the tag box itself — there is no second filter
  // field. Filtered in the DOM rather than asked of the server: the
  // suggestions are a fixed list, and a network call per keystroke is both
  // wasteful and jerky.
  //
  // Not typing -> CSS reveals only the first few chips (one row, easier on
  //               the eye).
  // Typing     -> .tim is added, the list becomes a dropdown and only
  //               matches show.
  // The "nothing chosen" box only shows while the tag box is really empty.
  function dongBo(khoi) {
    if (!khoi) return;
    const box = khoi.querySelector('[data-tags]');
    const trong = khoi.querySelector('.tagempty');
    if (box && trong) trong.hidden = box.querySelectorAll('.tag').length > 0;
  }

  function loc(khoi, tim) {
    const drop = khoi.querySelector('[data-sugdrop]');
    if (!drop) return null;
    let dau = null, hien = 0;
    $('[data-addtag]', drop).forEach((chip) => {
      const hop = !tim || chip.dataset.addtag.toLowerCase().includes(tim);
      chip.hidden = !hop;
      if (hop) { hien += 1; if (!dau) dau = chip; }
    });
    drop.classList.toggle('tim', !!tim);
    const trong = drop.querySelector('.sugnone');
    if (trong) trong.hidden = hien > 0 || !tim;
    return dau;
  }

  // With no suggestions left, it collapses: an empty search field and an
  // empty chip area are nothing but blank space.
  function dongBoGoiY(khoi) {
    if (!khoi) return;
    const drop = khoi.querySelector('[data-sugdrop]');
    if (!drop) return;
    const con = drop.querySelectorAll('[data-addtag]').length;
    drop.hidden = con === 0;
    const o = khoi.querySelector('.findrow');
    if (o) o.hidden = con === 0;
  }

  // "Select all": adds every suggestion CURRENTLY SHOWING. While a filter is
  // typed it adds only the matches — which is what anyone expects right after
  // filtering.
  function wireAddAll() {
    document.addEventListener('click', (e) => {
      const nut = e.target.closest('[data-addall]');
      if (!nut) return;
      e.preventDefault();
      const khoi = nut.closest('[data-tagfield]');
      const box = khoi && khoi.querySelector('[data-tags]');
      if (!box) return;
      $('[data-sugdrop] [data-addtag]', khoi).forEach((chip) => {
        if (chip.hidden) return;
        if (addTag(box, chip.dataset.addtag)) chip.remove();
      });
      dongBoGoiY(khoi);
    });
  }

  function wireSuggestFilter() {
    document.addEventListener('input', (e) => {
      const o = e.target;
      if (!o.classList || !o.classList.contains('tagfind')) return;
      const khoi = o.closest('[data-tagfield]');
      if (khoi) loc(khoi, o.value.trim().toLowerCase());
    });
    // Enter in the SEARCH field: take the first matching suggestion. Only
    // with no match at all does it take the typed text verbatim — adding
    // something outside the store is a deliberate decision, not the
    // consequence of a stray keystroke.
    document.addEventListener('keydown', (e) => {
      const o = e.target;
      if (e.key !== 'Enter' || !o.classList || !o.classList.contains('tagfind')) return;
      e.preventDefault();          // stop Enter submitting the whole form
      const khoi = o.closest('[data-tagfield]');
      const chu = o.value.trim();
      if (!khoi || !chu) return;
      const dau = khoi.querySelector('[data-sugdrop] [data-addtag]:not([hidden])');
      if (addTag(khoi.querySelector('[data-tags]'), dau ? dau.dataset.addtag : chu)) {
        if (dau) dau.remove();
        o.value = '';
        loc(khoi, '');
      }
    });
  }

  // Add / remove a ROW — shared by education, experience and projects. One
  // mechanism, three users: clone the LAST row and blank it, never build HTML
  // in JS. Built in two places, the day a field is added one of them is
  // forgotten.
  function wireRows() {
    document.addEventListener('click', (e) => {
      const them = e.target.closest('[data-rowadd]');
      if (them) {
        e.preventDefault();
        const kho = them.previousElementSibling;
        if (!kho || !kho.matches('[data-rows]')) return;
        const cuoi = kho.lastElementChild;
        if (!cuoi) return;
        const moi = cuoi.cloneNode(true);
        $('input, textarea', moi).forEach((o) => { o.value = ''; });
        kho.appendChild(moi);
        const dau = moi.querySelector('input, textarea');
        if (dau) dau.focus();
        return;
      }
      const bo = e.target.closest('[data-rowdrop]');
      if (bo) {
        e.preventDefault();
        const kho = bo.closest('[data-rows]');
        const hang = bo.parentElement;
        // The last row is BLANKED rather than removed: remove them all and
        // there is nothing left to clone, and the "add" button dies
        // silently.
        if (kho && kho.children.length > 1) hang.remove();
        else if (hang) $('input, textarea', hang).forEach((o) => { o.value = ''; });
      }
    });
  }

  // ATTACH A MESSAGE TO A ROW. A select, not buttons: a list of 37 companies
  // does not fit in a row of buttons, and the user has to FIND their own
  // row.
  function wireGan() {
    document.addEventListener('change', (e) => {
      const sel = e.target.closest('select[data-ganfor]');
      if (!sel || !sel.value) return;
      sel.disabled = true;
      fetch('/api/track/mail/gan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ arg: sel.dataset.ganfor + ':' + sel.value }).toString(),
      })
        .then((r) => r.json())
        .then((s) => { if (s.reload) location.reload(); else sel.disabled = false; })
        .catch(() => { sel.disabled = false; });
    });
  }

  function wireDangerWord() {
    document.addEventListener('input', (e) => {
      const box = e.target;
      const btn = document.querySelector(`[data-needword="${box.id}"]`);
      if (!box.id || !btn) return;
      const ok = box.value.trim().toUpperCase() === 'DELETE';
      btn.disabled = !ok;
      btn.dataset.arg = ok ? 'xoa' : '';
    });
  }

  function wireSheet() {
    document.addEventListener('click', (e) => {
      const app = e.target.closest('[data-appset]');
      if (app) {
        e.preventDefault();
        // data-appset can carry A TAB NAME: a "Connect a mailbox…" button on
        // Track that opens the Run tab leaves the user to go hunting — half
        // a direction is more annoying than none.
        openSheet('/settings', 'app', app.dataset.appset);
        return;
      }
      const knob = e.target.closest('[data-settings]');
      if (knob) { e.preventDefault(); openSheet(knob.dataset.settings, 'stage'); return; }
      // Clicking outside the box closes it — clicking INSIDE does not.
      const sheet = e.target.closest('[data-sheet]');
      if (sheet && !e.target.closest('.sheetbox')) closeSheet();
    });
    // A form with [data-post]: it posts THE WHOLE FORM, not just data-arg
    // the way a button does. A [data-post] button sends one parameter; the
    // mailbox fields need two.
    document.addEventListener('submit', (e) => {
      const form = e.target.closest('form[data-post]');
      if (!form) return;
      e.preventDefault();
      const note = form.querySelector('.formnote');
      if (note) note.textContent = ' · checking…';
      fetch(form.dataset.post, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(new FormData(form)).toString(),
      })
        .then((r) => r.json())
        .then((s) => {
          if (s.reload) { location.reload(); return; }
          if (note) note.textContent = ' · ' + (s.note || 'not yet');
        })
        .catch(() => { if (note) note.textContent = ' · sending failed'; });
    });
    document.addEventListener('submit', (e) => {
      const form = e.target.closest('.setform');
      // ONLY the Settings form is intercepted. This used to intercept EVERY
      // .setform and post it hardcoded to '/settings', so two other forms in
      // the same overlay — the CV block editor and adding a project to the CV
      // — ran into Settings when pressed by hand. Pressing with form.submit()
      // during testing never showed it, because that path skips listeners.
      if (!form || new URL(form.action, location.href).pathname !== '/settings') return;
      e.preventDefault();          // save in place, never leave the open page
      // URLSearchParams and NOT a bare FormData: FormData posts multipart
      // while the server reads urlencoded — it goes out and silently saves
      // nothing.
      //
      // FormData(form, SUBMITTER) — the second argument is required, not
      // optional. FormData(form) DROPS the name/value of the very button that
      // was pressed, so `Find chat` (name=tim) and `Test` (name=test) arrive
      // identical to Save: the server sees no flag and only saves, silently.
      // Both buttons still look like they work while doing nothing at all —
      // the worst kind of silent failure.
      const fd = new FormData(form, e.submitter);
      // Older browsers ignore the second argument: put it in by hand.
      if (e.submitter && e.submitter.name && !fd.has(e.submitter.name)) {
        fd.append(e.submitter.name, e.submitter.value || '');
      }
      fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(fd).toString(),
      })
        .then((r) => r.text())
        .then((html) => {
          const box = document.querySelector('.sheetbox');
          box.innerHTML = html;
          // DO NOT overwrite the note when the server has returned a REAL
          // RESULT (the .testkq banner). Overwriting replaces a measured
          // sentence with a guessed one, and "saved" is plainly wrong when
          // what just happened was sending a test message.
          if (box.querySelector('.testkq')) return;
          const note = box.querySelector('.applynote');
          if (note) note.textContent = 'saved · takes effect from the next scan';
        })
        .catch(() => {});
    });
  }

  // ---------------------------------------------------------------- buttons
  function syncNav() {
    // The server always draws the "Collapse" label because it cannot know
    // whether this machine has the sidebar collapsed or open — that choice
    // lives in localStorage. The label is corrected as the page comes up,
    // otherwise a collapsed sidebar still offers "Collapse sidebar".
    const min = document.documentElement.classList.contains('navmin');
    $('[data-nav]').forEach((b) => {
      b.title = min ? 'Expand sidebar' : 'Collapse sidebar';
    });
  }

  function wire() {
    document.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]');
      if (act) {
        e.preventDefault();
        fetch('/api/' + act.dataset.act, { method: 'POST' })
          .then((r) => r.json()).then((s) => setState(s.state, s.next_in))
          .catch(() => {});
        return;
      }
      // A button calling a BACKGROUND job: it posts, then says what it is
      // doing. It does not share [data-act] with Run/Pause because the two
      // return different things — that one returns machine state, this one
      // returns the job just queued.
      const post = e.target.closest('[data-post]');
      // A FORM also carries [data-post], and its submit button sits INSIDE
      // it — closest() walking up finds the form, not the button. This branch
      // used to accept the form and set textContent on it, which WIPES THE
      // FORM'S CONTENTS: one press of Connect and the fields vanished. Forms
      // are left to the 'submit' listener.
      if (post && post.tagName === 'FORM') return;
      // A TWO-BEAT LATCH for a destructive button. The first beat only
      // CHANGES THE TEXT and arms it; the second sends. No dialog box — a
      // dialog gets OK'd by reflex, while a button that turns into "Really
      // delete?" makes the eye read it again.
      //
      // It disarms itself after 4 seconds: an armed button sitting there all
      // afternoon is exactly the trap this was built to avoid.
      if (post && post.dataset.arm !== undefined && !post.dataset.armed) {
        e.preventDefault();
        const cu = post.textContent;
        post.dataset.armed = '1';
        post.textContent = post.dataset.arm || 'Are you sure?';
        post.classList.add('armed');
        setTimeout(() => {
          if (!post.dataset.armed) return;
          delete post.dataset.armed;
          post.textContent = cu;
          post.classList.remove('armed');
        }, 4000);
        return;
      }
      if (post) {
        e.preventDefault();
        delete post.dataset.armed;
        post.classList.remove('armed');
        const was = post.textContent;
        post.disabled = true;                 // stop a double press making two threads
        fetch(post.dataset.post, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ arg: post.dataset.arg || '' }).toString(),
        })
          .then((r) => r.json())
          .then((s) => {
            if (s.reload) {
              // "Back to the original state" includes what the browser is
              // remembering — a collapsed or open sidebar is app state, not
              // machine state.
              if (s.wipe_local) { try { localStorage.clear(); } catch (err) {} }
              location.reload();
              return;
            }
            // ON REFUSAL the reason goes to THE STATUS BAR, never into the
            // button's label: a reason runs to a hundred characters, and
            // setting it on the button bursts the pill. The button returns to
            // its old text and can be pressed again — the user gets to read
            // why and still has a button to press once they have fixed it.
            if (s.ok === false) {
              setLastMessage(s.note || 'not yet');
              post.disabled = false;
              post.textContent = was;
              return;
            }
            post.textContent = s.note || was;
            // AN ON/OFF BUTTON differs from a one-shot. By default a button
            // locks after being pressed (stopping a double press from making
            // two background threads) — right for "Apply" and "Build", wrong
            // for a switch: turn it on and it cannot be turned off again.
            if (s.again) post.disabled = false;
            if (typeof s.on === 'boolean') post.classList.toggle('off', !s.on);
          })
          .catch(() => { post.disabled = false; post.textContent = was; });
        return;
      }
      const nav = e.target.closest('[data-nav]');
      if (nav) {
        e.preventDefault();
        // Change the class FIRST and remember afterwards: pressing shows at
        // once, with nothing to wait for.
        const min = document.documentElement.classList.toggle('navmin');
        try { localStorage.jobbotNav = min ? '1' : '0'; } catch (err) {}
        syncNav();
        return;
      }
      // The "the sieve is missing these" chips: pressing drops the tag into
      // the job titles box. It does NOT save by itself — Apply still has to
      // be pressed, because changing the sieve re-judges the whole table.
      const add = e.target.closest('[data-addtag]');
      if (add) {
        e.preventDefault();
        // Find the tag box IN THE SAME BLOCK as the chip. A profile page has
        // several tag boxes; a page-wide querySelector drops every chip into
        // the first one.
        const khoi = add.closest('[data-tagfield]') || document;
        const box = khoi.querySelector('[data-tags]');
        if (box && addTag(box, add.dataset.addtag)) add.remove();
        dongBoGoiY(add.closest('[data-tagfield]'));
        return;
      }
      const bot = e.target.closest('[data-untag]');
      if (bot) {
        // let the existing [data-untag] branch handle it; only the empty box
        // needs tidying afterwards
        setTimeout(() => dongBo(bot.closest('[data-tagfield]')), 0);
      }
      const untag = e.target.closest('[data-untag]');
      if (untag) { e.preventDefault(); untag.closest('.tag').remove(); return; }

      const grow = e.target.closest('[data-expand]');
      if (grow) {
        e.preventDefault();
        grow.closest('[data-widget]').classList.toggle('big');
      }
    });
    // Esc shrinks an enlarged widget — enlarged with no visible close button
    // is a dead end.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const sheet = document.querySelector('[data-sheet]');
      if (sheet && !sheet.hidden) { closeSheet(); return; }   // the menu first
      $('[data-widget].big').forEach((w) => w.classList.remove('big'));
    });
  }

  wire();
  wireTags();
  wireSheet();
  wireGan();
  wireDangerWord();
  wireSheetTabs();
  wireSuggestFilter();
  wireAddAll();
  // MAKE THEM FILL IT IN: with the profile incomplete, the overlay opens as
  // soon as the app does. It can be closed (Esc / click outside) — held, not
  // locked in; come back to Home and it opens again.
  if (document.body.dataset.setup) openSheet(document.body.dataset.setup, 'app');
  wireRows();
  syncNav();
  connect();
})();
