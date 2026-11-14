# Báo cáo cá nhân — Day 6

**Học viên:** Đỗ Triệu Đức Phương · **MSSV:** 2A202603843 · **Lớp:** L3B

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  Corpus là bốn chương đầu của *Harry Potter and the Sorcerer's Stone* (J.K. Rowling), lấy từ file `starter/data/harrypotter.pdf` (bản tuyển tập, 3.623 trang vật lý). Đây là tác phẩm có bản quyền nên tôi chỉ dùng cục bộ cho mục đích học tập; file PDF không được đưa lên repo (đã thêm vào `.gitignore`), người chấm có thể đối chiếu qua `data/manifest.json`. Tôi kiểm tra 61 trang vật lý đầu và loại 11 trang: 7 trang bìa/trang trống không trích được chữ (trang 1–5, 7, 8), 3 trang mục lục (6, 10, 11) và trang đề tặng (9). Phần còn lại là **50 trang nội dung (trang 12–61)**, tổng cộng 87.235 ký tự sau chuẩn hóa. Danh sách trang, lý do loại và số ký tự từng trang được ghi trong manifest và `results/ingestion_log.json`.

- **Chuẩn hóa, lỗi và giới hạn:**
  File PDF có hai lỗi định dạng đáng chú ý: khoảng trắng giữa các từ bị lưu thành ký tự tab, và chữ cái đầu chương (drop-cap, cỡ 68pt) bị tách khỏi phần còn lại của từ (ví dụ "M" … "r. and Mrs. Dursley"). Tôi dùng `pypdf` với `visitor_text` để lấy tọa độ và cỡ chữ của từng dòng, từ đó ghép lại drop-cap, nhận diện ranh giới đoạn văn qua thụt lề và khoảng cách dòng, rồi chuẩn hóa Unicode về NFC. Giới hạn còn lại là câu văn bị ngắt giữa hai trang vật lý: vì mỗi trang được xử lý độc lập để giữ số trang chính xác, phần đầu trang thường bắt đầu bằng một mẩu câu thiếu chủ ngữ.

- **Embedding model, vector store, metric, lệnh chạy và chi phí:**
  Model `text-embedding-3-small` (1.536 chiều), gọi qua API tương thích OpenAI của ShopAI (`https://api.shopaikey.com/v1`); query và document được embed theo cùng một cách, không thêm tiền tố. Vector store là PostgreSQL 16 + pgvector (image `pgvector/pgvector:0.8.7-pg16`), bảng `rag_chunks` với khóa chính `(strategy, chunk_id)`, tìm kiếm chính xác (exact) bằng khoảng cách cosine `<=>`. Lệnh chạy: `cd starter && python -m src.run`. Lần chạy chính thức dùng 33 request, 44.421 token, chi phí ước tính **\$0,000888** (tính theo đơn giá công bố \$0,02/1M token của OpenAI; hóa đơn thực tế của ShopAI có thể khác).

- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  Mỗi chunk có `document_id` (`hp1-ch1-4`), `source` (đường dẫn file) và `page` (số trang PDF, 12–61). Trường lọc bổ sung là `section` (`chapter_1` … `chapter_4`, kiểu chuỗi), lấy trực tiếp từ tiêu đề "CHAPTER ONE … FOUR" ở các trang 12, 26, 37, 50. Tôi chọn `section` vì truyện có nhiều mô-típ lặp lại giữa các chương (Dudley ăn vạ, những lá thư, chuyện cha mẹ Harry), nên phạm vi chương là thông tin có thật trong nguồn và hữu ích để thu hẹp tìm kiếm. Ngoài ra còn có `chapter_title`, `page_id`, `char_start`/`char_end` để truy vết.

## Cấu hình và benchmark

- **A / B / C:**
  - **A:** `fixed_size(size=500, overlap=50)` → 219 chunk (trung bình 436,9 ký tự), không lọc.
  - **B:** `by_paragraph(max_size=900)`, gom đoạn văn liền nhau tới 900 ký tự, tách đoạn quá dài theo ranh giới câu → 134 chunk (trung bình 649,8 ký tự), không lọc.
  - **C:** dùng đúng chunk và vector của B; **khác biệt duy nhất** là khi câu hỏi có filter, truy vấn SQL thêm điều kiện `metadata ->> 'section' = %s` trước khi xếp hạng. Với câu không có filter, C chạy không lọc và cho kết quả giống hệt B.

