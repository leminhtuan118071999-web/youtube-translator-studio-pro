# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini API, tạo 20 prompt hình ảnh, tạo tiêu đề/mô tả/SEO, xem và tải thumbnail.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Đầu thanh bên trái là **🌍 Ngôn ngữ đích**, đã mở rộng thêm tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc** (không có ô “Chọn phiên”):

1. **Tự động lưu vào danh sách**: ngay khi app có phiên đầu tiên hoặc khi bấm **➕ Tạo phiên mới**, hệ thống đặt tên mặc định `Phiên 1`, `Phiên 2`… và thêm ngay vào **Danh sách phiên đã lưu**. Không cần bấm nút Lưu tên.
2. **✏️ Tên phiên / Đổi tên phiên**: có thể đặt lại tên của phiên đang mở sau khi đã tạo hoặc sau khi chạy các chức năng. Nhập tên mới rồi bấm **✏️ Đổi tên phiên**; nội dung và kết quả đang có không bị mất.
3. **➕ Tạo phiên mới**: tạo phiên trống mới, tách phụ đề, bản dịch, prompt và SEO.
4. **🗑️ Xóa tất cả phiên đã lưu**: cần đánh dấu xác nhận trước khi xóa các phiên thuộc phiên truy cập hiện tại.
5. **📚 Danh sách phiên đã lưu**: mới tạo ở trên; nhấn vào tên để mở lại toàn bộ nội dung của phiên. Phiên đang mở có dấu ✓.

Việc đổi tên trên giao diện diễn ra khi Streamlit xử lý thao tác mới, không phải ngay trong lúc một yêu cầu AI đang chạy ở phía máy chủ.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.

**Lưu ý quan trọng:** Phiên đang được lưu bằng `st.session_state`, vì vậy chỉ được giữ trong kết nối Streamlit hiện tại. **Tên và nội dung phiên không được lưu vĩnh viễn khi đóng tab, đăng xuất hoặc máy chủ Streamlit khởi động lại.** Đây không phải lưu trữ cloud vĩnh viễn. Không có nút sao lưu JSON hay khôi phục trong giao diện tối giản này.

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
