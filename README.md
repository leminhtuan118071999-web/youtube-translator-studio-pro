# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini/OpenAI API, tạo 20 prompt hình ảnh, dịch tiêu đề/mô tả và SEO, xem và tải thumbnail.

## 🚀 Tạo toàn bộ bằng một nút

1. Ở thanh bên trái, chọn **🌍 Ngôn ngữ đích**, nhà cung cấp AI, Base URL, Model ID và nhập API key.
2. Dán link YouTube vào ô **🔗 Dán link video YouTube** rồi nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ**. Phụ đề gốc sẽ được xử lý nội bộ, không hiển thị ô nhập văn bản gốc.
3. App tự động: tìm phụ đề thủ công hoặc phụ đề tự động có sẵn trên YouTube → dịch toàn bộ nội dung sang ngôn ngữ đích → tạo **20 prompt hình ảnh bằng ngôn ngữ đích** → tạo **tiêu đề, mô tả, từ khóa SEO bằng ngôn ngữ đích**.
4. Sau khi chạy, app chỉ hiển thị nội dung đã được xử lý theo **ngôn ngữ đích** trong các tab kết quả. Các tab cho phép **Copy riêng** qua biểu tượng Copy trên khung nội dung (`st.code`): bản dịch đầy đủ, từng prompt 01–20, toàn bộ prompt, tiêu đề, mô tả, từ khóa SEO và cả bộ SEO. Có nút tải TXT bổ sung.
5. Thanh tiến trình theo dõi các tác vụ nền đang chạy; có thể chuyển sang phiên mới trong lúc phiên cũ vẫn xử lý. Nếu API lỗi, dữ liệu một phần vẫn được giữ để có thể chạy lại riêng từng mục.

**Giới hạn:** YouTube có thể chặn truy cập phụ đề, hoặc video không có phụ đề, khiến thao tác tự động thất bại; app không tự nhận dạng giọng nói cho video không có phụ đề. Chất lượng dịch/prompt/SEO phụ thuộc model và API key, có thể phát sinh phí.

## 📥 Xử lý lỗi YouTube chặn IP Streamlit Cloud

YouTube có thể chặn request trích xuất phụ đề từ địa chỉ IP máy chủ cloud. Khi đó model dịch dù đã kết nối thành công vẫn không nhận được phụ đề.

App có 3 con đường:

1. **YouTube trực tiếp:** luôn thử trước, không cần API key phụ đề.
2. **Dịch vụ phụ đề dự phòng Supadata:** khi cách trực tiếp lỗi, nếu đã nhập key riêng trong thanh bên **📥 Phụ đề YouTube dự phòng**, app sẽ tự thử `GET https://api.supadata.ai/v1/transcript?url=...` với `mode=auto`. API trả dữ liệu ngay hoặc trả `jobId` để app chờ tác vụ xử lý xong. Supadata có tài khoản miễn phí giới hạn; tạo transcript bằng AI có thể tính phí/credit. Đây là **API lấy phụ đề**, khác API Groq/Gemini/OpenAI dùng để dịch. Có thể nhập trong giao diện hoặc đặt `SUPADATA_API_KEY` trong Streamlit Cloud Secrets; không đưa vào mã nguồn.
3. **File phụ đề tải từ máy:** mở phần thu gọn **📄 Phụ đề dự phòng từ máy**, chọn file `.txt`, `.srt` hoặc `.vtt` (tối đa 4 MB). Khi nhấn **BẮT ĐẦU TẠO TOÀN BỘ**, app ưu tiên file vừa tải, bỏ bước yêu cầu phụ đề YouTube và tiếp tục dịch/generate tất cả mục. Không phải hiển thị các ô phụ đề gốc dài như trước.

Nếu YouTube trực tiếp thất bại mà chưa có Supadata key hoặc file phụ đề, phiên vẫn được giữ trong danh sách với **⚠️ lỗi tiếng Việt**, giải thích bước xử lý tiếp theo. Không thể bảo đảm bất kỳ API bên thứ ba nào trích xuất được mọi video (ví dụ video riêng tư hoặc giới hạn vùng).

Tài liệu tích hợp Supadata: https://github.com/supadata-ai/skills/blob/main/skills/supadata/references/video.md

## ⏳ Chạy nhiều phiên đồng thời

- Nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ** để tạo tác vụ chạy nền; ứng dụng **trả lại giao diện ngay** thay vì giữ người dùng ở trang chờ.
- Trong lúc phiên A đang chạy (⏳ kèm phần trăm), nhấn **➕ Tạo phiên mới** rồi nhập URL cho phiên B và bắt đầu tiếp; công việc của A tiếp tục trên luồng riêng.
- **📚 Danh sách phiên đã chạy** hiển thị phiên đang chạy (⏳), hoàn thành (✅) và **mọi phiên đã chạy nhưng lỗi (⚠️), kể cả khi chưa lấy được phụ đề hoặc chưa có bản dịch**. Nhấn tên để xem kết quả và thông báo lỗi; nhấn ✏️ để đổi tên.
- Sau khi API xử lý xong, kết quả của đúng phiên đó sẽ tự được đưa vào dữ liệu phiên và danh sách tự cập nhật. Có thể mở lại để copy bản dịch, 20 prompt, tiêu đề, mô tả, SEO.
- Tối đa 3 tác vụ đồng thời trong một phiên kết nối; máy chủ chạy tối đa 3 luồng worker. Nút **Xóa tất cả phiên đã lưu** yêu cầu xác nhận, hủy các tác vụ chưa chạy và yêu cầu tác vụ đang chạy ngừng ở bước tiếp theo.
- Nếu phụ đề hoặc API lỗi ở bất cứ bước nào, phiên vẫn giữ trong danh sách kèm lý do lỗi. Các phần đã xử lý thành công xuất hiện khi bạn mở lại phiên; có thể thử chạy lại. Worker chia sẻ kết quả từng bước với giao diện thay vì chỉ đến cuối mới lưu.

