#!/bin/bash
# Bấm đúp để mở jobbot.  (macOS)
# Đang chạy   -> chỉ mở dashboard, KHÔNG khởi động lượt thứ hai
# Chưa chạy   -> khởi động ngầm (icon ◆ trên thanh menu) rồi mở dashboard
#
# Không hỏi cổng 8765 nữa. Cổng do hệ điều hành cấp (xem server.serve), nên
# nó đổi theo từng lượt chạy; app đang sống ở 8766 mà kịch bản này gõ 8765
# thì nó kết luận "chưa chạy" và bật lượt thứ hai đè lên cùng một tệp SQLite.
# Địa chỉ thật nằm ở data/dang-chay.txt — xem src/jobbot/core/dia_chi.py.

cd "$(dirname "$0")" || exit 1

keu() {          # hỏng thì PHẢI kêu. Bấm đúp mà im lặng là kiểu hỏng tệ nhất.
  osascript -e "display alert \"jobbot\" message \"$1\"" >/dev/null 2>&1
  echo "$1" >&2
  exit 1
}

# Có đúng jobbot đang trả lời ở địa chỉ này không. "Có ai đó trả lời 200"
# không đủ: cổng cũ có thể đã thuộc về app khác.
con_song() {
  [ -n "$1" ] || return 1
  curl -sf --max-time 2 "${1}api/alive" 2>/dev/null | grep -q '^jobbot '
}

URL=""
[ -f data/dang-chay.txt ] && URL="$(head -n 1 data/dang-chay.txt)"

if con_song "$URL"; then
  open "$URL"; exit 0
fi

# Lượt cũ để lại tệp mà không còn sống (kill -9, mất điện). Bỏ qua, chạy mới.
. scripts/tim-python.sh
[ -n "$PY" ] || keu "$THIEU_PYTHON"

mkdir -p data
nohup "$PY" run.py > data/app.log 2>&1 &

for _ in $(seq 1 40); do
  [ -f data/dang-chay.txt ] && URL="$(head -n 1 data/dang-chay.txt)"
  con_song "$URL" && break
  sleep 0.4
done

if con_song "$URL"; then
  open "$URL"
else
  keu "Khởi động không thành công.

Xem: $(pwd)/data/app.log"
fi