- **Bộ câu hỏi và cách kiểm chứng evidence:**
  20 câu tiếng Anh (`benchmark/questions.json`), chia trước **15 dev (q01–q15) / 5 test (q16–q20)**, gồm câu trực tiếp, diễn đạt lại, câu nhiều chi tiết/điều kiện và câu cần lọc metadata. Có **5 câu có filter `section`**: 3 câu dev (q02, q09, q14) và 2 câu test (q17, q19). Mỗi câu ghi `expected_answer`, `gold_source_id`, `gold_page`, `evidence_quote`. Trước khi chạy, script tạo benchmark kiểm tra bằng `assert` rằng từng `evidence_quote` xuất hiện nguyên văn trong trang gold sau chuẩn hóa; cả 20 câu đều đạt. Giá trị filter mô phỏng ngữ cảnh người dùng cung cấp trước (ví dụ đang đọc chương nào), không lấy từ đáp án.

- **Tiêu chí chọn chiến lược (chốt trước khi xem test):**
  Ưu tiên lần lượt: (1) Evidence Hit@3 trên dev, (2) Hit@1 trên dev, (3) coherence và tỷ lệ tuân thủ filter, (4) số chunk và chi phí.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 8/15 | 12/15 | 219 | 23,50 s | \$0,000461 |
| A | test | 3/5 | 3/5 | 219 | 23,50 s | \$0,000461 |
| B | dev | 10/15 | 14/15 | 134 | 13,74 s | \$0,000418 |
| B | test | 4/5 | 4/5 | 134 | 13,74 s | \$0,000418 |
| C | dev | 12/15 | 15/15 | 134 | 13,74 s* | \$0,000418* |
| C | test | 4/5 | 4/5 | 134 | 13,74 s* | \$0,000418* |

*Thời gian là thời gian embed + ghi vào pgvector, đo một lần. C tái sử dụng vector của B nên không tốn thêm chi phí embedding; riêng bước ghi của C mất 0,25 s. Đọc và chuẩn hóa PDF mất 6,56 s, dùng chung cho cả ba cấu hình. Nạp lại lần hai không sinh bản ghi trùng (A: 219 → 219, B và C: 134 → 134).*

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 0,60 (n=10) | 15/15 | dev 0/3 · test 2/2 | 0 / 2 / 3 → 1,60 |
| B | 1,70 (n=10) | 15/15 | dev 0/3 · test 1/2 | 0 / 1 / 4 → 1,80 |
| C | 1,70 (n=10) | 15/15 | dev 3/3 · test 2/2 | 0 / 1 / 4 → 1,80 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:** Trace top-3 đầy đủ của 60 lượt truy vấn nằm trong `results/traces.json`; số liệu tổng hợp ở `results/metrics_summary.json`; nhãn thủ công ở `results/manual_labels.json`, kèm bảng diễn giải `results/manual_audit_coherence.md` và `results/manual_audit_metadata_and_grounding.md`. Mẫu coherence được cố định trước khi xem điểm: 10 trang nội dung đầu (`p012`–`p021`), lấy chunk chứa ký tự thứ 460 của mỗi trang. Grounding được chấm trên cả 5 câu test × top-3. Cột metadata kiểm tra `source`, `page`, `section` của 15 bản ghi test bằng script đối chiếu với manifest. Người chấm là tác giả; bản nháp nhận xét được soạn với sự hỗ trợ của trợ lý AI và tác giả đã đọc lại từng chunk để xác nhận, nên vẫn có nguy cơ thiên lệch của người chấm duy nhất.

## Phân tích và kết luận

- **So sánh A–B (chỉ đổi cách chunk):** Chunk theo đoạn tốt hơn rõ rệt: Hit@1 dev tăng từ 8/15 lên 10/15, Evidence Hit@3 dev từ 12/15 lên 14/15; trên test cả hai chỉ số tăng từ 3/5 lên 4/5. Nguyên nhân chính là A có 4 câu tìm đúng trang nhưng bằng chứng bị cắt ngang ranh giới cửa sổ (q03, q06, q10, q16), còn B không có trường hợp nào. Coherence tăng từ 0,60 lên 1,70: cả 10 chunk của A đều bị cắt giữa câu hoặc giữa từ ở cuối (ví dụ "…said Professor Mc" ở trang 20), trong đó 4 chunk còn mở đầu bằng mẩu câu thiếu chủ ngữ nên bị chấm 0; B không có chunk nào điểm 0. B cũng gọn hơn, với ít hơn 38,8% chunk, ít token hơn và ingest nhanh hơn. Tuy vậy B không thắng tuyệt đối: ở q01, A xếp trang 12 ở hạng 1 còn B xếp trang 14 lên trước, có lẽ vì chunk ngắn của A tập trung hơn vào câu về Grunnings.

