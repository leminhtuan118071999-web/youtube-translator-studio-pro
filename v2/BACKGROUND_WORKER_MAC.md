# V2 worker nền trên macOS

Worker vẫn chạy trên máy Mac, dùng cấu hình hiện có và cùng hàng đợi/checkpoint.
Không cần mở cửa sổ Terminal sau khi cài. Đăng xuất hoặc tắt máy vẫn làm worker dừng.
Màn hình được phép tắt; máy cần còn bật, đăng nhập và có mạng.

## Cài một lần

Chờ phiên đang chạy hoàn thành rồi nhấn Ctrl+C tại Terminal worker cũ trước khi cài,
để tránh chạy đồng thời worker foreground và worker nền.

```bash
cd "$HOME/lmt-studio-pro-v2" &&
git fetch origin v2/rebuild-foundation &&
git merge --ff-only FETCH_HEAD &&
python3 v2/background_worker.py install
```

Cần Python 3.12+ và cấu hình đã được tạo bằng `start_local_worker.py`.
Trình cài chỉ kiểm tra cấu hình hiện có; không nhập lại khóa, không ghi bí mật vào plist.
LaunchAgent: `~/Library/LaunchAgents/com.lmtstudio.v2.worker.plist`.
Tự chạy khi đăng nhập Mac, khởi động lại sau lỗi với khoảng nghỉ ít nhất 30 giây.
Thông báo cài thành công nghĩa dịch vụ đã được nạp, không thay thế kiểm tra kết nối DB.

Mở https://lmt-studio-pro-v2-web.onrender.com để dùng.

## Tự khôi phục sau mất mạng hoặc gián đoạn

- Khi mạng trở lại, worker tự tiếp tục tác vụ đang chờ từ checkpoint; không cần mở trình duyệt hay bấm Tiếp tục.
- Khi tiến trình dừng bất ngờ, worker khác/lần chạy lại chỉ nhận việc sau khi lease cũ hết hạn (khoảng 3 phút).
- Lỗi mạng, timeout và gateway tạm thời được thử lại với khoảng chờ tăng dần, tối đa 15 phút giữa các lần. Các tác vụ văn bản không bị dừng vĩnh viễn chỉ vì vượt ngân sách thử lại cũ.
- Worker cũng rà soát các tác vụ lỗi tạm thời cũ khi khởi động và khoảng mỗi phút khi có thể; chỉ khôi phục tác vụ mới nhất, đầu vào chưa đổi, chưa có tác vụ khác đang hoạt động. Khóa được lấy lại từ cấu hình mã hóa của đúng chủ phiên.
- Không khôi phục tác vụ đã hủy, nguồn đã sửa, tác vụ cũ đã được thay thế hoặc lỗi cấu hình/nội dung. Nếu cấu hình không còn khả dụng, cần sửa cấu hình trước.
- Phần đã ghi thành công vào checkpoint được giữ; yêu cầu AI bị đứt trước khi lưu có thể phải gọi lại. Máy tắt thì không xử lý; tự tiếp tục sau khi đăng nhập lại và có mạng.

## Kiểm tra và dừng

Từ thư mục dự án:

```bash
python3 v2/background_worker.py status
```

Nhật ký kết nối: `~/Library/Logs/LMTStudioPro/v2-worker.log`.
Nhật ký lỗi: `~/Library/Logs/LMTStudioPro/v2-worker-error.log`.

Dừng worker nền trong lần đăng nhập hiện tại:

```bash
python3 v2/background_worker.py stop
```

Gỡ chế độ tự chạy (giữ nguyên dữ liệu và cấu hình):

```bash
python3 v2/background_worker.py uninstall
```

Chạy lại hoặc nạp mã mới sau cập nhật bằng lệnh `install`.
Nên dừng/cập nhật khi không có phiên đang xử lý. Không khởi động thêm worker foreground
trong khi worker nền vẫn đang chạy.

Kiểm tra tự động: `python3 -m unittest v2.test_background_worker -q`.
Các kiểm tra dùng giả lập launchctl; cần xác nhận khởi động, nhật ký kết nối và tác vụ thật trên Mac.
