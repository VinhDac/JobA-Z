"""LinkedIn — chỉ tin tuyển dụng CÔNG KHAI, KHÔNG đăng nhập.

Ranh giới, cố ý và không thoả hiệp:

    ĐƯỢC   trang tin công khai, xem khi chưa đăng nhập, nhịp người
    KHÔNG  đăng nhập tài khoản người dùng   -> đó là thứ mất được, và mất là
                                               mất luôn mạng lưới nghề nghiệp
    KHÔNG  hồ sơ cá nhân, kết nối, tin nhắn -> đó là thứ LinkedIn kiện Proxycurl
    KHÔNG  cãi lại khi bị chặn              -> chặn thì dừng, ghi nhận, đi tiếp

Chạy trên profile Chrome riêng, không đăng nhập gì cả. Không có tài khoản thì
không có tài khoản nào để mất.

Dùng đúng endpoint LinkedIn tự phục vụ khách chưa đăng nhập
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`), 10 tin một trang.

LƯU Ý: việc này vẫn nằm ngoài Điều khoản sử dụng của LinkedIn (mục 8.2). Vin đã
được nói rõ điều đó và tự quyết định. Ghi lại ở đây để người đọc code sau này biết.
"""

from __future__ import annotations

import random
import re
import time
import urllib.parse

from ...core.journal import SEARCH, log as jlog
from ..base import Posting, strip_html
from .base import Blocked, Health, grab, open_page

NAME = "linkedin"
GUEST = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
         "?keywords={q}&location={loc}&f_E={exp}&start={start}{tpr}")

# Cửa sổ thời gian, tính bằng giây. ĐÃ THỬ THẬT trên cổng guest:
#
#   f_TPR=r86400   CHẠY  — 10/10 tin trả về đều từ 24 giờ qua
#   sortBy=DD      bị phớt lờ — kết quả y hệt không truyền gì
#   f_WT=2         bị phớt lờ — (đo hôm trước, cùng kiểu)
#
# Phải thử từng cái, không được đoán: hai trong ba tham số trông hợp lý kia
# không làm gì cả, mà cổng vẫn trả 200 nên nhìn như đang chạy.
NGAY = 86400
TUAN = 7 * NGAY
# Mô tả đầy đủ, vẫn là đường LinkedIn phục vụ khách chưa đăng nhập.
GUEST_JOB = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
VIEW = "https://www.linkedin.com/jobs/view/{jid}/"
PER_PAGE = 10
# Cứ bấy nhiêu tin đọc kỹ thì nói một câu vào nhật ký. Không ghi từng tin:
# 2.297 dòng cho một lần quét thì nhật ký không đọc được nữa. Không ghi gì
# thì im lặng 27 phút — đã đo trên lượt quét 19:22. 25 tin ≈ 2 phút một câu.
NHIP_BAO = 25

# f_E: 1=internship 2=entry 3=associate 4=mid-senior
EXPERIENCE = {"intern": "1", "grad": "2", "grad_scheme": "2", "junior": "2,3",
              "mid": "3,4", "senior": "4", "lead": "4"}

# Nhịp chậm hơn hẳn nguồn khác. Không phải để né — mà vì đây là bên duy nhất
# mình đang ở nhờ, nên đi nhẹ chân.
PAUSE = (2.5, 5.0)

# Ba nhịp cho người dùng chọn. Module này chỉ BIẾT nhịp nghĩa là gì ở cổng
# này; ai gọi thì người đó quyết chọn nhịp nào — y như `worth`.
NHIP = {"nhe": (4.0, 7.0), "thuong": PAUSE, "nhanh": (1.2, 2.5)}

LIST_JS = """
(() => {
  try {
    const out = [];
    for (const li of document.querySelectorAll('li')) {
      const a = li.querySelector('a[href*="/jobs/view/"]');
      if (!a) continue;
      const pick = s => (li.querySelector(s) || {}).innerText || '';
      const t = li.querySelector('time');
      out.push({
        title: pick('h3').trim(),
        company: pick('a.hidden-nested-link').trim() || pick('h4').trim(),
        location: pick('[class*=location]').trim(),
        url: a.getAttribute('href').split('?')[0],
        posted: t ? (t.getAttribute('datetime') || t.innerText.trim()) : ''
      });
    }
    return JSON.stringify(out);
  } catch (e) { return "[]"; }
})()
"""