- **So sánh B–C (chỉ thêm filter):** Trên 15 câu không có filter, hai cấu hình cho kết quả giống hệt nhau, nên mọi khác biệt đều đến từ filter. Tỷ lệ tuân thủ filter trên dev tăng từ 0/3 lên 3/3, Hit@1 dev từ 10/15 lên 12/15, Evidence Hit@3 dev từ 14/15 lên 15/15. Trên test, Hit@3 không đổi (4/5), nhưng ở q19, B để lọt một chunk của chương 1 (trang 14) vào hạng 3, còn C giữ cả ba kết quả trong chương 4.

- **Ví dụ sai 1 — q16 (test, `hp1-ch1-4`, trang 44), cấu hình A:** Hai kết quả đầu đều thuộc đúng trang 44 (`p044_fixed_03`, score 0,6218; `p044_fixed_02`, score 0,5831) nhưng không chunk nào chứa trọn câu về 24 lá thư giấu trong hai tá trứng, vì câu này nằm sát cuối cửa sổ 1350–1850 và bị cắt ở ký tự 1850. B và C lấy được `p044_para_02` ở hạng 1 (score 0,6585) với câu bằng chứng nguyên vẹn.

- **Ví dụ sai 2 — q02 (dev, `hp1-ch1-4`, trang 13), cấu hình B:** Câu hỏi về cơn ăn vạ của Dudley trong bữa sáng. Không có filter, B trả về các trang 43 (chương 3), 28 và 27 (chương 2), vì những cảnh Dudley làm mình làm mẩy bên bàn ăn ở các chương sau dài hơn và giàu từ khóa hơn câu ngắn ở trang 13. Khi lọc `section = chapter_1`, C đưa trang 13 lên hạng 1.

- **Một lỗi chung của cả ba cấu hình — q17 (test, trang 27):** Đoạn văn về giấc mơ bắt đầu ở cuối trang 26 và kết thúc ở đầu trang 27. Cả ba cấu hình chỉ lấy được trang 26 và trang 32 (nơi Harry kể lại giấc mơ về chiếc mô-tô bay), không lấy được câu trả lời đầy đủ ở trang 27. Đây là hệ quả trực tiếp của việc chunk theo từng trang.

- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:** Theo tiêu chí đã chốt, tôi chọn **C**: đứng đầu cả Evidence Hit@3 dev (15/15) lẫn Hit@1 dev (12/15), coherence ngang B và cao nhất, tuân thủ filter 5/5. Kết quả test (4/5, grounding 1,80/2) phù hợp với dev. Đánh đổi là C chỉ có lợi khi phạm vi chương được biết trước từ ngữ cảnh; nếu không có filter, C hoạt động như B. Nếu người dùng cung cấp sai chương, filter sẽ loại luôn đáp án đúng, một rủi ro mà B không gặp.

- **Hạn chế:** (1) Tập test chỉ có 5 câu, mỗi câu tương ứng 20%, nên kết quả chỉ minh họa trên corpus này chứ không đủ để khái quát. (2) Corpus là văn xuôi hư cấu của một tác giả, cấu trúc đơn giản; trường `section` ở cấp chương còn thô. (3) Nhãn coherence và grounding do một người chấm. (4) Thời gian chỉ đo một lần và phụ thuộc độ trễ mạng tới API; chi phí là ước tính theo đơn giá công bố. (5) Tỷ lệ tuân thủ filter 2/2 của A trên test chỉ là trùng hợp do câu hỏi đủ đặc trưng, không phải do A có cơ chế lọc.

- **Nếu làm lại hoặc mở rộng:** Tôi sẽ cho phép nối đoạn văn bị ngắt giữa hai trang và lưu `page_start`/`page_end` để vừa giữ khả năng truy vết vừa xử lý được những trường hợp như q17. Tôi cũng muốn thử hybrid retrieval (BM25 kết hợp dense) cho các câu chứa tên riêng hiếm như q01, mở rộng tập test lên khoảng 15–20 câu, và nhờ thêm một người chấm độc lập để đo mức đồng thuận của nhãn thủ công.
