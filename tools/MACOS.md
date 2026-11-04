# V2 và V3 không cần giữ Terminal

Chạy bằng tài khoản Mac đang đăng nhập, không dùng sudo. Cần Python >= 3.12, hai thư mục dự án đã cài và cấu hình worker V2 đã lưu. Chờ video đang dựng hoàn tất trước khi chuyển cách khởi động. Nhấn Ctrl+C trong Terminal V2 và V3, sau đó:

```sh
cd ~/lmt-video-editor-v3
python3 tools/macos_agents.py install
python3 tools/macos_agents.py status
```

Đường dẫn mặc định V2 là ~/lmt-studio-pro-v2, V3 là ~/lmt-video-editor-v3; có thể truyền --v2 /đường/dẫn --v3 /đường/dẫn khi install.

Sau khi status có PID, V2 worker và V3 chạy nền; không cần chạy hai launcher thủ công nữa. V3 ở http://localhost:8503; V2 dùng trang web hiện tại. Cài thư viện lần đầu có thể cần vài phút. Status chỉ phản ánh tiến trình launchd; kiểm tra V2 đã kết nối trên web và V3 mở được. Log ở ~/Library/Logs/LMTStudioPro; không chia sẻ nguyên log khi chưa kiểm tra dữ liệu riêng.

```sh
python3 tools/macos_agents.py stop
python3 tools/macos_agents.py start
python3 tools/macos_agents.py uninstall
```

stop dừng hai agent tới khi start hoặc đăng nhập lại. uninstall chỉ gỡ agent, không xóa dự án/khóa. Không dừng khi đang làm việc nếu muốn tránh gián đoạn; render V3 tách rời có thể tiếp tục. Dịch vụ tự khởi động sau khi đăng nhập, tự khởi động lại khi tiến trình thoát (giãn 60 giây), không chạy khi máy tắt/ngủ hay đã đăng xuất. macOS có thể yêu cầu quyền truy cập thư mục xuất hoặc chạy nền; cho phép đúng Python/LMT khi hệ thống hỏi. Đóng Terminal được; không di chuyển/xóa thư mục dự án hoặc Python đã dùng cài. Khi nâng cấp mã, stop, git cập nhật đúng nhánh rồi start. Bộ cài không sao chép khóa vào plist, không đổi nguồn V2/V3 hoặc tệp cấu hình.

Tài liệu Apple: https://support.apple.com/guide/terminal/script-management-with-launchd-apdc6c1077b/mac
