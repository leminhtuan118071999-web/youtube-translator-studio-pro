# LMT Studio Pro — Chạy nền xuyên đêm kể cả khi Streamlit Cloud ngủ

## Cơ chế

- Streamlit **chỉ giao việc**: kết quả của nút **🚀 BẮT ĐẦU TẠO TOÀN BỘ** được gửi tới bảng `public.lmt_durable_jobs` khi `DURABLE_WORKER_ENABLED` bật. Đây là khâu lấy phụ đề → tối ưu kịch bản → dịch → SEO và ảnh nhân vật nếu có API/Storage.
- Form 8 giây **không** được tạo trong lần chạy toàn bộ. Sau khi tải MP3/WAV/M4A/OGG và nhấn **🎬 Tạo form 8 giây theo giọng đọc**, Streamlit chỉ gửi thời lượng audio + bản dịch (không upload audio lên API phân tích). Worker ước tính số form 8 giây, tự viết hết, mỗi form một dòng, cách một dòng trống, chuyển cảnh 1 giây nằm trong clip.
- Worker Python độc lập chạy liên tục theo `render.yaml` trên một dịch vụ background worker trả phí, không phụ thuộc vào Streamlit Cloud. Hàng đợi Supabase tồn tại khi worker khởi động lại.
- Sau mỗi phần dịch hoặc nhóm 6 form hoàn chỉnh, worker cập nhật `result`, `stage`, `progress` trên Postgres. Lease hết hạn tự cho worker nhận lại việc. Khi khôi phục, các phần dịch đã checkpoint và form đã hoàn thành được bỏ qua, tránh làm lại phần đã xong.
- Khi máy tính mở lại, giao diện dùng JWT người dùng và RLS để đọc đúng hàng đợi, khôi phục kết quả vào **Danh sách phiên**. Các phiên chưa hoàn thành nằm trong danh sách ngay khi được giao, không cần đóng trình duyệt để lưu.
- Ảnh nhân vật được đưa lên bucket riêng `lmt-character-images` nếu worker được cấu hình khóa Storage server-only; người đăng nhập chỉ đọc ảnh trong thư mục UUID tài khoản của họ.

## 1. Chuẩn bị Supabase

Sử dụng chính project Supabase mà Streamlit đang dùng. Nếu chưa có bảng `youtube_studio_state`, chạy `supabase_schema.sql` trong SQL Editor trước.

Chạy migration `migrations/20261027_lmt_durable_jobs.sql` một lần. Kiểm tra kết quả: hai bảng mới `public.lmt_durable_jobs`, `public.lmt_worker_health`, bucket `lmt-character-images`. Đã bật RLS trên hai bảng; client chỉ có quyền đọc/giao việc của chính mình. Người dùng **không** được tự sửa trạng thái công việc hay ghi kết quả vào hàng đợi.

## 2. Triển khai máy chủ worker độc lập

Tại <https://dashboard.render.com/> tạo **New → Blueprint**, kết nối repo GitHub `leminhtuan118071999-web/youtube-translator-studio-pro`. Render nhận `render.yaml` và tạo service **lmt-studio-overnight-worker** (`type: worker`, compute trả phí, không phải free web service ngủ khi không truy cập).

Nhập các biến **trong Render**, không ghi vào GitHub hoặc ảnh chụp:

| Biến Render | Giá trị |
|---|---|
| `DATABASE_URL` | Chuỗi PostgreSQL của **cùng** project Supabase, ưu tiên *Session Pooler* với SSL (`sslmode=require`). Chỉ worker được giữ mật khẩu DB. |
| `SESSION_ENCRYPTION_KEY` | **Chính xác cùng Fernet key** đang dùng trong Streamlit Secrets để mã hóa API key khi giao việc. |
| `SUPABASE_URL` | URL HTTPS của project Supabase. |
| `SUPABASE_SERVICE_ROLE_KEY` | *Secret/service role* chỉ cấp trong Render để worker đưa PNG vào Storage. **Không bao giờ** cấu hình vào Streamlit hoặc frontend. |

