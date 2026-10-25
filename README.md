# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit tạo mới, dựa trên quy trình bạn mô tả và video demo, có thêm:

- Lấy phụ đề có sẵn từ link YouTube (khi YouTube cho phép), hoặc nhập thủ công / nạp TXT, SRT, VTT.
- Dịch đa ngôn ngữ bằng Gemini hoặc OpenAI API.
- Copy **toàn bộ** ở mỗi phần: phụ đề, bản dịch, tiêu đề, mô tả, prompt hình ảnh, SEO.
- Tạo tối đa 20 prompt hình ảnh theo câu chuyện.
- Dịch hoặc tạo tiêu đề, mô tả và từ khóa SEO.
- Xem, tải thumbnail YouTube chất lượng cao nhất sẵn có.
- Quản lý dự án và tải bản sao lưu JSON.

## Triển khai trên Streamlit Community Cloud

1. Mở https://share.streamlit.io → **Create app** → **Yup, I have an app**.
2. Repository: `leminhtuan118071999-web/youtube-translator-studio-pro`; branch: `main`; main file: `streamlit_app.py`.
3. Chọn subdomain nếu muốn và nhấn **Deploy**.
4. Để dịch AI, vào **App settings → Secrets** và nhập `GEMINI_API_KEY = "..." ` hoặc `OPENAI_API_KEY = "..."`. Không đẩy API key lên GitHub.

**Lưu ý:** ChatGPT Plus không bao gồm phí API. Việc lấy phụ đề từ YouTube đôi khi bị máy chủ từ chối, và app không tự nhận dạng giọng nói ở video không có phụ đề.

## Mã nguồn

Mã nguồn gốc gồm `streamlit_app.py`, `ai_utils.py`, `state_utils.py`, `youtube_utils.py` và các bài test. Để triển khai nhanh, repo này sử dụng một bundle ZIP được giải nén tự động lúc khởi chạy; có thể giải nén `app_bundle.b64` (nội dung base64 của ZIP) để chỉnh sửa toàn bộ mã nguồn đọc được.

Tài liệu triển khai: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