DETAIL_JS = """
(() => {
  try {
    const box = document.querySelector('[class*=show-more-less-html__markup]')
             || document.querySelector('[class*=description__text]')
             || document.querySelector('section[class*=description]');
    const crit = [...document.querySelectorAll('[class*=job-criteria__item]')]
        .map(e => e.innerText.replace(/\\s+/g, ' ').trim());
    return JSON.stringify([{
      // innerHTML chứ KHÔNG phải innerText: innerText của <ul><li> trả về
      // các dòng trần, mất dấu gạch đầu dòng — mà bộ tách yêu cầu nhận
      // diện danh sách BẰNG dấu đó. strip_html() dựng lại '· ' từ <li>.
      description: box ? box.innerHTML.slice(0, 60000) : '',
      criteria: crit.join(' | ').slice(0, 400)
    }]);
  } catch (e) { return "[]"; }
})()
"""

JOB_ID = re.compile(r"-(\d{6,})/?$")


def _pause(nhip: tuple[float, float] = PAUSE) -> None:
    time.sleep(random.uniform(*nhip))


def _from_row(row: dict) -> Posting | None:
    url = row.get("url") or ""
    found = JOB_ID.search(url)
    if not found or not row.get("title"):
        return None
    # LỖI ĐÃ SỬA: href trong kết quả tìm kiếm trỏ về tên miền theo nước
    # (uk.linkedin.com), và tên miền đó đá thẳng sang trang đăng ký — nên vòng
    # đọc kỹ chỉ nhận được "Sign Up | LinkedIn". Dựng lại URL từ id trên www.
    jid = found.group(1)
    return Posting(
        source_id=jid,
        title=row["title"].strip(),
        company=(row.get("company") or "unknown").strip(),
        location=(row.get("location") or "").strip(),
        url=VIEW.format(jid=jid),
        posted_at=row.get("posted", ""),
        payload={"guest": True})


# Thị trường trong hồ sơ -> chỗ LinkedIn hiểu. Trước đây địa điểm là chuỗi
# cứng "London" trong chữ ký hàm và KHÔNG ai truyền vào — nên ô Thị trường
# người dùng chọn chưa bao giờ đi tới đâu.
MARKET_PLACE = {
    "uk_onsite": "United Kingdom",
    "uk_remote": "United Kingdom",
    "eu_remote": "European Union",
    "us_remote": "United States",
    "global_remote": "",            # rỗng = LinkedIn tìm toàn cầu
    "relocate": "",
}


def places_for(markets: list[str], location: str = "") -> list[str]:
    """Cần tìm ở mấy nơi. Giữ thứ tự khai trong hồ sơ, bỏ trùng.

    'United Kingdom' rộng hơn 'London' và bao cả London — chọn nơi rộng hơn.
    Đo được ngày 12/09: trong 290 việc đang giữ có 75 việc ở UK ngoài London,
    và 71/75 do LinkedIn mang về. Thu câu tìm về đúng "London" là mất chỗ đó,
    vì board không phủ nổi.

    Chưa khai thị trường nào thì tìm ở NƠI BẠN Ở, không phải ở một chữ "United
    Kingdom" đóng cứng trong mã nguồn.
    """
    from ..filter import NOI, noi_o
    out: list[str] = []
    for m in markets or []:
        place = MARKET_PLACE.get(m)
        if place is not None and place not in out:
            out.append(place)
    if out:
        return out
    nha = noi_o(location)
    return [NOI[nha]["place"]] if nha else ["United Kingdom"]


# Chức danh gửi đi mỗi vòng. Có TRẦN, và trần đó được GHI RA nhật ký khi
# chạm — không cắt lặng lẽ như `titles[:5]` trước đây.
MAX_QUERIES = 20


def signed_in(tab) -> bool:
    """Profile này có đang đăng nhập LinkedIn không.

    `li_at` là cookie phiên của LinkedIn. Đọc bằng JS không thấy (httpOnly),
    nên hỏi thẳng trình duyệt qua CDP.
    """
    try:
        got = tab.call("Network.getCookies",
                       {"urls": ["https://www.linkedin.com/"]})
    except Exception:                                # noqa: BLE001
        return False
    return any(c.get("name") == "li_at" for c in got.get("cookies", []))


