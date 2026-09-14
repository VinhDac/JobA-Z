# Auto Job Manage

Hệ thống tìm việc chạy liên tục — **máy đề xuất, người quyết định.**

Trạng thái: **App macOS chạy nền 24/7** · **Bước 1 xong** — 3.000+ tin thật, lọc còn 20 việc.
Bước 2–6 (chấm điểm, CV, project, gửi, theo dõi) chưa làm.

## Chạy

```bash
python3 scripts/make_app.py && python3 scripts/install_agent.py
```

Lệnh đầu dựng `jobbot.app`. Lệnh sau cài nó thành dịch vụ — **bật máy là tự chạy**,
crash thì tự bật lại.

Đây là **app macOS thật**, không phải tab trình duyệt:

- Cửa sổ riêng (`NSWindow` + `WKWebView`) — không thanh URL, không tab
- Icon ở Dock, cmd-tab được, có ở Launchpad
- Icon `◆` trên thanh menu: trạng thái, Open jobbot, Scan now, Quit
- **Đóng cửa sổ thì ẩn, app vẫn chạy nền** — giống Discord. Chỉ Quit mới thoát hẳn
- Tự quét mỗi 60 phút, có việc mới thì báo qua thông báo macOS

Không cần cài gì thêm, không venv — **Python 3.11 trở lên** là đủ.

PyObjC **không** có sẵn trên macOS: `/usr/bin/python3` (3.9.6) không có nó,
và bản đó cũng quá cũ so với 3.11. Có PyObjC (Anaconda, hoặc `pip install
pyobjc`) thì được cửa sổ macOS thật; không có thì app tự lùi về cửa sổ Chrome
`--app` — vẫn là cửa sổ riêng, không thanh địa chỉ. WebKit nạp động lúc chạy.

App tự đi tìm Python lúc khởi động (`scripts/tim-python.sh`) nên không phụ
thuộc bản đã dựng bằng. Máy có Python ở chỗ lạ thì chỉ tay:
`export JOBBOT_PYTHON=/duong/dan/toi/python3`.

| Lệnh | Làm gì |
|---|---|
| `open jobbot.app` | Mở app |
| `./start.command` | Bấm đúp cũng được — đang chạy thì chỉ mở dashboard |
| `python3 run.py` | Chạy trực tiếp, không qua bundle |
| `python3 run.py --window` | Chạy trong Terminal, thấy log, Ctrl+C dừng |
| `python3 run.py --scan` | Quét một lần rồi thoát |
| `python3 scripts/install_agent.py --status` | Xem dịch vụ đang chạy không |
| `python3 scripts/install_agent.py --uninstall` | Gỡ dịch vụ |

Test: `python3 tests/run_all.py` (chạy hết mọi bài)

---

## Đọc theo thứ tự

| | File | Nội dung |
|---|---|---|
| 1 | [docs/strategy.md](docs/strategy.md) | *Vì sao.* Bản chất bài toán xin việc. Đọc trước tiên. |
| 2 | [docs/design.md](docs/design.md) | *Làm thế nào.* Vòng lặp đề xuất, trục an toàn, cache, stack. |
| 3 | [docs/roadmap.md](docs/roadmap.md) | *Theo thứ tự nào.* 11 module, mỗi cái có tiêu chí "Xong khi". |

## Ý tưởng trong một khung

```
module  ->  đề xuất  ->  hàng đợi  ->  bạn bấm Yes/No  ->  thực thi  ->  ghi kết quả
```

Mọi module đều đẻ ra cùng một kiểu object. Vì vậy dashboard chỉ vẽ một thứ,
cổng duyệt chỉ viết một lần, và thêm module mới thì lõi không phải sửa.

**Hai luật không được phá:**

1. Module chỉ **đề xuất**. Lõi mới **thực thi**.
2. Mọi hành động **không đảo ngược được** đều phải qua một lần bấm của người.

## Bản đồ thư mục

```
docs/                 Tài liệu. Quyết định nằm ở đây, không nằm trong đầu.
config/               config.example.toml -> copy thành config.toml (đã gitignore)
src/jobbot/
  profile/      M0     Hồ sơ người dùng: là ai, muốn gì, KHÔNG nhận gì
  core/         M1,M6  Kiểu dữ liệu, store, cache, hàng đợi, cổng Yes/No, thực thi
  ingest/       M2     Kéo tin về. Một file một nguồn.
  dedup/        M3     Gộp tin trùng
  dashboard/    M4     8 trang giao diện — xem live, bấm Yes/No
    layout.py          khung chung: nav, thẻ, huy hiệu, thanh điểm
    mock.py            DỮ LIỆU GIẢ = hợp đồng backend phải khớp
    views/             một file một trang
  scoring/      M5     Chấm điểm CV <-> JD
  cv/           M7     Dựng CV theo JD  [Yes/No]
  mail/         M8     Gửi hồ sơ, đọc phản hồi  [Yes/No khi gửi]
  notify/       M9     Báo ra ngoài
  stats/        M10    Đếm, đo, tỉ lệ phản hồi
  outreach/     M11    Profile, bài đăng, kết nối  [Yes/No — rủi ro cao nhất]
tests/                Test theo module
scripts/              Lệnh chạy tay, việc một lần
data/                 DB + cache. KHÔNG commit.
```

Mỗi thư mục con trong `src/jobbot/` có `__init__.py` ghi rõ **cái gì thuộc về nó và cái gì không**.
Đọc dòng đó trước khi thêm file. Không biết file mới nên nằm đâu → nghĩa là chưa rõ nó làm gì.

## Luật giữ sạch

- Một nguồn dữ liệu = một file trong `ingest/`. Không nhồi hai nguồn vào một file.
- Không có logic nghiệp vụ trong `dashboard/`. Nó chỉ vẽ.
- `core/` không được biết Greenhouse hay LinkedIn là gì.
- Thử nghiệm, việc chạy một lần → `scripts/`. Không để rơi ở thư mục gốc.
- Quyết định gì thì ghi vào `docs/`, không để trong chat.
- Xong một module thì tick vào `roadmap.md` — nhưng chỉ khi đạt đúng "Xong khi".

## Việc tiếp theo

Lát 0 — mở bài: **M0 — hồ sơ người dùng.** Chưa xong cái này thì chưa kéo tin nào về.

Hệ thống phải biết: tuyển vai trò gì · băng tần nào · thị trường nào · nguyên liệu
CV có gì · và quan trọng nhất là **KHÔNG nhận cái gì**.

Thiếu nó thì ingest kéo về rác, scoring chấm điểm dựa trên không khí.

Xong M0 mới tới lát 1 — xương sống: **M1 → M2 → M3 → M4**.

## Còn thiếu để đi tiếp

Xem cuối [docs/strategy.md](docs/strategy.md): cần **băng tần thật** và **2–3 JD thật**
để ngược từ JD ra project, thay vì xây trước rồi tìm chỗ nhét vào.
