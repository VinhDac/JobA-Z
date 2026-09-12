/* Cầu nối runtime: máy đẩy xuống, màn hình vẽ lại. Không thư viện.
 *
 * Hợp đồng với HTML — view chỉ cần đặt đúng thuộc tính, không cần biết gì thêm:
 *
 *   [data-journal="search"]   khung nhật ký, lọc theo luồng ("" = tất cả)
 *   [data-progress="search"]  khung thanh tiến độ, lọc theo luồng
 *   [data-state]              chỗ hiện đang chạy / tạm dừng / chờ
 *   [data-act="run"|"pause"]  nút master
 *   [data-nav]                nút gập thanh bên
 *   [data-tags]               ô thẻ: gõ + Enter để thêm, × để bỏ
 *   [data-post]               nút gọi việc nền; [data-arg] là tham số
 *   [data-settings]           mở tấm bên phải; giá trị = URL mảnh HTML cần nạp
 *   [data-appset]             mở hộp Cài đặt cả app (giữa màn)
 *   [data-widget]             một ô; [data-expand] trong đó là nút mở to
 *
 * Không dùng polling: mở một kết nối SSE rồi để yên. Chạy 24/7 mà hỏi mỗi
 * giây thì một ngày là 86.400 lượt hỏi cho phần lớn là "chưa có gì mới".
 */