Render sẽ chạy `python durable_worker.py` và tự khởi động lại khi service bị gián đoạn. Worker chỉ cần CPU nhỏ cho prompt generation, không render MP4. Nếu Render gửi SIGTERM hoặc host chết khi đang gọi API, công việc vẫn nằm trong Postgres và sẽ được nhận lại khi lease hết hạn (180 giây), với dữ liệu đã checkpoint.

> Render Background Worker là dịch vụ tính phí; ngoài ra nhà cung cấp AI có thể tính phí theo token/lần tạo ảnh. Worker xử lý một tác vụ mỗi instance, nhiều phiên sẽ xếp hàng; không bảo đảm mỗi phiên hoàn thành trước một giờ cố định nếu API chậm/hết quota.

## 3. Kích hoạt trong Streamlit Cloud

Chỉ bật sau khi Render worker thực sự chạy, bằng cách thêm vào **Streamlit Secrets**:

```toml
DURABLE_WORKER_ENABLED = "true"
```

Giữ các biến `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SESSION_ENCRYPTION_KEY` hiện có. Người dùng cần đăng nhập tài khoản để giao việc; chế độ lưu chỉ trên trình duyệt không có đảm bảo xuyên đêm.

Ứng dụng kiểm tra bảng `lmt_worker_health` (heartbeat cập nhật gần nhất trong 150 giây). Nếu worker chưa online, ứng dụng từ chối báo đã giao việc chạy qua đêm và hiển thị hướng dẫn khởi động. Sau khi worker thực sự online, nhấn **BẮT ĐẦU TẠO TOÀN BỘ** và có thể tắt máy/ngủ.

## 4. Theo dõi và tự khôi phục

Truy cập Supabase SQL Editor bằng tài khoản quản trị để xem trạng thái:

```sql
select id, session_id, kind, status, progress, stage, attempts,
       retry_after, updated_at
from public.lmt_durable_jobs
order by created_at desc
limit 30;
```

Các trạng thái: `queued` (đang chờ), `running` (worker đang xử lý), `retry_wait` (API tạm lỗi, sẽ thử lại), `completed`, `failed`. Các lỗi tạm thời tối đa 18 lần thử với backoff tối đa 15 phút; lỗi xác thực/quota vĩnh viễn có thể chuyển `failed` cần người dùng thay API key.

Mở lại Streamlit sau khi ngủ → đăng nhập → Danh sách phiên. Kết quả của đúng công việc được lấy từ hàng đợi, không phụ thuộc RAM của Streamlit Cloud. Nếu từng kết quả đã checkpoint thành công, nó luôn được lưu trên Supabase kể cả khi Streamlit bị ngắt trong khi worker xử lý.

## Giới hạn và bảo mật

- **Chưa có worker triển khai thì không có xử lý 24/7.** Chỉ đẩy code lên GitHub không làm Render tự chạy; phải kết nối và cấp các biến môi trường qua tài khoản Render.
- Hệ thống có thể tự khôi phục sau lỗi worker, nhưng không thể bảo đảm 100% hoàn thành mọi tác vụ nếu nhà cung cấp AI mất dịch vụ dài hạn, tài khoản hết hạn mức, file nguồn không lấy được hoặc worker không được duy trì.
- API key được mã hóa bằng Fernet trong các bản ghi đang chờ; bị xóa khỏi hàng đợi khi job kết thúc. Worker không ghi API key vào log. Database URL/Service Role Key chỉ lưu trong Render.
- Do hàng đợi lưu nội dung kịch bản và bản dịch phục vụ khôi phục, cần hạn chế quyền truy cập DB, và có thể dọn công việc đã hoàn thành sau khi chắc chắn đã đồng bộ vào Danh sách phiên.
- Để đổi `SESSION_ENCRYPTION_KEY`, xử lý hết các job đang chờ trước; đổi giữa chừng sẽ khiến worker không giải mã được token API cho những job cũ.
