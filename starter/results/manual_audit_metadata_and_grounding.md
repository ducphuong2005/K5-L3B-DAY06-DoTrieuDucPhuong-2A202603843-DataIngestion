# Audit Thủ công — Tiêu chí 3 (Metadata Usefulness) & Tiêu chí 4 (Grounding Quality)

- **Người chấm:** Đỗ Triệu Đức Phương (`2A202603843` — tác giả bài lab đối chiếu thủ công từng bản ghi Top-3 với file PDF gốc).
- **Phạm vi kiểm tra:** Toàn bộ **5 câu hỏi tập `test` (`q16`–`q20`) × Top-3 chunks = 15 bản ghi** cho mỗi chiến lược.
- **Thang điểm Grounding Quality (0–2):** `0` = không có bằng chứng; `1` = có một phần bằng chứng nhưng bị cắt mất chi tiết/điều kiện do ranh giới chunk hoặc ranh giới trang; `2` = đủ bằng chứng nguyên vẹn để trả lời và truy vết chính xác trang nguồn.

## Tiêu chí 3: Bảng kiểm tra tính đúng đắn & hữu dụng của Metadata (Tập Test)

| Strategy | Số bản ghi Top-3 đã kiểm tra | Metadata đủ và đúng (`source`, `page`, `section`) | Số câu Test có Filter | Tỷ lệ Top-3 tuân thủ Filter |
|---|---:|---:|---:|---:|
| **A** | 15 | **15/15** (100.0%) | 2 (`q17`, `q19`) | Test: **2/2** (Dev: **0/3**) |
| **B** | 15 | **15/15** (100.0%) | 2 (`q17`, `q19`) | Test: **1/2** (Dev: **0/3**) |
| **C** | 15 | **15/15** (100.0%) | 2 (`q17`, `q19`) | Test: **2/2** (Dev: **3/3**) |

### Giải thích tính hữu dụng và hạn chế của Metadata:
- **Trường giúp truy vết & lọc phạm vi:** Ba trường `document_id` (`hp1-ch1-4`), `source` (`starter/data/harrypotter.pdf`) và `page` (`12..61`) giúp đối chiếu chính xác tuyệt đối vị trí trích dẫn trên PDF (đạt `15/15` bản ghi đúng trên tập `test` và `45/45` trên tập `dev`). Trường bổ sung `section` (`chapter_1`..`chapter_4`) giúp thu hẹp phạm vi truy vấn theo đúng chương khi câu hỏi có ngữ cảnh chương: nhờ lọc SQL `metadata ->> 'section'`, Chiến lược C nâng tỷ lệ tuân thủ filter trên tập `dev` từ `0/3` (ở A và B) lên `3/3` (giúp `q02` và `q14` lên Top-1), và trên tập `test` từ `1/2` (ở B, bị lọt trang 14 thuộc Chương 1 vào Top-3 của `q19`) lên `2/2`.
- **Hạn chế của Metadata hiện tại:** (1) Trường `section` ở mức chương (11–14 trang/chương) vẫn còn khá rộng nên chưa phân biệt được các đoạn văn bị ngắt qua ranh giới hai trang liên tiếp trong cùng một chương (như `q17` giữa trang 26 và 27 thuộc `chapter_2`); (2) Việc lọc theo `section` đòi hỏi hệ thống/người dùng phải biết trước phạm vi chương từ ngữ cảnh hội thoại hoặc giao diện điều hướng.

## Tiêu chí 4: Bảng tổng hợp Grounding Quality (Tập Test, 5 câu hỏi mỗi chiến lược)

| Strategy | Mức 0 (Không có bằng chứng) | Mức 1 (Thiếu chi tiết / bị cắt qua ranh giới) | Mức 2 (Đủ bằng chứng & truy được nguồn) | Điểm Grounding trung bình (/2) |
|---|---:|---:|---:|---:|
| **A** | 0 | 2 | 3 | **1.60 / 2.00** |
| **B** | 0 | 1 | 4 | **1.80 / 2.00** |
| **C** | 0 | 1 | 4 | **1.80 / 2.00** |

## Bảng chấm thủ công chi tiết từng câu hỏi Test (`q16`–`q20`)

