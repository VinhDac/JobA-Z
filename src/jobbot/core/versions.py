"""Phiên bản của các bộ luật.

Đổi luật thì ĐỔI SỐ Ở ĐÂY. Tin nào được phán bằng phiên bản cũ sẽ tự động
được tính lại ở lần quét sau.

Không có cơ chế này thì: sửa vocab.py xong, điểm cũ và điểm mới nằm lẫn trong
cùng một bảng, không cách nào biết cái nào tính bằng luật nào.
"""

# 2026-09-12.1 — "chỗ mình" suy từ ô hồ sơ "Where you're based" thay vì đóng
# cứng UK, + chốt chặn mã bang Mỹ cho tên thành phố đụng nhau (Birmingham, AL).
FILTER_RULES = "2026-09-12.1"  # ingest/filter.py + ingest/base.norm_*
# scoring/vocab.py + scoring/extract.py + scoring/score.py + realism + deadline
# 2026-09-12.4 — (a) norm() giữ `+ # /` và ranh giới alias đổi từ \b sang
# (?<!\w)/(?!\w): trước đó "C++" bị chuẩn hoá thành "c" nên 208 tin đòi C++
# không bao giờ khớp, dù CV CÓ C++. (b) bỏ search_keywords/stack_want khỏi chỉ
# số bằng chứng — nhãn tự khai "(not proof)" mà vẫn cho 249 dòng ở 153 tin
# tính là ĐẠT. Điểm sẽ tụt; đó là điểm thật.
SCORE_RULES = "2026-09-12.4"
# cv/rules.py + cv/build.py + cv/rewrite.py. Bản dựng CV được LƯU xuống đĩa
# (bảng cv_build), nên đổi luật viết CV mà không đổi số ở đây thì bản cũ nằm
# lại và không ai biết nó được dựng bằng luật nào.
#
# 2026-09-12.1 — bộ dựng bắt đầu HỎI rules.sentence_ok (trước đó không hỏi, và
# 3 câu bị cấm đi ra ngoài trên mọi bản), + cv/rewrite.py lược chủ ngữ ngôi 1.
# 2026-09-12.2 — dòng "Bản sẽ gửi" tính phủ trên TIN ĐẦU ĐÀN thay vì trên
# hợp cả nhóm (hợp thì đo kích thước nhóm, không đo chất lượng CV).
CV_RULES = "2026-09-12.2"