**Giới hạn kỹ thuật:** Đây là xử lý nền trong bộ nhớ của tiến trình Streamlit, **không phải hệ thống hàng đợi bền vững**. Phải giữ app/tab còn kết nối để danh sách phiên tự cập nhật; nếu tab đóng/tải lại thành kết nối mới, hoặc Streamlit Cloud ngủ/khởi động lại, công việc đang chạy và dữ liệu có thể mất. Không thể bảo đảm tác vụ tiếp tục khi máy chủ khởi động lại. Muốn chạy qua khởi động lại và lưu vĩnh viễn cần dịch vụ job queue/bộ nhớ lưu trữ riêng có xác thực.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Đầu thanh bên trái là **🌍 Ngôn ngữ đích**, đã mở rộng thêm tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc**:
1. Nhấn **➕ Tạo phiên mới**: nếu phiên cũ đang xử lý, app **không dừng tác vụ cũ**; bạn có thể bắt đầu công việc khác. Khi phiên cũ hoàn thành, app tự lưu kết quả vào **📚 Danh sách phiên đã chạy** trong kết nối hiện tại. Phiên chưa chạy sẽ không vào danh sách.
2. Khi đã nhấn **BẮT ĐẦU TẠO TOÀN BỘ**, phiên xuất hiện ngay là **⏳ đang chạy**. Sau khi hoàn tất hiện **✅**. Nếu lỗi ở bước đầu hoặc giữa quy trình, phiên vẫn hiển thị **⚠️**, đồng thời có thông báo nguyên nhân khi mở phiên. Phiên mới chưa bấm Bắt đầu không xuất hiện.
3. Trong danh sách, **nhấn trực tiếp vào tên phiên** để xem lại phụ đề, bản dịch, prompt và SEO; **không có nút “Mở”**.
4. Để đổi tên, nhấn **✏️** cạnh tên, nhập tên mới rồi nhấn Enter. Phiên đang hoạt động có dấu ✓.
5. **🗑️ Xóa tất cả phiên đã lưu** chỉ thực thi sau khi tích xác nhận.

**Giới hạn lưu trữ quan trọng:** Khi bấm Tạo phiên mới, phiên cũ được tự động giữ trong danh sách **ở kết nối Streamlit đang mở**. Đây chưa phải lưu trữ vĩnh viễn: dữ liệu có thể mất khi tải lại trang, đóng tab hoặc Streamlit Cloud khởi động lại. Không dùng tệp trên máy chủ làm kho chung vì có nguy cơ lộ nội dung giữa nhiều người dùng. Muốn giữ phiên qua các lần đăng nhập, cần tích hợp lưu trữ bền vững có xác thực riêng cho từng người dùng.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.



## Các phần khác được giữ nguyên

- Dịch văn bản, tạo prompt và SEO bằng nhiều nhà cung cấp AI; API key và model tùy chọn.
- Copy bản dịch, prompt, tiêu đề, mô tả và SEO bằng ngôn ngữ đích; **không hiển thị hoặc Copy phụ đề/tiêu đề/mô tả gốc**.
- Tự động trích xuất phụ đề từ link YouTube bằng nút **BẮT ĐẦU TẠO TOÀN BỘ**; không hiển thị các ô phụ đề, tiêu đề hoặc mô tả gốc.
- Xem trước và tải thumbnail nếu truy cập được.

## 🔧 Lỗi API có phản hồi nhưng không trả văn bản

Một số model có suy luận (đặc biệt `openai/gpt-oss-120b` trên Groq) có thể dùng hết quota token đầu ra cho reasoning trước khi xuất bản dịch. App đã tối ưu riêng GPT-OSS trên **Groq** với `reasoning_effort=low`, `max_completion_tokens=8192` và không yêu cầu trả lại reasoning. Các nhà cung cấp khác giữ cấu hình riêng để tránh lỗi 400 do tham số không được hỗ trợ.

Nếu API trả về không có text, app sẽ giải thích `finish_reason` (ví dụ `length` khi hết token, hoặc `tool_calls` khi model chỉ gọi công cụ) thay vì báo chung chung. App không sử dụng trường reasoning làm nội dung dịch và không ghi nội dung suy luận ra giao diện.

Nếu còn lỗi sau khi cập nhật, chọn model văn bản khác trong menu Model ID, ví dụ `llama-3.3-70b-versatile` khi nhà cung cấp Groq và API key của bạn được phép sử dụng; kiểm tra kết nối API, sau đó dùng **BẮT ĐẦU TẠO TOÀN BỘ** để chạy lại phiên.

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