| Strategy | Câu hỏi | Trang vàng | Các trang Top-3 trả về | Hit@1 | Evidence Hit@3 | Điểm Grounding (/2) | Nhận xét chấm thủ công (Manual Rationale) |
|---|---|---:|---|---|---|---|---|
| **A** | `q16` | p.44 | `[44, 44, 43]` | `False` | `False` | **1** | Top-3 lấy đúng trang vàng p.44 ở hạng 1 và 2 (fixed_03, fixed_02), nhưng câu bằng chứng về 24 lá thư giấu trong 2 tá trứng nằm sát cuối cửa sổ fixed_03 (ký tự 1350–1850) và bị cắt ở mốc 1850, nên không chunk nào trong Top-3 chứa trọn câu. |
| **A** | `q17` | p.27 | `[26, 32, 32]` | `False` | `False` | **1** | Top-3 trả về p.26 (cuối trang có câu Harry cố nhớ lại giấc mơ) và p.32 (Harry kể lại giấc mơ có chiếc mô-tô bay), nhưng thiếu đầu trang p.27 nơi nêu đầy đủ cả chiếc mô-tô bay lẫn cảm giác đã mơ giấc mơ này trước đó. |
| **A** | `q18` | p.52 | `[52, 52, 52]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p052_fixed_01, p.52) chứa đầy đủ danh sách các vật dụng Hagrid lấy từ túi áo khoác (ấm đồng, gói xúc xích, que cời lửa, ấm trà, cốc sứt và chai rượu màu hổ phách) cùng nguồn trang chính xác. |
| **A** | `q19` | p.55 | `[55, 54, 55]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p055_fixed_00, p.55) chứa nguyên văn bức thư của Phó Hiệu trưởng Minerva McGonagall ghi rõ ngày khai giảng 1/9 và hạn chót gửi cú phản hồi trước 31/7. |
| **A** | `q20` | p.61 | `[61, 61, 56]` | `True` | `True` | **2** | Chunk hạng 2 (hp1-ch1-4_p061_fixed_03, p.61) chứa trọn vẹn lời giải thích của Hagrid về việc ông bị đuổi học năm thứ ba, bị bẻ gãy đũa phép và được Dumbledore cho ở lại làm người giữ khóa. |
| **B** | `q16` | p.44 | `[44, 44, 43]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p044_para_02, p.44) giữ nguyên cả đoạn văn mô tả 24 lá thư được cuộn tròn giấu trong 2 tá trứng do người giao sữa đưa cho dì Petunia qua cửa sổ phòng khách. |
| **B** | `q17` | p.27 | `[32, 26, 35]` | `False` | `False` | **1** | Top-3 trả về [p.32, p.26, p.35]: có thông tin Harry mơ thấy mô-tô bay (p.32) và chi tiết thức dậy cố nhớ lại giấc mơ (cuối p.26), nhưng do đoạn văn bị ngắt qua trang PDF p.26->p.27 nên thiếu câu đầu trang p.27 về cảm giác đã mơ giấc mơ này trước đây. |
| **B** | `q18` | p.52 | `[52, 50, 52]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p052_para_01, p.52) chứa trọn vẹn đoạn văn liệt kê toàn bộ đồ vật Hagrid lấy từ túi áo khoác và chi tiết nướng xúc xích, đủ bằng chứng trả lời và truy vết nguồn. |
| **B** | `q19` | p.55 | `[55, 54, 14]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p055_para_00, p.55) chứa đầy đủ nội dung thư của Giáo sư McGonagall (khai giảng 1/9, hạn gửi cú 31/7), tuy nhiên ở hạng 3 bị lọt chunk p.14 (chapter_1) do không dùng filter. |
| **B** | `q20` | p.61 | `[61, 60, 56]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p061_para_01, p.61) chứa đầy đủ đoạn hội thoại Hagrid thú nhận bị đuổi học năm thứ ba, bị bẻ đũa phép và được Dumbledore giữ lại làm gamekeeper. |
| **C** | `q16` | p.44 | `[44, 44, 43]` | `True` | `True` | **2** | Câu hỏi không có filter nên Chiến lược C giữ nguyên kết quả của B: chunk hạng 1 (hp1-ch1-4_p044_para_02, p.44) cung cấp đầy đủ bằng chứng về 24 lá thư giấu trong 2 tá trứng. |
| **C** | `q17` | p.27 | `[32, 26, 35]` | `False` | `False` | **1** | Filter section=chapter_2 được tuân thủ 3/3 chunk ([p.32, p.26, p.35]), cung cấp được chi tiết mô-tô bay (p.32) và lúc mới ngủ dậy (p.26), nhưng thiếu câu đầu trang p.27 do đoạn văn bị ngắt qua ranh giới trang PDF. |
| **C** | `q18` | p.52 | `[52, 50, 52]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p052_para_01, p.52) cung cấp đầy đủ danh sách các món đồ trong túi áo của Hagrid và ngữ cảnh nấu trà, nướng xúc xích. |
| **C** | `q19` | p.55 | `[55, 54, 55]` | `True` | `True` | **2** | Nhờ filter section=chapter_4, cả 3 chunk Top-3 đều thuộc Chương 4 ([p.55, p.54, p.55]), và chunk hạng 1 (hp1-ch1-4_p055_para_00) chứa đầy đủ ngày khai giảng 1/9 cùng hạn phản hồi 31/7. |
| **C** | `q20` | p.61 | `[61, 60, 56]` | `True` | `True` | **2** | Chunk hạng 1 (hp1-ch1-4_p061_para_01, p.61) chứa trọn vẹn lời giải thích của Hagrid về lý do không được phép dùng phép thuật và việc bị đuổi học năm thứ ba. |
