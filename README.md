# 🎬 YouTube Translator Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini/OpenAI API, tạo 20 prompt hình ảnh, dịch tiêu đề/mô tả và SEO, xem và tải thumbnail.

## ☁️ Tự động lưu toàn bộ dữ liệu và cấu hình API qua lần đăng nhập sau

Để lưu bền vững, admin kết nối một dự án Supabase có xác thực email và RLS. Khi đăng nhập, người dùng sẽ thấy lại mọi phiên đã đồng bộ: bản dịch, prompt ảnh, SEO, phụ đề, link video, tên phiên, trạng thái và cấu hình các nhà cung cấp API. Nhà cung cấp hiện chọn, Base URL, Model ID và API key do người dùng nhập đều được nhớ đến khi thay đổi. Supadata API key cũng được hỗ trợ.

### Bật lưu trữ

1. Tạo dự án Supabase tại https://supabase.com/dashboard và bật Email authentication.
2. Mở SQL Editor của Supabase, chạy file [supabase_schema.sql](supabase_schema.sql) trong repository. Bảng có Row Level Security: tài khoản chỉ đọc/ghi dữ liệu của chính mình.
3. Sinh Fernet key bằng Python và cryptography: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
4. Thêm vào Streamlit Cloud → App settings → Secrets ba giá trị: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SESSION_ENCRYPTION_KEY`. Dùng giá trị riêng của dự án, tuyệt đối không commit các giá trị vào GitHub.
5. Khởi động lại app. Màn hình tạo tài khoản/đăng nhập sẽ xuất hiện. Khi đăng nhập, dữ liệu của tài khoản được khôi phục và những thay đổi mới được tự lưu. Có thể chọn **Lưu ngay** trong thanh bên để chủ động đồng bộ trước khi thoát.

**Bảo mật:** API key được mã hóa Fernet trên Streamlit server trước khi lưu vào Supabase, và dữ liệu được giới hạn cho từng tài khoản bằng RLS. Người quản trị sở hữu khóa Fernet vẫn có thể giải mã nên đây không phải mã hóa end-to-end. Đừng thay hoặc làm mất khóa Fernet; đừng dùng Supabase service-role key. Key từ Streamlit Secrets dùng chung trên máy chủ không được sao chép vào dữ liệu cá nhân.

**Chưa kết nối Supabase:** App vẫn hoạt động nhưng chỉ lưu tạm trong kết nối. Phần **Lưu dữ liệu và sao lưu** cho phép tải và khôi phục JSON các phiên (không chứa API key). Sau khi có Supabase, việc lưu phiên và key mới tự động hoạt động.

**Tác vụ đang chạy:** Kết quả đã đồng bộ vẫn tồn tại khi đóng app. Job đang chạy trong bộ nhớ vẫn có thể dừng khi đóng tab hoặc Streamlit Cloud khởi động lại; hệ thống tải lại phần kết quả đã lưu và cho phép chạy lại. Tránh mở nhiều tab cùng tài khoản để chỉnh sửa đồng thời.
## 🚀 Tạo toàn bộ bằng một nút

1. Ở thanh bên trái, chọn nhà cung cấp AI, Base URL, Model ID và nhập API key. **🌍 Ngôn ngữ đích** được chọn ở khu vực chính, ngay trên nút **🚀 BẮT ĐẦU TẠO TOÀN BỘ**.
2. Dán link YouTube vào ô **🔗 Dán link video YouTube** rồi nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ**. Phụ đề gốc sẽ được xử lý nội bộ, không hiển thị ô nhập văn bản gốc.
3. App tự động: tìm phụ đề thủ công hoặc phụ đề tự động có sẵn trên YouTube → dịch toàn bộ nội dung sang ngôn ngữ đích → tạo **20 prompt hình ảnh bằng ngôn ngữ đích** → tạo **tiêu đề, mô tả, từ khóa SEO bằng ngôn ngữ đích**.
4. Sau khi chạy, app chỉ hiển thị nội dung đã được xử lý theo **ngôn ngữ đích** trong các tab kết quả. Có nút Copy bản dịch đầy đủ, **Copy toàn bộ 20 prompt** (không còn danh sách Copy từng cảnh), và **Copy riêng tiêu đề, mô tả, từ khóa SEO** (không còn khối Copy gộp toàn bộ tiêu đề • mô tả • SEO). Có nút tải TXT bổ sung.
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

**Giới hạn kỹ thuật:** Xử lý nền vẫn chạy trong bộ nhớ Streamlit, không phải hàng đợi bền vững. Nếu tab bị đóng hoặc máy chủ khởi động lại trong lúc đang chạy, tác vụ có thể dừng. Với Supabase, phần kết quả đã được đồng bộ vẫn được giữ để xem lại; chưa có Supabase thì dữ liệu có thể mất. Muốn đảm bảo tác vụ vẫn hoàn thành sau khi server khởi động lại cần job queue riêng.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Ô **🌍 Ngôn ngữ đích** nằm ở khu vực chính, ngay trước nút **🚀 BẮT ĐẦU TẠO TOÀN BỘ**, với tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc**:
1. Nhấn **➕ Tạo phiên mới**: nếu phiên cũ đang xử lý, app **không dừng tác vụ cũ**; bạn có thể bắt đầu công việc khác. Khi phiên cũ hoàn thành, app tự lưu kết quả vào **📚 Danh sách phiên đã chạy** trong kết nối hiện tại. Phiên chưa chạy sẽ không vào danh sách.
2. Khi đã nhấn **BẮT ĐẦU TẠO TOÀN BỘ**, phiên xuất hiện ngay là **⏳ đang chạy**. Sau khi hoàn tất hiện **✅**. Nếu lỗi ở bước đầu hoặc giữa quy trình, phiên vẫn hiển thị **⚠️**, đồng thời có thông báo nguyên nhân khi mở phiên. Phiên mới chưa bấm Bắt đầu không xuất hiện.
3. Trong danh sách, **nhấn trực tiếp vào tên phiên** để xem lại phụ đề, bản dịch, prompt và SEO; **không có nút “Mở”**.
4. Để đổi tên, nhấn **✏️** cạnh tên, nhập tên mới rồi nhấn Enter. Phiên đang hoạt động có dấu ✓.
5. **🗑️ Xóa tất cả phiên đã lưu** chỉ thực thi sau khi tích xác nhận.

**Giới hạn:** Chưa cấu hình Supabase thì phiên chỉ được giữ trong kết nối Streamlit. Sau khi đăng nhập Supabase, các kết quả đã đồng bộ được lưu lâu dài. Công việc đang chạy vẫn có thể gián đoạn khi máy chủ khởi động lại.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.



## Các phần khác được giữ nguyên

- Dịch văn bản, tạo prompt và SEO bằng nhiều nhà cung cấp AI; API key và model tùy chọn.
- Copy bản dịch, prompt, tiêu đề, mô tả và SEO bằng ngôn ngữ đích; **không hiển thị hoặc Copy phụ đề/tiêu đề/mô tả gốc**.
- Tự động trích xuất phụ đề từ link YouTube bằng nút **BẮT ĐẦU TẠO TOÀN BỘ**; không hiển thị các ô phụ đề, tiêu đề hoặc mô tả gốc.
- Xem trước và tải thumbnail nếu truy cập được.

## ⏳ Tự động xử lý Groq HTTP 429 (giới hạn token/phút)

Nếu Groq báo lỗi `429 Rate limit reached` và có thông báo `Please try again in 11.52s`, điều đó **không có nghĩa API key sai**. Model `openai/gpt-oss-120b` trên gói miễn phí có giới hạn 8.000 TPM (thời điểm tài liệu được tra cứu). Giới hạn mỗi tổ chức và mỗi model có thể thay đổi.

Ứng dụng hiện:
- Đọc `Retry-After` của Groq hoặc thời gian trong thông báo, cộng thời gian đệm, rồi **tự đợi và thử lại** yêu cầu vừa bị 429 (tối đa 3 lần thử lại). Trạng thái chờ xuất hiện trong tiến trình phiên.
- Chia nhỏ phụ đề thành các đoạn ngắn hơn khi dùng Groq GPT-OSS. Các đoạn đã dịch thành công được giữ lại, không bắt đầu toàn bộ từ đầu khi một đoạn gặp 429.
- Giảm `max_completion_tokens` của dịch từ 8.192 xuống 2.200 token, giữ 3.600 token khi tạo 20 prompt, và dùng tóm tắt phân tầng cho nội dung dài nhằm giảm đỉnh nhu cầu TPM.
- Nếu vượt quota **theo ngày** (TPD/RPD), app dừng thử lại vô ích và hướng dẫn chờ hạn mức mới hoặc chọn model khác.
- Nếu 3 lần thử lại vẫn bị giới hạn, phiên hiện ⚠️ cùng thông báo rõ ràng và giữ các kết quả đã xử lý được.

Lưu ý: App **không thể tăng hạn mức thật** của Groq hay bảo đảm mọi video dài sẽ hoàn thành trong hạn mức miễn phí. Nếu cần xử lý nhanh nhiều video, chọn nhà cung cấp/model có hạn mức cao hơn hoặc nâng gói của nhà cung cấp. Tham khảo [Groq rate limits](https://console.groq.com/docs/rate-limits).

## 🔧 Lỗi API có phản hồi nhưng không trả văn bản

Một số model có suy luận (đặc biệt `openai/gpt-oss-120b` trên Groq) có thể dùng hết quota token đầu ra cho reasoning trước khi xuất bản dịch. App đã tối ưu riêng GPT-OSS trên **Groq** với `reasoning_effort=low` và số token đầu ra phù hợp từng loại nội dung và không yêu cầu trả lại reasoning. Các nhà cung cấp khác giữ cấu hình riêng để tránh lỗi 400 do tham số không được hỗ trợ.

Nếu API trả về không có text, app sẽ giải thích `finish_reason` (ví dụ `length` khi hết token, hoặc `tool_calls` khi model chỉ gọi công cụ) thay vì báo chung chung. App không sử dụng trường reasoning làm nội dung dịch và không ghi nội dung suy luận ra giao diện.

Nếu còn lỗi sau khi cập nhật, chọn model văn bản khác trong menu Model ID, ví dụ `llama-3.3-70b-versatile` khi nhà cung cấp Groq và API key của bạn được phép sử dụng; kiểm tra kết nối API, sau đó dùng **BẮT ĐẦU TẠO TOÀN BỘ** để chạy lại phiên.

## 🔑 Cấu hình API đa nền tảng

**Giao diện thu gọn:** Thanh bên trái hiển thị hai mục đóng mặc định: **📥 Phụ đề YouTube dự phòng** và **🔑 Cấu hình API đa nền tảng**. Nhấn tiêu đề để mở khi cần nhập/sửa key, Base URL hoặc Model; nhấn lại để thu gọn. Các thông số đã nhập vẫn được dùng khi khung đóng, không cần giữ khung mở khi bấm **BẮT ĐẦU TẠO TOÀN BỘ**.

App hỗ trợ lựa chọn **Groq, Google Gemini, OpenAI, OpenRouter, DeepSeek, Together AI, Anthropic Claude** hoặc **API tương thích OpenAI (tùy chỉnh)**.

Tại thanh bên trái:

1. **CHỌN NỀN TẢNG AI**: chọn nhà cung cấp. Mỗi nền tảng có Base URL và model mặc định, nhưng bạn có thể sửa.
2. **🔐 API Key**: nhập khóa của nhà cung cấp tương ứng. Khi có Supabase, key sẽ được mã hóa và lưu theo tài khoản để sử dụng ở lần đăng nhập sau; nếu không có Supabase thì chỉ giữ trong kết nối. Key không lưu trong JSON phiên hoặc GitHub. Với ứng dụng riêng, có thể cấu hình các khóa tại **App settings → Secrets** bằng tên: `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `TOGETHER_API_KEY`, `ANTHROPIC_API_KEY`.
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
