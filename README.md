# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini/OpenAI API, tạo 20 prompt hình ảnh, dịch tiêu đề/mô tả và SEO, xem và tải thumbnail.

## 🚀 Tạo toàn bộ bằng một nút

1. Ở thanh bên trái, chọn **🌍 Ngôn ngữ đích**, nhà cung cấp AI (Gemini hoặc OpenAI), model và nhập API key.
2. Dán link YouTube vào ô **🔗 Dán link video YouTube** rồi nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ**. Nếu dùng văn bản đã nhập hoặc tải file TXT, có thể chạy không cần link (để trống URL).
3. App tự động: tìm phụ đề thủ công hoặc phụ đề tự động có sẵn trên YouTube → dịch toàn bộ nội dung sang ngôn ngữ đích → tạo **20 prompt hình ảnh bằng ngôn ngữ đích** → tạo **tiêu đề, mô tả, từ khóa SEO bằng ngôn ngữ đích**.
4. Các tab cho phép **Copy riêng** từng mục qua biểu tượng Copy trên khung nội dung (`st.code`): bản dịch đầy đủ, từng prompt từ 01–20, toàn bộ prompt, tiêu đề, mô tả, từ khóa SEO và cả bộ SEO. Có nút tải file .txt bổ sung.
5. Thanh tiến trình hiển thị các bước đang chạy; nếu một bước lỗi, kết quả của các bước đã hoàn tất vẫn thuộc phiên hiện tại, và có thể dùng nút chạy lại từng mục.

**Giới hạn:** YouTube có thể chặn truy cập phụ đề, hoặc video không có phụ đề, khiến thao tác tự động thất bại; app không tự nhận dạng giọng nói cho video không có phụ đề. Chất lượng dịch/prompt/SEO phụ thuộc model và API key, có thể phát sinh phí.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Đầu thanh bên trái là **🌍 Ngôn ngữ đích**, đã mở rộng thêm tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc**:
1. Nhấn **➕ Tạo phiên mới** để tạo phiên trống. Phiên trống **không xuất hiện** trong danh sách.
2. Sau khi **trích xuất phụ đề**, **nhập file TXT**, **dịch**, **tạo prompt** hoặc **tạo SEO** thành công, phiên tự động được đánh dấu đã chạy và xuất hiện tại **📚 Danh sách phiên đã chạy**. Các lần thử lỗi không được lưu.
3. Trong danh sách, **nhấn trực tiếp vào tên phiên** để xem lại phụ đề, bản dịch, prompt và SEO; **không có nút “Mở”**.
4. Để đổi tên, nhấn **✏️** cạnh tên, nhập tên mới rồi nhấn Enter. Phiên đang hoạt động có dấu ✓.
5. **🗑️ Xóa tất cả phiên đã lưu** chỉ thực thi sau khi tích xác nhận.

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
