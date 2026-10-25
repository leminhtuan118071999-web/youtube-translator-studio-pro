# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini/OpenAI API, tạo 20 prompt hình ảnh, dịch tiêu đề/mô tả và SEO, xem và tải thumbnail.

## 🚀 Tạo toàn bộ bằng một nút

1. Ở thanh bên trái, chọn **🌍 Ngôn ngữ đích**, nhà cung cấp AI, Base URL, Model ID và nhập API key.
2. Dán link YouTube vào ô **🔗 Dán link video YouTube** rồi nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ**. Phụ đề gốc sẽ được xử lý nội bộ, không hiển thị ô nhập văn bản gốc.
3. App tự động: tìm phụ đề thủ công hoặc phụ đề tự động có sẵn trên YouTube → dịch toàn bộ nội dung sang ngôn ngữ đích → tạo **20 prompt hình ảnh bằng ngôn ngữ đích** → tạo **tiêu đề, mô tả, từ khóa SEO bằng ngôn ngữ đích**.
4. Sau khi chạy, app chỉ hiển thị nội dung đã được xử lý theo **ngôn ngữ đích** trong các tab kết quả. Các tab cho phép **Copy riêng** qua biểu tượng Copy trên khung nội dung (`st.code`): bản dịch đầy đủ, từng prompt 01–20, toàn bộ prompt, tiêu đề, mô tả, từ khóa SEO và cả bộ SEO. Có nút tải TXT bổ sung.
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

- Dịch văn bản, tạo prompt và SEO bằng nhiều nhà cung cấp AI; API key và model tùy chọn.
- Copy bản dịch, prompt, tiêu đề, mô tả và SEO bằng ngôn ngữ đích; **không hiển thị hoặc Copy phụ đề/tiêu đề/mô tả gốc**.
- Tự động trích xuất phụ đề từ link YouTube bằng nút **BẮT ĐẦU TẠO TOÀN BỘ**; không hiển thị các ô phụ đề, tiêu đề hoặc mô tả gốc.
- Xem trước và tải thumbnail nếu truy cập được.

## 🔑 Cấu hình API đa nền tảng

App hỗ trợ lựa chọn **Groq, Google Gemini, OpenAI, OpenRouter, DeepSeek, Together AI, Anthropic Claude** hoặc **API tương thích OpenAI (tùy chỉnh)**.

Tại thanh bên trái:

1. **CHỌN NỀN TẢNG AI**: chọn nhà cung cấp. Mỗi nền tảng có Base URL và model mặc định, nhưng bạn có thể sửa.
2. **🔐 API Key**: nhập khóa của nhà cung cấp tương ứng. App giữ khóa trong kết nối hiện tại, không lưu trong dữ liệu phiên hay GitHub. Với ứng dụng riêng, có thể cấu hình các khóa tại **App settings → Secrets** bằng tên: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, `ANTHROPIC_API_KEY`.
3. **🌐 Base URL**: nhập địa chỉ gốc HTTPS của nhà cung cấp. Không thêm đuôi `/chat/completions`, `/messages` hoặc `/models`. App tự thêm endpoint.
4. **🤖 Model ID**: nhập model bạn có quyền sử dụng, ví dụ `openai/gpt-oss-120b` khi chọn Groq.
5. **🔎 Quét Model từ API**: gọi `GET {base_url}/models` (hoặc endpoint tương đương), nếu dịch vụ hỗ trợ; chọn một model từ kết quả và bấm **📌 Dùng Model đã chọn**.
6. **🧪 Kiểm tra kết nối API**: thử sinh một đoạn ngắn trước khi chạy **🚀 BẮT ĐẦU TẠO TOÀN BỘ**.

| Nhà cung cấp | Base URL mặc định |
|---|---|
| Groq | `https://api.groq.com/openai/v1` |
| Gemini (OpenAI-compatible) | `https://generativelanguage.googleapis.com/v1beta/openai` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| DeepSeek | `https://api.deepseek.com` |
| Together AI | `https://api.together.xyz/v1` |
| Anthropic Claude | `https://api.anthropic.com/v1` |

**Lưu ý:** Các dịch vụ OpenAI-compatible dùng endpoint chat completions; Anthropic dùng Messages API. Không phải mọi model đều hỗ trợ chức năng/dung lượng giống nhau. Quét model có thể không khả dụng trên một số server, nhưng vẫn có thể nhập thủ công. Base URL tùy chỉnh chỉ chấp nhận HTTPS công khai, chặn địa chỉ nội bộ và không tự theo chuyển hướng HTTP. Chỉ cung cấp API key cho máy chủ bạn tin tưởng vì key sẽ được gửi tới Base URL đã nhập. API có thể tính phí. Nếu app ở chế độ công khai và dùng key trong Secrets, cần bật hạn chế truy cập để tránh người khác sử dụng API của bạn.

## Triển khai

Repository: `leminhtuan118071999-web/youtube-translator-studio-pro`; branch: `main`; entry: `streamlit_app.py`.

Triển khai qua https://share.streamlit.io/ . Nếu app đã triển khai, Streamlit Community Cloud thường cập nhật sau khi commit; hãy làm mới trang để xem giao diện mới.

ChatGPT Plus không bao gồm quyền sử dụng API của Groq, Google Gemini, OpenAI hoặc các nhà cung cấp khác. Phụ đề có thể bị YouTube hạn chế trên hạ tầng Streamlit.

Tài liệu: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
