# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit tạo mới dành cho việc xử lý nội dung YouTube.

## Chức năng hiện có

- Trích xuất phụ đề sẵn có từ đường link YouTube khi có thể truy cập; hỗ trợ nhập văn bản hoặc tải tệp TXT.
- Dịch nội dung sang nhiều ngôn ngữ bằng Gemini API key riêng.
- Sinh 20 prompt hình ảnh tiếng Anh và nội dung SEO.
- Copy toàn bộ bản dịch, prompt, tiêu đề và mô tả bằng biểu tượng sao chép trong khung văn bản. **Đã bỏ phần Copy phụ đề gốc theo yêu cầu.**
- Xem trước và tải thumbnail YouTube theo chất lượng sẵn có.
- **Quản lý các phiên riêng biệt:** tạo phiên, đặt tên, đổi tên, chọn phiên, nhân bản và xóa phiên.
- **Lưu từng phiên** ra tệp JSON; **sao lưu tất cả** hoặc **khôi phục** tệp JSON khi mở lại.

## Cách sử dụng phiên làm việc

1. Trong thanh bên trái, tìm mục **📁 Quản lý phiên làm việc**.
2. Nhập tên video/dự án rồi bấm **➕ Tạo phiên mới**.
3. Mỗi phiên có phụ đề, bản dịch, 20 prompt, tiêu đề, mô tả và SEO riêng.
4. Dùng **Chọn phiên** để chuyển giữa các phiên; có thể **Đổi tên** hoặc **Nhân bản**.
5. Khi muốn giữ nội dung lâu dài, bấm **💾 Lưu phiên hiện tại (.json)**. Để lưu mọi phiên, bấm **📦 Sao lưu tất cả phiên (.json)**.
6. Lần sử dụng tiếp theo, chọn tệp bằng **📂 Chọn file JSON đã lưu** rồi bấm **♻️ Khôi phục phiên từ file**.

**Giới hạn lưu trữ:** Các phiên trong app được giữ bằng `st.session_state` trong phiên kết nối Streamlit đang mở. **Chúng không tự đồng bộ qua thiết bị hoặc được giữ vĩnh viễn sau khi đóng tab/khởi động lại server.** Để không mất nội dung, hãy tải JSON và khôi phục khi quay lại. API key không có trong tệp JSON.

## Triển khai

1. Vào https://share.streamlit.io/ và triển khai từ repository `leminhtuan118071999-web/youtube-translator-studio-pro`.
2. Chọn branch `main` và main file `streamlit_app.py`.
3. Nhập Gemini API key tại thanh bên trong app; key không nằm trong tệp sao lưu.
4. Nếu app đang mở, tải lại trang sau khi commit mới được triển khai.

ChatGPT Plus không bao gồm quyền dùng Gemini API. Video không có phụ đề hoặc bị YouTube chặn có thể không trích xuất được.

Tài liệu Streamlit: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