def read_deep(tab, items: list[Posting], skip: frozenset[str] = frozenset(),
              worth=None, pace: str = "thuong", stop=None,
              ten: str = NAME) -> Health:
    """Mở từng tin lấy MÔ TẢ. Tách khỏi fetch() vì đây là VIỆC RIÊNG.

    `ten` là tên NGUỒN đang được đọc, chỉ dùng để ghi nhật ký. Trang thì vẫn
    là trang LinkedIn, nhưng tin tới từ đâu là chuyện khác: đọc 106 tin của
    thư báo mà nhật ký ghi "linkedin: 106 tin" thì người dùng tưởng vòng quét
    LinkedIn đang chạy trong khi họ vừa tắt nó đi.

    Ba lượt quét cần ba việc khác nhau, và trước khi tách thì cả ba đều phải
    đi qua vòng tìm 30 phút:

        lần đầu    tìm đầy  -> đọc kỹ
        cập nhật   tìm mới  -> đọc kỹ
        tiếp tục   (không tìm gì cả) -> đọc nốt chỗ dở

    Cái thứ ba là lý do phải tách. "Tiếp tục" mà vẫn chạy vòng tìm thì nó chỉ
    là chữ khác của "quét lại từ đầu" — tìm lại 2.296 tin y hệt, mất 30 phút,
    để rồi đọc nốt 11 tin.

    Sửa `items` tại chỗ (gán description vào từng Posting) và trả về sức khoẻ.
    """
    nhip = NHIP.get(pace, PAUSE)
    fresh = [i for i in items if i.source_id not in skip]

    # LỌC TRƯỚC KHI ĐỌC KỸ. Đây là chỗ tốn nhất của cả vòng quét — mỗi tin một
    # lần mở trang cộng 2,5-5 giây nghỉ — mà 89% số tin mở ra sẽ bị lưới sàng
    # loại ngay sau đó. Đo trên kho thật: 2.389 tin LinkedIn, chỉ 257 tin lọt
    # lưới, tức là hơn hai tiếng mỗi lượt quét đổ đi.
    #
    # Lọc được trước vì `judge()` chỉ đụng TIÊU ĐỀ, CÔNG TY, ĐỊA ĐIỂM — ba thứ
    # trang danh sách đã đưa sẵn. Nó không cần mô tả, mà mô tả mới là thứ phải
    # mở trang mới có.
    #
    # Nhận một HÀM chứ không nhận hồ sơ: module này lo việc lấy tin, không
    # được biết gì về hồ sơ hay luật lọc. Ai gọi thì người đó quyết.
    #
    # Tin bị bỏ qua VẪN được trả về và vẫn được lưu — nhờ vậy chồng "Đã loại"
    # còn nguyên, và nút Giữ lại vẫn có cái để giữ.
    if worth is not None and fresh:
        truoc = len(fresh)
        fresh = [i for i in fresh if worth(i)]
        if truoc != len(fresh):
            jlog.emit(SEARCH,
                      f"lọc trước khi đọc kỹ: {truoc} -> {len(fresh)} tin"
                      f" · bỏ qua {truoc - len(fresh)} tin lưới sàng sẽ loại")

    health = Health(attempted=len(fresh), failed=0)
    jlog.emit(SEARCH, f"{ten}: {len(items)} tin trong tay"
                      + (f", {len(items) - len(fresh)} đã đọc từ trước"
                         f" -> chỉ đọc kỹ {len(fresh)}" if skip else
                         f", đọc kỹ cả {len(fresh)}"))
    for index, item in enumerate(fresh):
        # Điểm ngắt THẬT: đây là vòng tốn 8-16 phút, mở Chrome đọc từng tin.
        # Đặt cờ dừng ở ngoài vòng này thì bấm Dừng xong vẫn phải chờ hết.
        if stop and stop():
            jlog.warn(SEARCH, f"dừng theo yêu cầu — đã đọc kỹ {index}/{len(fresh)} tin")
            break
        # Chỗ vòng quét đứng lâu nhất — mỗi tin nghỉ 2.5-5 giây. Không báo
        # tiến độ ở đây thì màn hình im lặng suốt.
        #
        # Viết TÊN TIN đang đọc vào thanh, không chỉ "đọc kỹ LinkedIn": người
        # dùng phải thấy máy đang mở cái gì, mới biết nó còn sống.
        jlog.progress(SEARCH, f"đọc kỹ · {item.title[:44]} — {item.company[:22]}",
                      index + 1, len(fresh))
        if index and index % NHIP_BAO == 0:
            con = jlog.remaining(SEARCH)
            jlog.emit(SEARCH, f"đọc kỹ {index}/{len(fresh)} tin"
                              f"{f' · còn {con}' if con else ''}"
                              f" · đang đọc: {item.title[:40]}")
        try:
            open_page(tab, GUEST_JOB.format(jid=item.source_id), timeout=30)
            detail = grab(tab, DETAIL_JS)
            raw = detail[0].get("description", "") if detail else ""
            if len(raw) < 200:            # mở được trang nhưng không có mô tả = hỏng
                health.failed += 1
                health.note(f"{item.source_id}: mô tả rỗng")
            else:
                item.raw_body = raw[:60000]
                item.description = strip_html(raw)[:20000]
                item.payload["criteria"] = detail[0].get("criteria", "")
        except Blocked:
            # Dừng hẳn, không cãi lại — nhưng phải NÓI RA là đã dừng, và số
            # tin còn lại chưa đọc được tính vào phần hỏng. Chỉ note() rồi
            # break thì failed=0 và lần quét này trông y hệt một lần thành công.
            health.block(f"bị chặn ở tin {index + 1}/{len(fresh)}",
                         unread=len(fresh) - index)
            break
        except Exception as exc:           # noqa: BLE001
            health.failed += 1
            health.note(f"{type(exc).__name__}: {str(exc)[:44]}")
        _pause(nhip)
    return health


