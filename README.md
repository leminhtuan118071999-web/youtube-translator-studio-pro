# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini API, tạo 20 prompt hình ảnh, tạo tiêu đề/mô tả/SEO, xem và tải thumbnail.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Giao diện quản lý chỉ gồm:
1. **Chọn phiên**: mở phiên đang có để tiếp tục công việc.
2. **Tên phiên** + **💾 Lưu tên phiên**: đặt/đổi tên cho phiên đang chọn.
3. **➕ Tạo phiên mới**: mở một phiên trống hoàn toàn, không dùng lại phụ đề/bản dịch của phiên cũ.
4. **🗑️ Xóa tất cả phiên đã lưu**: cần đánh dấu xác nhận; xóa toàn bộ dữ liệu các phiên trong kết nối hiện tại, sau đó tạo phiên trắng.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.

**Lưu ý quan trọng:** Phiên đang được lưu bằng `st.session_state`, vì vậy chỉ được giữ trong kết nối Streamlit hiện tại. **Tên và nội dung phiên không được lưu vĩnh viễn khi đóng tab, đăng xuất hoặc máy chủ Streamlit khởi động lại.** Đây không phải lưu trữ cloud vĩnh viễn. Không có nút sao lưu JSON hay khôi phục trong giao diện tối giản này.

## Các phần khác được giữ nguyên

- Dịch văn bản, tạo prompt và SEO bằng Gemini API key của người dùng.
- Copy bản dịch, prompt, tiêu đề và mô tả; **không còn Copy phụ đề gốc**.
- Trích xuất phụ đề YouTube hoặc tải file TXT.
- Xem trước và tải thumbnail nếu truy cập được.

## Triển khai

Repository: `leminhtuan118071999-web/youtube-translator-studio-pro`; branch: `main`; entry: `streamlit_app.py`.

Triển khai qua https://share.streamlit.io/ . Nếu app đã triển khai, Streamlit Community Cloud thường cập nhật sau khi commit; hãy làm mới trang để xem giao diện mới.

ChatGPT Plus không bao gồm Gemini API key. Phụ đề có thể bị YouTube hạn chế trên hạ tầng Streamlit.

Tài liệu: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
