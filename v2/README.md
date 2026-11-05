# LMT Studio Pro V2 — Dịch văn bản và SEO

## Chức năng hiện tại
- Lấy phụ đề gốc từ YouTube hoặc dùng toàn bộ văn bản nhập sẵn.
- Dịch trực tiếp sang ngôn ngữ đích, giữ lời thoại, tên và số liệu; kết quả gọi là Bản dịch.
- Tiêu đề, mô tả và tag chạy song song, lấy nguồn gốc làm ngữ cảnh, không chờ bản dịch.
- Kết quả mỗi nhánh lưu/hiện độc lập. Checkpoint cho phép tiếp tục phần lỗi, không gọi lại nhánh đã xong.
- Giữ AI33, cấu hình API, danh sách phiên, copy riêng và xuất TXT bản dịch/JSON phiên.
- Không còn tác vụ tạo nhân vật, ảnh, form/video hoặc nhập dữ liệu V1 trong API và bộ xử lý V2.
- Dữ liệu lịch sử vẫn giữ, không xóa hàng loạt dữ liệu người dùng.

## Chạy
Giữ nguyên cấu hình kết nối và khóa mã hóa đã có. Không tạo lại khóa cho tài khoản cũ.
- API: `uvicorn app.main:app --app-dir v2/backend --host 0.0.0.0 --port 8000`.
- Worker Mac: `python3 v2/start_local_worker.py` (hoặc LaunchAgent đã cài).
- Web: trong `v2/frontend`, chạy `npm ci`, `npm run build`, `npm start`.
Cập nhật cả web/API và worker để dùng cùng luồng mới. Máy worker phải bật và có mạng.

## Giới hạn
Hai nhánh có thể chạy đồng thời nhưng nhà cung cấp có thể giới hạn/tuần tự hóa API. Tự kiểm tra trong cùng lượt là chế độ ưu tiên tốc độ, không cam kết đúng tuyệt đối. Văn bản dài chia phần không chồng lặp và có thể cần thêm lượt tạo ngữ cảnh SEO. Không tự cắt nguồn vượt 350.000 ký tự. Chỉ dùng kết quả hoàn thành đúng phiên/revision để tránh ghi đè bản người dùng sửa.

## Kiểm tra
`python -m unittest test_v2_text_pipeline test_direct_translation`
`PYTHONPATH=.:v2/backend pytest v2/backend/tests` (kiểm tra tích hợp cần PostgreSQL cục bộ dùng một lần).
Trong `v2/frontend`: `npm test`, `npm run typecheck`.
