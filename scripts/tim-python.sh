# Tìm một Python >= 3.11.  Dùng:  . scripts/tim-python.sh   ->  $PY
#
# MỘT BẢN DUY NHẤT, hai nơi dùng: start.command (bấm đúp) và vỏ jobbot.app.
# Chép làm hai thì sớm muộn sẽ lệch, và lệch ở đây nghĩa là bấm đúp thì mở
# được mà bấm icon thì không — không ai đoán ra vì sao.
#
# Vì sao không chỉ gõ `python3`: máy này `/usr/bin/python3` là 3.9.6 (đo thật),
# mà app cần 3.11 trở lên (tomllib). PATH của Finder cũng không phải PATH của
# Terminal — thứ gõ được trong terminal có thể không thấy lúc bấm đúp. Nên
# phải HỎI TỪNG CÁI xem nó mấy chấm mấy, chứ không tin vào cái tên.

PY=""
for _ung_vien in \
    "$JOBBOT_PYTHON" \
    "$(command -v python3)" \
    "$(command -v python3.13)" "$(command -v python3.12)" "$(command -v python3.11)" \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /opt/anaconda3/bin/python3 "$HOME/anaconda3/bin/python3" \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3
do
  [ -n "$_ung_vien" ] && [ -x "$_ung_vien" ] || continue
  if "$_ung_vien" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$_ung_vien"
    break
  fi
done
unset _ung_vien

# Câu để nói với người dùng khi không tìm thấy. Cùng một câu ở cả hai nơi.
THIEU_PYTHON="Không tìm thấy Python 3.11 trở lên.

Cài bằng:  brew install python@3.12
Hoặc tải ở python.org

Đã có sẵn một bản rồi thì chỉ nó ra:
  export JOBBOT_PYTHON=/duong/dan/toi/python3"
