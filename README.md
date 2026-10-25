# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini API, tạo 20 prompt hình ảnh, tạo tiêu đề/mô tả/SEO, xem và tải thumbnail.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Đầu thanh bên trái là **🌍 Ngôn ngữ đích**, đã mở rộng thêm tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc**:
1. Nhấn **➕ Tạo phiên mới** để tạo phiên trống. Phiên mới xuất hiện tự động trong danh sách.
2. **🗑️ Xóa tất cả phiên đã lưu** (yêu cầu xác nhận) xóa mọi phiên đang lưu trong phiên truy cập hiện tại.
3. **📚 Danh sách phiên đã lưu** nằm bên dưới: mỗi dòng gồm **ô tên có thể sửa trực tiếp** và nút **Mở**. Sửa tên rồi nhấn **Enter** để cập nhật; nhấn **Mở** để xem lại phụ đề, bản dịch, prompt và SEO của phiên. Phiên đang mở hiển thị **✓ Mở**.
4. Không có menu **Chọn phiên**, nút mũi tên xổ xuống hay khối đổi tên riêng phía trên.

**Giới hạn lưu trữ:** Danh sách và dữ liệu của từng phiên được giữ bởi `st.session_state` trong kết nối Streamlit đang mở. Việc tạo/đổi tên **không đồng nghĩa với lưu vĩnh viễn**. Nếu đóng tab, tải lại thành một phiên kết nối mới hoặc máy chủ khởi động lại, dữ liệu có thể mất. Hiện app không có cơ sở dữ liệu người dùng hoặc đồng bộ cloud.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.



## Các phần khác được giữ nguyên

- Dịch văn bản, tạo prompt và SEO bằng Gemini hoặc OpenAI API key của người dùng.
- Copy bản dịch, prompt, tiêu đề và mô tả; **không còn Copy phụ đề gốc**.
- Trích xuất phụ đề YouTube hoặc tải file TXT.
- Xem trước và tải thumbnail nếu truy cập được.

## 🔑 Cấu hình API

Mở thanh bên trái, trong phần **Cấu hình API**:

1. Chọn nhà cung cấp: **Google Gemini** hoặc **OpenAI**.
2. Nhập API key vào ô được che (hoặc đặt `GEMINI_API_KEY` / `OPENAI_API_KEY` trong Streamlit Cloud → App settings → Secrets).
3. Chọn model trong danh sách; có thể chọn **Tự nhập model** nếu cần.
4. Bấm **🧪 Kiểm tra kết nối API**. Khi có lỗi HTTP, app sẽ hiển thị giải thích về key, model, quota hoặc quyền truy cập.

Không đưa API key vào mã nguồn hay repository công khai. Key nhập trên giao diện chỉ dùng trong phiên truy cập Streamlit đang mở; cấu hình bằng Secrets dùng cho app server và có thể phát sinh chi phí. Người khác có quyền truy cập app có thể sử dụng API key đặt tại server để gọi AI, nên cần thiết lập kiểm soát truy cập nếu sử dụng Secrets cho app công khai.

## Triển khai

Repository: `leminhtuan118071999-web/youtube-translator-studio-pro`; branch: `main`; entry: `streamlit_app.py`.

Triển khai qua https://share.streamlit.io/ . Nếu app đã triển khai, Streamlit Community Cloud thường cập nhật sau khi commit; hãy làm mới trang để xem giao diện mới.

ChatGPT Plus không bao gồm quyền sử dụng Google Gemini API hay OpenAI API. Phụ đề có thể bị YouTube hạn chế trên hạ tầng Streamlit.

Tài liệu: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
