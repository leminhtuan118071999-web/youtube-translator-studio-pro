# Phương án không mất phí hosting worker

Giữ hai dịch vụ giao diện/API đang có trên Render Free. Chạy worker V2 trên máy
Mac cá nhân, kết nối cùng Supabase. Không tạo Background Worker trả phí trên
Render. API AI có thể vẫn phát sinh phí theo nhà cung cấp/model bạn chọn.

## Điều kiện

- Mac có Python 3.12 trở lên, lấy từ https://www.python.org/downloads/macos/.
- Máy có mạng, cắm sạc, mở nắp và giữ cửa sổ Terminal chạy worker.
- Trình khởi chạy dùng `caffeinate -i` trên macOS để ngăn máy tự ngủ khi worker
  hoạt động. Nó không ngăn tắt máy, gập nắp, mất điện hoặc mất mạng. Màn hình
  vẫn có thể tắt. Khi worker dừng, chế độ giữ thức cũng dừng.
- Giao diện/API Render Free vẫn có thể ngủ và có giới hạn tài nguyên. Worker
  cá nhân xử lý job đã được ghi vào Supabase mà không cần trình duyệt/API mở.
  Giao diện/API phải thức để gửi job mới hoặc xem tiến độ.

## Cấu hình trước khi chạy

1. Trên API Render, thêm `DATABASE_URL` và **đúng** `SESSION_ENCRYPTION_KEY` từ
   Streamlit V1, rồi lưu và deploy. Không tạo Fernet key mới.
2. Chạy dry-run V1 bằng tài khoản hiện tại, kiểm tra giải mã thành công.
3. Áp dụng hai migration V2 được kiểm thử (`001_v2_core.sql`, sau đó
   `002_v2_runtime.sql`) theo hướng dẫn chuyển dữ liệu. Không sửa bảng V1.
4. Nhập các phiên V1. Giữ V1 cho tới khi kiểm tra dữ liệu/ảnh hoàn tất.

## Chạy trên Mac

Tải/clone **toàn bộ** repository ở nhánh `v2/rebuild-foundation`. Không chỉ tải
thư mục backend, vì worker tái sử dụng các mô-đun ở thư mục gốc.

Mở Terminal tại thư mục repository rồi chạy:

```bash
python3 v2/start_local_worker.py
```

Hoặc mở tệp `v2/Start-LMT-Worker.command`. Nếu quyền thực thi bị mất khi giải
nén, chạy `bash v2/Start-LMT-Worker.command` trong Terminal.

Lần đầu, script tạo môi trường Python riêng tại `v2/.venv-worker`, cài các
thư viện trong requirements đã có, rồi hỏi:

- `DATABASE_URL`: cùng chuỗi kết nối Supabase dùng cho API; dùng SSL.
- `SESSION_ENCRYPTION_KEY`: đúng khóa V1, giống API Render.
- `SUPABASE_URL`: mặc định là dự án hiện tại; có thể sửa khi cần.
- Storage service-role key: tùy chọn, chỉ cần khi tạo/lưu ảnh. API Render cũng
  cần cấu hình Storage cho chức năng ảnh. Không cần key này để dịch/SEO/form.

Các giá trị bí mật không hiện khi gõ. Cấu hình được lưu riêng trên máy tại
`~/Library/Application Support/LMTStudioPro/worker.json`, quyền đọc/ghi chỉ cho
chủ tài khoản (`0600`), không nằm trong repository. Đây là tệp chứa bí mật trên
máy cá nhân, không phải mã hóa end-to-end; chỉ dùng trên tài khoản máy tin cậy.

Khi xuất hiện “Worker đã kết nối”, mở V2 và kiểm tra “Worker sẵn sàng”. Gửi một
truyện ngắn để thử. Job được lưu vào Supabase trước khi chạy; browser có thể đóng
và các batch/chunk đã xong có checkpoint. Nhấn Ctrl+C để dừng worker. Mở lại
lệnh trên để tiếp tục; job đang chạy có thể đợi lease cũ hết hạn (khoảng 3 phút).

Nhập lại cấu hình nếu cần:

```bash
python3 v2/start_local_worker.py --configure
```

Tắt máy hoặc để máy ngủ vẫn làm dừng xử lý. Nếu cần máy cá nhân ngủ mà tác vụ
vẫn chạy, phải chuyển worker sang một máy/máy chủ khác đang hoạt động.
