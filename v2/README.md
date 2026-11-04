# LMT Studio Pro V2

Next.js workspace, authenticated FastAPI API, and independent PostgreSQL worker.
V2 reuses the existing production translation, narration, SEO, character and
video-planning engines. V1 source and Supabase data remain available for rollback.

## Implemented

- Existing Supabase accounts, sign-in, registration and password recovery.
- Owner-scoped session CRUD, search, export and optimistic revision checks.
- Encrypted provider settings, model discovery and connection check. Existing
  keys are never returned to the browser.
- Original YouTube thumbnail preview/download and existing subtitle providers.
  No additional transcription or third-party service was introduced.
- Complete translation into one narrator's indirect speech; number spelling and
  fidelity checks use the existing engines. Translation/SEO have one action;
  profiles, images and forms are independent actions.
- Eight-second forms with reference image/video prompts, English production
  directions, target-language narration/subtitles, wardrobe/identity checks and
  repair memory. Groups of 99 support copy, TXT and JSON export. Prompts are
  editable without changing locked narration/timing.
- Character profiles, private persistent reference images and per-session ZIP.
- Durable jobs with encrypted credentials, checkpoints, lease fencing, bounded
  retries, manual resume, cancellation and independent worker heartbeats.
- Atomic V1 import with raw reversible snapshots, checksums and idempotent
  session IDs. Re-running import preserves existing V2 edits/settings.
- AI33 iframe and external-link fallback.

## Run

1. Apply `backend/migrations/001_v2_core.sql` then `002_v2_runtime.sql` to the same
   Supabase project, after reviewing a successful V1 dry run. Do not change V1
   tables, Auth users or image paths.
2. Configure the backend/worker with the **exact V1 Fernet key** and the same
   private PostgreSQL DSN. See `backend/.env.example`.
3. API from repository root:
   `uvicorn app.main:app --app-dir v2/backend --host 0.0.0.0 --port 8000`.
4. Worker from `v2/backend`: `python -m app.worker`.
5. Frontend from `v2/frontend`: `npm ci`, `npm run build`, `npm start`.
6. Sign in, inspect/import V1 data, then configure or test the saved provider.

The API and worker must have the **whole repository** available because the
engines live at its root. The frontend builds independently from its directory.

## Free hosting with a local worker

Keep the existing frontend/API on Render Free and run `python3 v2/start_local_worker.py`
on a powered-on personal computer. On macOS, `Start-LMT-Worker.command` provides
a Finder launcher and the worker prevents idle system sleep while it runs.
See [Vietnamese setup guide](docs/FREE_LOCAL_WORKER.md). No paid Render worker
is created by this option. The computer must remain awake and online.

## Deployment and cutover

`v2/render.yaml` defines the frontend, API and independent worker. It uses paid
always-on `0.5c-512mb` service plans; inspect the current Render quotation before applying.
No service is created merely by committing this file. Existing Streamlit hosting
does not switch to Next.js automatically when this code is merged.

See [deployment](docs/DEPLOYMENT.md), [migration](docs/MIGRATION_RUNBOOK.md) and
[verification](docs/VERIFICATION.md). Production cutover requires real account,
provider and worker smoke tests plus session/image reconciliation. Do not retire
V1 until those gates are verified.

## Limits

Audio metadata provides estimated timing, not word-level forced alignment. The
worker runs through browser/Streamlit sleep only while its independent hosting
is available. A provider request in flight may finish after cancellation. Lease
fencing protects database results; it cannot guarantee exactly-once billing by
an external provider after a network interruption. Reference prompts cannot
promise identical characters in external video tools.

V1 images held only in Streamlit process memory must be exported before that
process is stopped; they cannot be reconstructed by importing database JSON.

### Nhập nội dung từ YouTube

Mục Nội dung chỉ cần tên phiên, link YouTube, ngôn ngữ đích và phong cách. Các ô tiêu đề gốc, mô tả gốc, nội dung gốc/phụ đề và nhập TXT/SRT đã được bỏ khỏi giao diện; dữ liệu nguồn của phiên cũ vẫn được giữ bên trong.

Nhập link rồi đổi ngôn ngữ đích sẽ tự giao tác vụ **Dịch lời kể và YouTube SEO** khi worker sẵn sàng. Lựa chọn được chờ ngắn để tránh gửi tác vụ cho từng lần đổi liên tiếp; không tự chạy khi chỉ mở lại phiên, và không tạo thêm tác vụ khi phiên đang xử lý. Có nút chạy/chạy lại khi cần. Đổi link xóa dữ liệu nguồn cũ trong bản nháp để không dịch nhầm video trước. Không có phụ đề khả dụng thì tác vụ báo lỗi thay vì tự viết nội dung video.

Form 8 giây và nhân vật vẫn chạy riêng theo yêu cầu.

### Tự sửa đoạn dịch chưa đạt

Sau các lần sửa chi tiết, đoạn vẫn lỗi đối soát sẽ được tự chia nhỏ và dịch/kiểm tra tiếp, giữ ngữ cảnh trước–sau để xác định đúng người nói và người được hỏi. Những đoạn đã đạt được giữ trong checkpoint. Việc chia nhỏ có giới hạn; đoạn chưa đạt không được coi là hoàn tất hoặc bỏ qua.

Với tác vụ đã lỗi trước khi cập nhật, khởi động lại worker bằng mã mới rồi chọn **Tác vụ → Tiếp tục từ checkpoint** cho đúng phiên, giữ nguyên đầu vào. Không bấm tạo bản dịch mới nếu muốn tiếp tục các phần đã đạt của tác vụ cũ.

### Xóa tất cả phiên V2

Thanh bên có **Xóa tất cả phiên**, yêu cầu xác nhận trước khi xóa cả phiên bị ẩn bởi tìm kiếm và nội dung chưa lưu. API `DELETE /v1/sessions` chỉ xóa phiên của tài khoản đã đăng nhập, hủy tác vụ liên quan và vô hiệu hóa lease trong cùng giao dịch. Cấu hình API, dữ liệu V1 và V3 được giữ. Ảnh lưu trữ được giữ theo chính sách hiện tại của thao tác xóa một phiên; yêu cầu AI đã gửi có thể vẫn tính phí cho tới khi worker nhận việc hủy. Cần triển khai cả backend và frontend mới để dùng nút này.