(() => {
  'use strict';

  const MAX_LINES = 200;          // trần DOM — chạy 24/7 không được phình
  const $ = (sel, root) => (root || document).querySelectorAll(sel);

  // ---------------------------------------------------------------- nhật ký
  const timeOf = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? '' : d.toTimeString().slice(0, 8);
  };

  // Khung CUỘN thật nằm ở đâu. Dòng nhật ký nằm trong .journal, nhưng thứ có
  // thanh cuộn là .jfeed bọc ngoài — đặt scrollTop lên nhầm phần tử thì không
  // có gì xảy ra, và cũng không có lỗi nào để mà lần ra. Dừng ở [data-widget]
  // để không leo ra tới cả trang.
  function scroller(el) {
    for (let n = el; n; n = n.parentElement) {
      const how = getComputedStyle(n).overflowY;
      if (how === 'auto' || how === 'scroll') return n;
      if (n.matches('[data-widget]')) return null;
    }
    return null;
  }

  const STICK = 24;               // cách đỉnh trong ngần này px = đang bám tin mới

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

    // Dòng mới vào ĐỈNH. Chèn ở trên chỗ đang nhìn thì trình duyệt giữ
    // nguyên scrollTop, nghĩa là mỗi dòng mới đẩy khung nhìn xuống thêm một
    // nấc — càng chạy càng trôi xa tin mới nhất, và tin mới nhất nằm ngoài
    // màn hình. Đúng cái vừa thấy: vòng nộp đang chạy mà nhật ký đứng ở
    // mấy dòng cũ.
    const sc = scroller(box);
    const dang_bam = !sc || sc.scrollTop <= STICK;
    box.insertBefore(row, box.firstChild);
    while (box.childElementCount > MAX_LINES) box.removeChild(box.lastChild);
    if (!sc) return;
    if (dang_bam) sc.scrollTop = 0;              // bám theo tin mới nhất
    else sc.scrollTop += row.offsetHeight;       // đang đọc dòng cũ -> giữ nguyên chỗ
  }

  const journal = (ev) => $('[data-journal]').forEach((b) => addLine(b, ev));

  // --------------------------------------------------------------- tiến độ
  function drawProgress(box, all) {
    const want = box.dataset.progress;
    const rows = Object.entries(all).filter(([s]) => !want || s === want);
    if (!rows.length) { box.innerHTML = '<div class=pidle>không có việc đang chạy</div>'; return; }

    box.innerHTML = rows.map(([stream, p]) => {
      const width = p.total ? p.percent : 100;
      // Dòng "còn bao lâu" chỉ dựng khi CÓ số. Dựng sẵn rồi để rỗng thì nó
      // vẫn chiếm chỗ và thanh nhảy lên nhảy xuống mỗi lần máy đổi việc.
      return '<div class="prow' + (p.total ? '' : ' spin') + '">' +
             '<div class=phead><b></b><span></span></div>' +
             '<div class=ptrack><i style="width:' + width + '%"></i></div>' +
             (p.eta_text ? '<div class=peta></div>' : '') + '</div>';
    }).join('');

    // Chữ đặt bằng textContent, KHÔNG nối vào chuỗi HTML: tên nguồn và tên
    // tin là dữ liệu cào về, nối thẳng vào innerHTML là mở cửa cho thẻ lạ.
    box.querySelectorAll('.prow').forEach((el, i) => {
      const [stream, p] = rows[i];
      el.querySelector('b').textContent = want ? p.what : stream + ' — ' + p.what;
      el.querySelector('span').textContent = p.total ? p.done + '/' + p.total : '';
      const eta = el.querySelector('.peta');
      // Chữ do MÁY CHỦ tính (journal.remain_text) — dòng nhật ký và thanh này
      // phải nói cùng một con số, nên chỉ có một chỗ định dạng.
      if (eta) eta.textContent = 'còn ' + p.eta_text;
    });
  }

  const progress = (all) => $('[data-progress]').forEach((b) => drawProgress(b, all));

  // --------------------------------------------------------------- trạng thái
  // 'tạm dừng' lúc vừa mở app đọc ra như đang hỏng. Nói thẳng ra là tự quét
  // đang tắt, và nút bên cạnh chính là chỗ bật.
  function label(state, mins) {
    if (state === 'running') return 'đang chạy';
    if (state === 'paused') return 'tự quét: TẮT';
    return mins > 0 ? 'chờ · quét sau ' + mins + ' phút' : 'chờ';
  }

  // Việc gần nhất, hiện ở thanh trạng thái đáy app. Không lưu đâu cả — đây là
  // TIN, không phải trạng thái; dòng mới đến là đè lên dòng cũ.
  function setLastMessage(text) {
    if (!text) return;
    $('[data-lastmsg]').forEach((el) => { el.textContent = text; });
  }

  function setState(state, mins) {
    document.body.dataset.run = state;
    $('[data-state]').forEach((el) => { el.textContent = label(state, mins); });
    $('[data-act="pause"]').forEach((b) => {
      b.textContent = state === 'paused' ? 'Bật tự quét' : 'Tắt tự quét';
      b.title = state === 'paused'
        ? 'Quét theo lịch. Lựa chọn được nhớ cho lần mở app sau.'
        : 'Ngưng quét theo lịch. Nút Chạy ngay vẫn dùng được.';
    });
    $('[data-act="run"]').forEach((b) => { b.disabled = state === 'running'; });

    // Nút chạy của KHÚC (Search…). Chữ lúc rảnh do máy chủ tính theo tình
    // huống — Bắt đầu / Tiếp tục / Cập nhật — và nằm sẵn ở data-run. Lúc
    // đang chạy thì chỉ có một chữ đúng, và nó là trạng thái tạm nên để
    // trình duyệt lo, máy chủ không phải đoán xem màn hình đang thấy gì.
    $('[data-post="/api/stage/start"]').forEach((b) => {
      const ranh = b.dataset.run || b.textContent;
      b.disabled = state === 'running';
      b.textContent = state === 'running' ? 'Đang quét…' : ranh;
    });
  }

  // --------------------------------------------------------------- kết nối
  // Nạp lại trang, TRỪ KHI làm thế là cướp mất việc người dùng đang làm dở.
  function refreshIfIdle() {
    const here = document.activeElement;
    if (here && here.matches('input, textarea, select')) return;  // đang gõ
    const sheet = document.querySelector('[data-sheet]');
    if (sheet && !sheet.hidden) return;                           // menu đang mở
    location.reload();
  }

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
        // Luồng CỦA TRANG NÀY vừa xong -> vẽ lại trang. Ruột mỗi tab (danh
        // sách việc, kho đề bài) do máy chủ dựng thành HTML; SSE chỉ đẩy được
        // nhật ký và tiến độ. Không nạp lại thì máy làm xong mà màn hình vẫn
        // y nguyên — người dùng đọc ra là hỏng.
        const box = document.querySelector('[data-journal]');
        const mine = box && box.dataset.journal;      // "" ở Home = mọi luồng
        if (!m.what && mine && m.stream === mine) { refreshIfIdle(); return; }
        // Còn lại: hỏi lại toàn cảnh, vì khung tiến độ vẽ TẤT CẢ luồng đang
        // chạy chứ không riêng luồng vừa báo.
        fetch('/api/state').then((r) => r.json()).then((s) => {
          progress(s.running); setState(s.state, s.next_in);
        }).catch(() => {});
      }
    };

    // Đứt thì tự nối lại. Máy chạy 24/7, ngủ dậy mở máy là phải có sẵn.
    live.onerror = () => { live.close(); setTimeout(connect, 3000); };
  }

  // --------------------------------------------------------------- ô thẻ
  // Gõ chức danh rồi Enter là thêm. Mỗi thẻ mang một <input hidden>, nên form
  // gửi lên một danh sách giá trị — server không phải ngồi tách dòng.
  // Ô thẻ dùng chung cho MỌI câu hỏi kiểu danh sách. Tên trường lấy từ
  // data-tags của chính ô đó — trước đây đóng cứng 'job_titles', nên mang
  // widget sang ô khác là mọi thẻ lặng lẽ lưu nhầm vào chức danh.
  function addTag(box, text) {
    const name = text.trim().replace(/\s+/g, ' ');
    if (!name) return false;
    const have = [...box.querySelectorAll('.tag > input')].map(
      (i) => i.value.toLowerCase());
    if (have.includes(name.toLowerCase())) return false;   // đã có, không thêm hai lần

    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = name;                                 // textContent: chữ người
    const hidden = document.createElement('input');         // gõ vào, không phải HTML
    hidden.type = 'hidden';
    hidden.name = box.dataset.tags || 'job_titles';
    hidden.value = name;
    const kill = document.createElement('button');
    kill.type = 'button';                                   // không có dòng này thì
    kill.className = 'untag';                               // bấm × là gửi cả form
    kill.dataset.untag = '';
    kill.title = 'bỏ';
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
        // Chặn Enter gửi form: người dùng đang thêm thẻ, chưa muốn Áp dụng.
        e.preventDefault();
        // Đang có gợi ý khớp thì Enter lấy CÁI ĐÓ, không lấy chữ gõ dở. Gõ
        // "quant" rồi Enter mà ra thẻ "quant" thì tìm không ra tin nào —
        // chức danh phải đúng nguyên văn như trên tin.
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
    // Rời ô mà còn chữ dở thì vẫn thêm — gõ xong bấm thẳng Áp dụng là chuyện
    // thường, không nên im lặng nuốt mất.
    document.addEventListener('blur', (e) => {
      const input = e.target.closest && e.target.closest('.taginput');
      if (input && addTag(input.closest('[data-tags]'), input.value)) {
        input.value = '';
      }
    }, true);
  }

  // ------------------------------------------------------------- menu Cài đặt
  // Nạp nội dung LÚC BẤM, không nhúng sẵn vào mọi trang: cài đặt là thứ mở ra
  // vài lần một tuần, mà nhúng sẵn thì trang nào cũng phải mang theo dữ liệu
  // nó không dùng.
  // kind='stage' -> tấm bên phải (⚟ điều chỉnh khúc)
  // kind='app'   -> hộp giữa màn (Cài đặt cả app). Cùng bộ máy mở/đóng, khác
  //                 chỗ đứng, để nhìn là biết thứ này của khúc hay của app.
  function openSheet(url, kind, tab) {
    const sheet = document.querySelector('[data-sheet]');
    if (!sheet) return;
    sheet.classList.toggle('mid', kind === 'app');
    const box = sheet.querySelector('.sheetbox');
    box.innerHTML = '<div class=sheetwait>đang mở…</div>';
    sheet.hidden = false;
    fetch(url || '/settings')
      .then((r) => r.text())
      .then((html) => {
        box.innerHTML = html;
        // Mở đúng TAB được chỉ. Bấm ở đây chứ không hẹn giờ: nội dung nạp về
        // bằng fetch, đặt setTimeout là đoán xem mạng nhanh hay chậm — và
        // trên máy chậm thì cái nút chưa tồn tại lúc hẹn giờ nổ.
        if (tab) {
          const nut = box.querySelector(`[data-stab="${tab}"]`);
          if (nut) nut.click();
        }
      })
      .catch(() => { box.innerHTML = '<div class=sheetwait>không mở được</div>'; });
  }

  function closeSheet() {
    const sheet = document.querySelector('[data-sheet]');
    if (sheet) { sheet.hidden = true; sheet.querySelector('.sheetbox').innerHTML = ''; }
  }

  // Nút phá hoại phải GÕ ĐÚNG CHỮ mới bấm được. Trình nghe đặt trên document
  // vì khối Cài đặt nạp vào tấm phủ sau khi trang đã dựng — gắn thẳng vào nút
  // thì lúc gắn nút chưa tồn tại.
  //
  // Đây chỉ là lớp khoá ở MÀN HÌNH cho đỡ bấm nhầm. Server kiểm lại lần nữa
  // (arg phải là "xoa"); không bao giờ tin mỗi phía trình duyệt.
  // Chuyển tab trong tấm Cài đặt. Đặt trên document vì tấm này nạp vào sau
  // khi trang đã dựng. KHÔNG nạp lại từ server mỗi lần đổi tab: cả ba tab đã
  // nằm sẵn trong mảnh HTML, đổi tab chỉ là đổi cái nào hiện.
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

  // GÕ ĐỂ TÌM, ngay trong ô thẻ — không có ô lọc thứ hai. Lọc trong DOM chứ
  // không hỏi server: gợi ý là danh sách cố định, gọi mạng mỗi phím là thừa
  // và giật.
  //
  // Không gõ -> CSS chỉ để lộ mấy chip đầu (một hàng, cho đỡ dồn mắt).
  // Đang gõ  -> thêm .tim, danh sách thành dropdown và chỉ hiện cái khớp.
  // Ô "chưa chọn gì" chỉ hiện khi khung thẻ rỗng thật.
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

  // Hết gợi ý thì thu gọn: ô tìm và vùng chip rỗng chỉ còn là khoảng trống.
  function dongBoGoiY(khoi) {
    if (!khoi) return;
    const drop = khoi.querySelector('[data-sugdrop]');
    if (!drop) return;
    const con = drop.querySelectorAll('[data-addtag]').length;
    drop.hidden = con === 0;
    const o = khoi.querySelector('.findrow');
    if (o) o.hidden = con === 0;
  }

  // "Chọn tất cả": thêm mọi gợi ý ĐANG HIỆN. Đang gõ lọc thì nó chỉ thêm cái
  // khớp — đó là điều người ta mong đợi khi vừa lọc xong.
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
    // Enter ở ô TÌM: lấy gợi ý khớp đầu tiên. Không khớp gì thì mới lấy
    // nguyên văn chữ gõ — thêm thứ ngoài kho là quyết định có ý thức, không
    // phải hậu quả của một phím lỡ tay.
    document.addEventListener('keydown', (e) => {
      const o = e.target;
      if (e.key !== 'Enter' || !o.classList || !o.classList.contains('tagfind')) return;
      e.preventDefault();          // chặn Enter gửi cả form
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

  // Thêm / bỏ HÀNG — dùng chung cho học vấn, kinh nghiệm và project. Một cơ
  // chế, ba chỗ dùng: nhân bản hàng CUỐI rồi xoá trắng, không dựng HTML trong
  // JS. Dựng ở hai nơi thì hôm nào thêm một ô là quên một chỗ.
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
        // Hàng cuối cùng thì XOÁ TRẮNG chứ không gỡ: gỡ hết thì không còn gì
        // để nhân bản, nút "thêm" chết câm.
        if (kho && kho.children.length > 1) hang.remove();
        else if (hang) $('input, textarea', hang).forEach((o) => { o.value = ''; });
      }
    });
  }

  function wireDangerWord() {
    document.addEventListener('input', (e) => {
      const box = e.target;
      const btn = document.querySelector(`[data-needword="${box.id}"]`);
      if (!box.id || !btn) return;
      const ok = box.value.trim().toUpperCase() === 'XOA';
      btn.disabled = !ok;
      btn.dataset.arg = ok ? 'xoa' : '';
    });
  }

  function wireSheet() {
    document.addEventListener('click', (e) => {
      const app = e.target.closest('[data-appset]');
      if (app) {
        e.preventDefault();
        // data-appset có thể mang TÊN TAB: một nút "Nối hộp thư…" bên Quản lí
        // mà mở ra tab Chạy thì người dùng phải tự đi tìm — chỉ đường nửa vời
        // còn khó chịu hơn không chỉ.
        openSheet('/settings', 'app', app.dataset.appset);
        return;
      }
      const knob = e.target.closest('[data-settings]');
      if (knob) { e.preventDefault(); openSheet(knob.dataset.settings, 'stage'); return; }
      // Bấm ra ngoài hộp thì đóng — nhưng bấm TRONG hộp thì không.
      const sheet = e.target.closest('[data-sheet]');
      if (sheet && !e.target.closest('.sheetbox')) closeSheet();
    });
    // Form có [data-post]: gửi CẢ FORM, không phải mỗi data-arg như nút bấm.
    // Nút [data-post] chỉ gửi một tham số; ô nhập hộp thư cần hai.
    document.addEventListener('submit', (e) => {
      const form = e.target.closest('form[data-post]');
      if (!form) return;
      e.preventDefault();
      const note = form.querySelector('.formnote');
      if (note) note.textContent = ' · đang kiểm…';
      fetch(form.dataset.post, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(new FormData(form)).toString(),
      })
        .then((r) => r.json())
        .then((s) => {
          if (s.reload) { location.reload(); return; }
          if (note) note.textContent = ' · ' + (s.note || 'chưa được');
        })
        .catch(() => { if (note) note.textContent = ' · gửi hỏng'; });
    });
    document.addEventListener('submit', (e) => {
      const form = e.target.closest('.setform');
      // CHỈ chặn form Cài đặt. Trước đây chặn MỌI .setform rồi gửi cứng tới
      // '/settings', nên hai form khác trong cùng tấm phủ — soạn khối CV và
      // đưa project vào CV — bấm tay là chạy vào Cài đặt. Bấm bằng
      // form.submit() trong lúc thử thì không lộ, vì cách đó bỏ qua trình nghe.
      if (!form || new URL(form.action, location.href).pathname !== '/settings') return;
      e.preventDefault();          // lưu tại chỗ, không rời trang đang xem
      // URLSearchParams chứ KHÔNG phải FormData trần: FormData gửi kiểu
      // multipart, mà server đọc urlencoded — gửi đi thì im lặng không lưu gì.
      fetch('/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(new FormData(form)).toString(),
      })
        .then((r) => r.text())
        .then((html) => {
          document.querySelector('.sheetbox').innerHTML = html;
          const note = document.querySelector('.sheetbox .applynote');
          if (note) note.textContent = 'đã lưu · có tác dụng từ lần quét sau';
        })
        .catch(() => {});
    });
  }

  // --------------------------------------------------------------- nút bấm
  function syncNav() {
    // Server luôn vẽ nhãn "Gập" vì nó không biết máy này đang gập hay mở —
    // lựa chọn nằm ở localStorage. Sửa nhãn ngay khi trang lên, nếu không thì
    // thanh đang gập mà nút vẫn mời "Gập thanh bên".
    const min = document.documentElement.classList.contains('navmin');
    $('[data-nav]').forEach((b) => {
      b.title = min ? 'Mở thanh bên' : 'Gập thanh bên';
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
      // Nút gọi một việc NỀN: gửi đi, rồi tự nói ra nó đang làm gì. Không
      // dùng chung [data-act] với Chạy/Tạm dừng vì hai cái trả về khác nhau —
      // bên kia trả về trạng thái máy, bên này trả về việc vừa xếp hàng.
      const post = e.target.closest('[data-post]');
      // FORM cũng mang [data-post], và nút Gửi nằm TRONG nó — closest() đi
      // ngược lên là gặp form chứ không phải nút. Trước đây nhánh này nhận
      // luôn cái form rồi gán textContent lên nó, tức là XOÁ SẠCH RUỘT FORM:
      // bấm Nối một cái là ô nhập biến mất. Form để trình nghe 'submit' lo.
      if (post && post.tagName === 'FORM') return;
      if (post) {
        e.preventDefault();
        const was = post.textContent;
        post.disabled = true;                 // chặn bấm hai lần ra hai luồng
        fetch(post.dataset.post, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ arg: post.dataset.arg || '' }).toString(),
        })
          .then((r) => r.json())
          .then((s) => {
            if (s.reload) {
              // "Về trạng thái ban đầu" gồm cả thứ trình duyệt đang nhớ —
              // thanh bên đang gập hay mở là state của app, không phải của máy.
              if (s.wipe_local) { try { localStorage.clear(); } catch (err) {} }
              location.reload();
              return;
            }
            // BỊ TỪ CHỐI thì lý do ra THANH TRẠNG THÁI, không nhét vào nhãn
            // nút: câu lý do dài cả trăm ký tự, gán vào nút là vỡ viên thuốc.
            // Nút trả về chữ cũ và bấm lại được — người dùng vừa đọc được vì
            // sao, vừa còn nút để bấm sau khi sửa.
            if (s.ok === false) {
              setLastMessage(s.note || 'chưa được');
              post.disabled = false;
              post.textContent = was;
              return;
            }
            post.textContent = s.note || was;
            // NÚT BẬT/TẮT khác nút một-lần. Mặc định nút bị khoá sau khi bấm
            // (chặn bấm hai lần ra hai luồng việc nền) — đúng cho "Nộp",
            // "Dựng", nhưng sai cho một công tắc: bật rồi không tắt lại được.
            if (s.again) post.disabled = false;
            if (typeof s.on === 'boolean') post.classList.toggle('off', !s.on);
          })
          .catch(() => { post.disabled = false; post.textContent = was; });
        return;
      }
      const nav = e.target.closest('[data-nav]');
      if (nav) {
        e.preventDefault();
        // Đổi class NGAY rồi mới ghi nhớ: bấm là thấy, không chờ gì cả.
        const min = document.documentElement.classList.toggle('navmin');
        try { localStorage.jobbotNav = min ? '1' : '0'; } catch (err) {}
        syncNav();
        return;
      }
      // Chip "lưới đang bỏ sót": bấm là thẻ rơi vào ô chức danh. KHÔNG tự
      // lưu — vẫn phải bấm Áp dụng, vì đổi lưới là phán lại cả bảng.
      const add = e.target.closest('[data-addtag]');
      if (add) {
        e.preventDefault();
        // Tìm ô thẻ CÙNG KHỐI với chip. Một trang hồ sơ có nhiều ô thẻ; lấy
        // querySelector toàn trang thì mọi chip đều rơi vào ô đầu tiên.
        const khoi = add.closest('[data-tagfield]') || document;
        const box = khoi.querySelector('[data-tags]');
        if (box && addTag(box, add.dataset.addtag)) add.remove();
        dongBoGoiY(add.closest('[data-tagfield]'));
        return;
      }
      const bot = e.target.closest('[data-untag]');
      if (bot) {
        // để nhánh [data-untag] sẵn có xử lí; chỉ cần dọn ô trống sau đó
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
    // Esc để thu ô đang mở to — mở to rồi không tìm thấy nút đóng là bí.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const sheet = document.querySelector('[data-sheet]');
      if (sheet && !sheet.hidden) { closeSheet(); return; }   // menu trước
      $('[data-widget].big').forEach((w) => w.classList.remove('big'));
    });
  }

  wire();
  wireTags();
  wireSheet();
  wireDangerWord();
  wireSheetTabs();
  wireSuggestFilter();
  wireAddAll();
  // BẮT ĐIỀN: hồ sơ chưa đủ thì bật tấm phủ ngay khi vào app. Đóng được
  // (Esc / bấm ra ngoài) — giữ chứ không nhốt; quay lại Home là nó bật lại.
  if (document.body.dataset.setup) openSheet(document.body.dataset.setup, 'app');
  wireRows();
  syncNav();
  connect();
})();