def fetch(tab, queries: list[str], location: str = "United Kingdom",
          levels: list[str] | None = None, pages: int = 3,
          deep: bool = True, skip: frozenset[str] = frozenset(),
          worth=None, pace: str = "thuong", recent: int = 0,
          covered: frozenset[str] = frozenset(), done_out=None,
          stop=None) -> list[Posting]:
    """Tìm rồi đọc kỹ tin LinkedIn.

    skip = id những tin ĐÃ có mô tả. Vòng đọc kỹ bỏ qua chúng.

    Đây là chỗ sửa quan trọng nhất của cả bước 1: trước đây vòng đọc kỹ mở
    lại TOÀN BỘ tin tìm được, mỗi giờ. Trên máy thật 194/196 tin đã có mô tả
    từ trước, nên 97% thời gian là đọc lại thứ đã đọc — 8-16 phút mở Chrome
    liên tục mỗi tiếng, ~4.600 lượt gọi mỗi ngày, và LinkedIn bóp lại 40-82%.
    """
    # Ranh buộc ở đầu tệp — "không có tài khoản thì không có tài khoản nào để
    # mất" — giờ do MÁY canh, không do người nhớ. Đã xảy ra một lần: cửa sổ
    # quét và cửa sổ nộp trông giống hệt nhau, đăng nhập nhầm là mỗi lần quét
    # chạy dưới tài khoản thật.
    if signed_in(tab):
        raise Blocked(
            "profile QUÉT đang đăng nhập LinkedIn — quét bằng tài khoản thật là "
            "cách mất tài khoản. Đăng xuất ở cửa sổ quét; đăng nhập ở cửa sổ NỘP.")

    if len(queries) > MAX_QUERIES:
        jlog.warn(SEARCH, f"chỉ tìm {MAX_QUERIES}/{len(queries)} chức danh"
                          f" — bỏ: {', '.join(queries[MAX_QUERIES:])}")
        queries = queries[:MAX_QUERIES]
    nhip = NHIP.get(pace, PAUSE)
    exp = ",".join(sorted({e for lv in (levels or ["grad", "junior"])
                           for e in EXPERIENCE.get(lv, "2").split(",")}))
    found: dict[str, Posting] = {}
    dut = ""                  # lý do đứt giữa chừng; rỗng = chạy trọn

    # Ghép sẵn từng cặp (chức danh, nơi) rồi chạy MỘT vòng — lồng hai vòng
    # vào nhau thì thân vòng thụt thêm một tầng và lệch cả file.
    places = location if isinstance(location, list) else [location]
    pairs = [(q, p) for q in queries for p in places]

    for step, (query, place) in enumerate(pairs, 1):
        if stop and stop():
            jlog.warn(SEARCH, f"dừng theo yêu cầu — mới xong {step - 1}/{len(pairs)} lượt tìm")
            break
        # `place` rỗng nghĩa là LinkedIn tìm toàn cầu. Để nguyên thì màn hình
        # hiện "Operations Analyst · " — một dấu chấm giữa treo lơ lửng, người
        # đọc tưởng chữ bị cắt mất.
        o_dau = place or "toàn cầu"
        # CẶP NÀY ĐÃ HỎI ĐẦY BAO GIỜ CHƯA. Chưa thì hỏi đầy; rồi thì chỉ hỏi
        # tin mới. Hai kiểu chạy được trong CÙNG một lượt, nên thêm một chức
        # danh không bắt cả lưới quét lại — chỉ mấy cặp mới là quét đầy.
        khoa = f"{query}|{place}"
        cua_so = 0 if khoa not in covered else recent
        jlog.progress(SEARCH, f"tìm LinkedIn · {query} · {o_dau}"
                              + ("" if cua_so else " · quét đầy"),
                      step, len(pairs))
        truoc, so_trang = len(found), 0
        try:
            for page in range(pages):
                url = GUEST.format(q=urllib.parse.quote(query),
                                   loc=urllib.parse.quote(place),
                                   exp=urllib.parse.quote(exp), start=page * PER_PAGE,
                                   tpr=f"&f_TPR=r{cua_so}" if cua_so else "")
                open_page(tab, url, timeout=30)
                rows = grab(tab, LIST_JS)
                if not rows:
                    break
                so_trang += 1
                for row in rows:
                    item = _from_row(row)
                    if item:
                        found.setdefault(item.source_id, item)
                _pause(nhip)
        except Exception as exc:                     # noqa: BLE001
            # ĐỨT GIỮA CHỪNG THÌ GIỮ LẠI THỨ ĐÃ TÌM ĐƯỢC, không ném lên trên.
            #
            # Trước đây lỗi ở đây bay thẳng ra ngoài fetch(), nên `items` không
            # bao giờ trả về và save_batch() không bao giờ chạy: cả kho tin đã
            # tìm được đổ đi sạch. Xảy ra thật lúc 17:18 — 48/76 lượt tìm xong,
            # một ConnectionResetError, fetched=0.
            #
            # Máy ngủ dậy là đúng cái lỗi này: socket CDP chết, mà app chạy
            # 24/7 nên chuyện đó là chuyện thường ngày, không phải tai nạn.
            dut = f"{type(exc).__name__}: {str(exc)[:50]}"
            jlog.warn(SEARCH, f"đứt ở lượt {step}/{len(pairs)} ({dut})"
                              f" — giữ lại {len(found)} tin đã tìm được")
            break
        # MỘT DÒNG CHO MỖI LƯỢT TÌM. Trước đây cả vòng này im lặng: đo trên
        # lượt quét 19:22 là 31 phút chạy mà nhật ký để lại đúng một dòng ở
        # đầu. Người dùng ngồi nhìn một thanh tiến độ nhích, không biết máy
        # đang gõ chức danh nào, ở đâu, được gì.
        # Cặp này vừa được hỏi ĐẦY và chạy trọn -> ghi nhận đã phủ. Chỉ ghi
        # khi cua_so == 0: một lượt hỏi cửa sổ 24 giờ không phủ được cặp nào,
        # nó chỉ liếc phần mới nhất.
        if done_out is not None and not cua_so:
            done_out.add(khoa)
        con = jlog.remaining(SEARCH)
        jlog.emit(SEARCH,
                  f"tìm · {query} · {o_dau} — {len(found) - truoc} tin mới"
                  f" / {so_trang} trang · kho {len(found)}"
                  f"{'' if cua_so else ' · đã phủ'}"
                  f"{f' · còn {con}' if con else ''}")

    if not deep or dut:
        # Đứt rồi thì đừng đọc kỹ nữa: cổng vừa từ chối mình xong, mở tiếp
        # 2.000 trang chỉ để nhận 2.000 lỗi. Trả tin về cho save_batch ghi
        # xuống, lần quét sau đọc kỹ tiếp — save_batch vá mô tả vào đúng dòng
        # cũ, nên chỗ dở không thành lỗ hổng.
        suc = Health(0, 0)
        if dut:
            suc.broke(f"đứt khi đang tìm: {dut}")
        return list(found.values()), suc

    health = read_deep(tab, list(found.values()), skip=skip, worth=worth,
                       pace=pace, stop=stop)
    return list(found.values()), health

