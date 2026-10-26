# 🎬 LMT Studio Pro

Ứng dụng Streamlit xử lý video YouTube: trích xuất phụ đề có sẵn (khi YouTube cho phép), dịch bằng Gemini/OpenAI API, tạo 20 prompt hình ảnh, dịch tiêu đề/mô tả và SEO, xem và tải thumbnail.

## ☁️ Tự động lưu toàn bộ dữ liệu và cấu hình API qua lần đăng nhập sau

Để lưu bền vững, admin kết nối một dự án Supabase có xác thực email và RLS. Khi đăng nhập, người dùng sẽ thấy lại mọi phiên đã đồng bộ: bản dịch, prompt ảnh, SEO, phụ đề, link video, tên phiên, trạng thái và cấu hình các nhà cung cấp API. Nhà cung cấp hiện chọn, Base URL, Model ID và API key do người dùng nhập đều được nhớ đến khi thay đổi. Supadata API key cũng được hỗ trợ.

### Bật lưu trữ

1. Tạo dự án Supabase tại https://supabase.com/dashboard và bật Email authentication.
2. Mở SQL Editor của Supabase, chạy file [supabase_schema.sql](supabase_schema.sql) trong repository. Bảng có Row Level Security: tài khoản chỉ đọc/ghi dữ liệu của chính mình.
3. Sinh Fernet key bằng Python và cryptography: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
4. Thêm vào Streamlit Cloud → App settings → Secrets ba giá trị: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SESSION_ENCRYPTION_KEY`. Dùng giá trị riêng của dự án, tuyệt đối không commit các giá trị vào GitHub.
5. Khởi động lại app. Màn hình tạo tài khoản/đăng nhập sẽ xuất hiện. Khi đăng nhập, dữ liệu của tài khoản được khôi phục và những thay đổi mới được tự lưu. Không cần thao tác lưu thủ công: ứng dụng tự đồng bộ phiên và cấu hình ở mỗi lần cập nhật.

**Bảo mật:** API key được mã hóa Fernet trên Streamlit server trước khi lưu vào Supabase, và dữ liệu được giới hạn cho từng tài khoản bằng RLS. Người quản trị sở hữu khóa Fernet vẫn có thể giải mã nên đây không phải mã hóa end-to-end. Đừng thay hoặc làm mất khóa Fernet; đừng dùng Supabase service-role key. Key từ Streamlit Secrets dùng chung trên máy chủ không được sao chép vào dữ liệu cá nhân.

**Chưa kết nối Supabase:** App tự động nén và lưu **danh sách phiên, bản dịch, prompt, SEO, trạng thái và phiên đang chọn** vào `localStorage` của chính trình duyệt đang mở. Khi tải lại trang hoặc đóng rồi mở lại cùng địa chỉ Streamlit Cloud **trên đúng trình duyệt đó**, danh sách được khôi phục tự động; khi máy chủ khởi động lại, các tác vụ đang chạy được đánh dấu gián đoạn để có thể chạy lại. **Không đưa API key, token đăng nhập hoặc cấu hình bí mật vào bản lưu trình duyệt.** Nếu chưa có Supabase thì API key có thể cần nhập lại sau khi tải lại trang. Nếu dùng tab ẩn danh, xóa dữ liệu website, đổi trình duyệt/máy tính hoặc vượt hạn mức bộ nhớ trình duyệt thì dữ liệu có thể không còn hoặc không lưu được. Mục sao lưu/khôi phục JSON thủ công đã được gỡ khỏi giao diện theo yêu cầu; nếu trình duyệt chặn lưu hoặc dữ liệu website bị xóa thì các phiên không đồng bộ Supabase có thể mất. Để đồng bộ nhiều thiết bị hoặc khôi phục an toàn theo tài khoản, dùng Supabase.

**Tác vụ đang chạy:** Kết quả đã đồng bộ vẫn tồn tại khi đóng app. Job đang chạy trong bộ nhớ vẫn có thể dừng khi đóng tab hoặc Streamlit Cloud khởi động lại; hệ thống tải lại phần kết quả đã lưu và cho phép chạy lại. Tránh mở nhiều tab cùng tài khoản để chỉnh sửa đồng thời.
## 🚀 Tạo toàn bộ bằng một nút

1. Ở thanh bên trái, chọn nhà cung cấp AI, Base URL, Model ID và nhập API key. **🌍 Ngôn ngữ đích** được chọn ở khu vực chính, ngay trên nút **🚀 BẮT ĐẦU TẠO TOÀN BỘ**.
2. Dán link YouTube vào ô **🔗 Dán link video YouTube** rồi nhấn **🚀 BẮT ĐẦU TẠO TOÀN BỘ**. Phụ đề gốc sẽ được xử lý nội bộ, không hiển thị ô nhập văn bản gốc.
3. App tự động: tìm phụ đề thủ công hoặc phụ đề tự động có sẵn trên YouTube → dịch toàn bộ nội dung sang ngôn ngữ đích → tạo **20 prompt hình ảnh bằng ngôn ngữ đích** → tạo **tiêu đề, mô tả, từ khóa SEO bằng ngôn ngữ đích**.
4. Sau khi chạy, app chỉ hiển thị nội dung theo **ngôn ngữ đích** trong các tab kết quả. **Bản dịch hoàn chỉnh** và **Mô tả đã dịch** được thu gọn mặc định; nhấn tiêu đề để mở xem toàn bộ. Nút **⬇️ Tải nội dung (.txt)** chỉ còn trong phần **Bản dịch hoàn chỉnh**; các phần prompt, tiêu đề, mô tả và SEO không còn nút tải TXT. **Nút 📋 Copy toàn bộ luôn nằm bên ngoài khung**, dùng một lần nhấn để sao chép trọn vẹn từng mục (bản dịch, 20 prompt, tiêu đề, mô tả, từ khóa SEO) kể cả khi bản dịch/mô tả đang thu gọn. Nút sẽ báo đã sao chép khi trình duyệt cho phép; nếu trình duyệt chặn clipboard, vẫn có nút Copy trong khung nội dung khi mở rộng. Không còn danh sách Copy từng cảnh hoặc khối Copy gộp tiêu đề • mô tả • SEO.
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
- **📚 Danh sách phiên đã chạy** hiển thị phiên đang chạy (⏳), hoàn thành (✅) và **mọi phiên đã chạy nhưng lỗi (⚠️), kể cả khi chưa lấy được phụ đề hoặc chưa có bản dịch**. Nhấn một lần vào tên để xem kết quả/trạng thái; nhấp đúp vào ô tên để đổi ngay tại chỗ. Nút Xóa đỏ bên cạnh có bước xác nhận.
- Sau khi API xử lý xong, kết quả của đúng phiên đó sẽ tự được đưa vào dữ liệu phiên và danh sách tự cập nhật. Có thể mở lại để copy bản dịch, 20 prompt, tiêu đề, mô tả, SEO.
- Tối đa 3 tác vụ đồng thời trong một phiên kết nối; máy chủ chạy tối đa 3 luồng worker. Nút **Xóa tất cả phiên đã lưu** yêu cầu xác nhận, hủy các tác vụ chưa chạy và yêu cầu tác vụ đang chạy ngừng ở bước tiếp theo.
- Nếu phụ đề hoặc API lỗi ở bất cứ bước nào, phiên vẫn giữ trong danh sách kèm lý do lỗi. Các phần đã xử lý thành công xuất hiện khi bạn mở lại phiên; có thể thử chạy lại. Worker chia sẻ kết quả từng bước với giao diện thay vì chỉ đến cuối mới lưu.

**Giới hạn kỹ thuật:** Xử lý nền vẫn chạy trong bộ nhớ Streamlit, không phải hàng đợi bền vững. Nếu tab bị đóng hoặc máy chủ khởi động lại trong lúc đang chạy, tác vụ có thể dừng. Với Supabase, phần kết quả đã đồng bộ được giữ theo tài khoản; nếu chưa có Supabase thì bản phiên đã lưu trong trình duyệt cùng máy có thể được khôi phục (không bảo đảm khi trình duyệt bị xóa dữ liệu). Muốn đảm bảo tác vụ vẫn hoàn thành sau khi server khởi động lại cần job queue riêng.

## 🎨 Màu nút quản lý phiên

- **➕ Tạo phiên mới:** nút nền xanh lá.
- Trong **📚 Danh sách phiên đã chạy**, tên phiên **hoàn thành** có nền xanh lá; phiên **đang chạy, chưa xong, lỗi hoặc bị gián đoạn** có nền đỏ.
- **Phiên đang được chọn để xem** luôn có nền vàng, không phụ thuộc trạng thái xử lý. Khi mở sang phiên khác, ô đang xem chuyển vàng còn ô vừa bỏ chọn trở về xanh/đỏ đúng trạng thái.
- **Nhấp một lần vào ô tên** để mở phiên; **nhấp đúp vào chính ô đó** để chỉnh sửa tên tại chỗ, nhấn **Enter** hoặc nhấp ra ngoài để lưu; nhấn **Esc** để hủy sửa. Nút Đổi tên riêng đã được bỏ.
- Chỉ còn nút **Xóa** nền đỏ bên phải ô tên; vẫn cần xác nhận trước khi xóa. Ô tên không còn biểu tượng dấu tích xanh (✅ hoặc ✓), vì màu nền đã biểu thị trạng thái.

## 📁 Phần quản lý phiên ở góc trái (đã tối giản)

Ô **🌍 Ngôn ngữ đích** nằm ở khu vực chính, ngay trước nút **🚀 BẮT ĐẦU TẠO TOÀN BỘ**, với tiếng Ý, Bồ Đào Nha, Hà Lan, Thụy Điển, Séc, Romania, Hungary, Ukraine và nhiều ngôn ngữ châu Âu khác. Mỗi phiên có ngôn ngữ đích riêng.

Ngay bên dưới là **📁 Quản lý phiên làm việc**:
1. Nhấn **➕ Tạo phiên mới**: nếu phiên cũ đang xử lý, app **không dừng tác vụ cũ**; bạn có thể bắt đầu công việc khác. Khi phiên cũ hoàn thành, app tự lưu kết quả vào **📚 Danh sách phiên đã chạy** trong kết nối hiện tại. Phiên chưa chạy sẽ không vào danh sách.
2. Khi đã nhấn **BẮT ĐẦU TẠO TOÀN BỘ**, phiên xuất hiện ngay là **⏳ đang chạy**. Sau khi hoàn tất hiện **✅**. Nếu lỗi ở bước đầu hoặc giữa quy trình, phiên vẫn hiển thị **⚠️**, đồng thời có thông báo nguyên nhân khi mở phiên. Phiên mới chưa bấm Bắt đầu không xuất hiện.
3. Trong danh sách, **nhấn trực tiếp vào tên phiên** để xem lại phụ đề, bản dịch, prompt và SEO; **không có nút “Mở”**.
4. Để đổi tên, **nhấp đúp trực tiếp vào ô tên phiên**, nhập tên mới ngay tại ô rồi nhấn Enter (hoặc nhấp ra ngoài) để lưu. Có thể nhấn Esc để hủy. **Không còn nút Đổi tên riêng và không có dấu ✓/✅ bên trong tên.**
5. Với mỗi phiên, nhấn **Xóa (đỏ)** bên cạnh tên rồi **✅ Xác nhận xóa** để xóa riêng phiên đó. App hủy tác vụ của đúng phiên, bỏ bản dịch, prompt, SEO và dữ liệu tạm gắn với phiên, sau đó đồng bộ danh sách đã giảm vào Supabase (nếu có). Nếu dùng bộ nhớ trình duyệt, bản lưu tự được ghi đè và xác nhận cập nhật; khi Supabase đang dùng, app cũng xóa bản lưu trình duyệt cũ để tránh khôi phục nhầm sau này. **🗑️ Xóa tất cả phiên đã lưu** có ô xác nhận riêng và đặt lại về một phiên trống. API key/cấu hình chung không bị xóa. **Giới hạn:** Không thể tự xóa các file JSON đã tải xuống, ảnh/đoạn văn đã sao chép sang nơi khác, dữ liệu lưu của những trình duyệt/thiết bị khác hoặc bản sao lưu riêng của nhà cung cấp. Nếu có nhiều tab đang mở cùng lúc, hãy tải lại chúng để tránh ghi đè dữ liệu cũ.

**Giới hạn:** Chưa cấu hình Supabase, danh sách phiên được tự lưu trong trình duyệt này (không lưu API key) và sẽ khôi phục khi mở lại cùng địa chỉ. Dữ liệu có thể mất nếu xóa site data hoặc vượt dung lượng; hiện giao diện không còn nút tải/khôi phục JSON thủ công. Khi Supabase được bật, dữ liệu đồng bộ theo tài khoản. Công việc đang chạy vẫn có thể gián đoạn khi máy chủ khởi động lại.

Dữ liệu mỗi phiên được tách riêng: link YouTube, phụ đề gốc, bản dịch, tiêu đề, mô tả, prompt ảnh, nội dung SEO, ngôn ngữ dịch.



## Các phần khác được giữ nguyên

- Dịch văn bản, tạo prompt và SEO bằng nhiều nhà cung cấp AI; API key và model tùy chọn.
- Copy bản dịch, prompt, tiêu đề, mô tả và SEO bằng ngôn ngữ đích; **không hiển thị hoặc Copy phụ đề/tiêu đề/mô tả gốc**.
- Tự động trích xuất phụ đề từ link YouTube bằng nút **BẮT ĐẦU TẠO TOÀN BỘ**; không hiển thị các ô phụ đề, tiêu đề hoặc mô tả gốc.
- Xem trước và tải thumbnail nếu truy cập được.

## ⏳ Tự động xử lý Groq HTTP 429 (giới hạn token/phút)

**Đối với Groq GPT-OSS, 8.000 token/phút là hạn mức tổng của model, không phải số token cho mỗi đoạn.** App chia văn bản dài thành nhiều đoạn nhỏ (tối đa 2.200 ký tự nguồn mỗi đoạn với GPT-OSS), dịch tuần tự và ghép các đoạn theo đúng thứ tự. Các yêu cầu Groq dùng chung API key + model trên máy chủ được điều tiết theo ngân sách mềm 7.200 token trong cửa sổ 65 giây để giảm lỗi 429. Đây là ước tính bảo thủ, không thể đảm bảo khi cùng tài khoản còn gọi API từ bên ngoài, chạy nhiều máy chủ hoặc khi hạn mức thực khác 8.000 TPM. Nếu bị giới hạn, app vẫn ưu tiên thời gian chờ do Groq thông báo.

Nếu Groq báo lỗi `429 Rate limit reached` và có thông báo `Please try again in 11.52s`, điều đó **không có nghĩa API key sai**. Model `openai/gpt-oss-120b` trên gói miễn phí có giới hạn 8.000 TPM (thời điểm tài liệu được tra cứu). Giới hạn mỗi tổ chức và mỗi model có thể thay đổi.

Ứng dụng hiện:
- Đọc `Retry-After` của Groq hoặc thời gian trong thông báo, cộng thời gian đệm, rồi **tự đợi và thử lại** yêu cầu vừa bị 429 (tối đa 6 lần thử lại). Trạng thái chờ xuất hiện trong tiến trình phiên.
- Chia nhỏ phụ đề thành các đoạn ngắn hơn khi dùng Groq GPT-OSS. Các đoạn đã dịch thành công được giữ lại, không bắt đầu toàn bộ từ đầu khi một đoạn gặp 429.
- Giảm `max_completion_tokens` của dịch từ 8.192 xuống 2.200 token, giữ 3.600 token khi tạo 20 prompt, và dùng tóm tắt phân tầng cho nội dung dài nhằm giảm đỉnh nhu cầu TPM.
- Nếu vượt quota **theo ngày** (TPD/RPD), app dừng thử lại vô ích và hướng dẫn chờ hạn mức mới hoặc chọn model khác.
- Nếu 6 lần thử lại vẫn bị giới hạn, phiên hiện ⚠️ cùng thông báo rõ ràng và giữ các kết quả đã xử lý được.

Lưu ý: App **không thể tăng hạn mức thật** của Groq hay bảo đảm mọi video dài sẽ hoàn thành trong hạn mức miễn phí. Nếu cần xử lý nhanh nhiều video, chọn nhà cung cấp/model có hạn mức cao hơn hoặc nâng gói của nhà cung cấp. Tham khảo [Groq rate limits](https://console.groq.com/docs/rate-limits).

## 🔧 Lỗi API có phản hồi nhưng không trả văn bản

Một số model có suy luận (đặc biệt `openai/gpt-oss-120b` trên Groq) có thể dùng hết quota token đầu ra cho reasoning trước khi xuất bản dịch. App đã tối ưu riêng GPT-OSS trên **Groq** với `reasoning_effort=low` và số token đầu ra phù hợp từng loại nội dung và không yêu cầu trả lại reasoning. Các nhà cung cấp khác giữ cấu hình riêng để tránh lỗi 400 do tham số không được hỗ trợ.

Nếu API trả về không có text, app sẽ giải thích `finish_reason` (ví dụ `length` khi hết token, hoặc `tool_calls` khi model chỉ gọi công cụ) thay vì báo chung chung. App không sử dụng trường reasoning làm nội dung dịch và không ghi nội dung suy luận ra giao diện.

Nếu còn lỗi sau khi cập nhật, chọn model văn bản khác trong menu Model ID, ví dụ `llama-3.3-70b-versatile` khi nhà cung cấp Groq và API key của bạn được phép sử dụng; kiểm tra kết nối API, sau đó dùng **BẮT ĐẦU TẠO TOÀN BỘ** để chạy lại phiên.

## 🛠️ Lỗi Claude Gateway HTTP 502 / 503 / 504

Nếu bấm **🧪 Kiểm tra kết nối API** và nhận `HTTP 502: Upstream service temporarily unavailable` từ một Claude Gateway bên thứ ba, điều này cho thấy gateway hoặc dịch vụ phía sau đang gặp lỗi tạm thời. **Không thể khẳng định API key sai chỉ từ mã lỗi 502.** Đừng cố thay model hoặc nhập lại token nhiều lần khi chưa có thông tin từ nhà cung cấp.

LMT Studio Pro đã tách riêng các mã 502/503/504 với lỗi 401/403 (xác thực/quyền) và lỗi 429 (quota). Khi nhấn **BẮT ĐẦU TẠO TOÀN BỘ**, mỗi yêu cầu gặp 502/503/504 sẽ được thử lại tối đa 3 lần với khoảng chờ tăng dần và khả năng hủy. Những đoạn đã dịch trước đó không bị dịch lại. Việc thử lại lệnh POST có thể phát sinh chi phí trùng nếu upstream thực tế đã xử lý xong nhưng gateway không gửi được kết quả, nên số lần thử được giới hạn.

Khi kiểm tra kết nối Claude/Gateway bằng yêu cầu ngắn, ứng dụng chỉ yêu cầu tối đa 128 token đầu ra thay vì dự phòng 8.192 token. Những tác vụ dịch, prompt, SEO có ngân sách đầu ra riêng. Đây là biện pháp giảm tải, **không thể sửa gateway đang ngừng hoạt động**.

Nếu gateway liên tục trả 502: thử lại khi dịch vụ phục hồi, kiểm tra thông báo trạng thái của nhà cung cấp, hoặc chuyển sang **Claude (Anthropic)** chính thức với API key Anthropic riêng. Không đưa token vào ảnh chụp màn hình hoặc GitHub.

## 🔗 Claude Code Gateway (AUTH_TOKEN) – dịch vụ API qua máy chủ trung gian

App có hai cách kết nối Claude:

- **Claude (Anthropic)**: dịch vụ chính thức, dùng Base URL `https://api.anthropic.com/v1` và Claude API key từ Anthropic Console.
- **Claude Gateway (AUTH_TOKEN)**: dành cho cấu hình Claude Code dùng `ANTHROPIC_BASE_URL` và `ANTHROPIC_AUTH_TOKEN`. Chọn mục này trong **🔑 Cấu hình API đa nền tảng**, nhập Base URL của gateway (ví dụ `https://your-trusted-gateway.example.com`), nhập **token mới** vào ô **🔐 Gateway AUTH_TOKEN** và model được gateway cho phép, rồi nhấn **🧪 Kiểm tra kết nối API**. App gửi `Authorization: Bearer <token>` và gọi chuẩn Messages API `/v1/messages`; khi Base URL chỉ là domain gốc, app tự thêm `/v1` trước đường dẫn `/messages`.

`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` là cấu hình riêng của Claude Code, **không cần nhập vào LMT Studio Pro**. Token phát hành bởi gateway **không mặc nhiên dùng được** với API chính thức của Anthropic; gateway có thể sử dụng đường dẫn, quyền truy cập hoặc danh sách model riêng. Nếu gateway không hỗ trợ chuẩn Anthropic Messages API, chức năng này có thể không kết nối được.

**Bảo mật:** Không chia sẻ ảnh chụp có token thật, không dán token vào GitHub hay nội dung công khai. Nếu token đã lộ, hãy thu hồi và tạo mới từ bên cấp token. Chỉ dùng gateway đáng tin cậy, vì token và nội dung sẽ được chuyển tới máy chủ của gateway. LMT Studio Pro không xác nhận hoặc bảo đảm chất lượng của các gateway bên thứ ba.

## 🌐 API bên thứ ba – tự nhập Key, Base URL và Model ID

Trong sidebar, mở **🔑 Cấu hình API đa nền tảng**, chọn **API bên thứ ba (tùy chỉnh)**. Người dùng có thể nhập riêng:

- **📡 Chuẩn API:** OpenAI Chat Completions (endpoint `/chat/completions`) hoặc Anthropic Messages (endpoint `/messages`).
- **🔏 Kiểu xác thực:** `Authorization: Bearer <token>` hoặc header `x-api-key`.
- **🔐 API Key**, **🌐 Base URL**, **🤖 Model ID:** nhập theo hướng dẫn của bên cung cấp dịch vụ, không bắt buộc phải là Claude/Groq hay nhà cung cấp có sẵn.

Ví dụ: dịch vụ OpenAI-compatible thường nhập Base URL `https://provider.example/v1`, chọn **OpenAI Chat Completions** và **Bearer Token**. Gateway tương thích Claude Code có thể nhập Base URL `https://provider.example`, chọn **Anthropic Messages** và **Bearer Token**; khi Base URL chỉ là tên miền gốc, ứng dụng tự thêm `/v1/messages`. Nếu cung cấp đường dẫn gốc API khác, app nối `/messages` sau đường dẫn đó.

Bấm **🧪 Kiểm tra kết nối API** để gửi một tin nhắn thử và xem lỗi HTTP nếu có. **🔎 Quét Model từ API** không nhất thiết khả dụng ở gateway bên thứ ba: có thể nhập Model ID bằng tay rồi thử kết nối. Việc điền đủ ba trường không bảo đảm máy chủ cung cấp model đó hay dịch vụ của họ hoạt động (ví dụ HTTP 502).

Cấu hình riêng này được dùng xuyên suốt quá trình tạo bản dịch, prompt và SEO. Khi Supabase được kết nối, URL, model, lựa chọn giao thức/cách xác thực và API key được mã hóa/lưu theo tài khoản tương tự các provider khác; nếu chưa kết nối Supabase thì các thông số chỉ tồn tại trong phiên Streamlit đang mở.

**Bảo mật:** Chỉ nhập key từ dịch vụ bạn tin tưởng; app chặn Base URL không phải HTTPS công khai và không theo chuyển hướng. Không gửi key hoặc token vào ảnh chụp, GitHub hay đoạn chat. Token từng xuất hiện công khai cần được thu hồi trước khi dùng tiếp.

## 🆓 Cấu hình Groq và Gemini trên gói miễn phí

**Phân biệt Groq và Grok:** `Groq` là dịch vụ GroqCloud có model GPT-OSS, còn `Grok` là model của xAI. LMT Studio Pro có mục **Groq**; API key xAI không sử dụng thay cho API key Groq.

Trong sidebar, mở **🔑 Cấu hình API đa nền tảng**:

- **Groq (GroqCloud):** Lấy API key tại https://console.groq.com/keys, chọn Groq. Base URL `https://api.groq.com/openai/v1`; model khởi tạo mới `openai/gpt-oss-20b`. Model `openai/gpt-oss-120b` vẫn có thể sử dụng khi tài khoản được cấp quyền, nhưng free tier thường dễ đạt hạn mức 8.000 token/phút khi xử lý video dài. Groq áp dụng nhiều loại hạn mức (TPM, RPD, TPD); hãy đối chiếu https://console.groq.com/settings/limits.
- **Gemini (Google AI Studio):** Tạo key tại https://aistudio.google.com/apikey, chọn Google Gemini. LMT Studio Pro dùng **API chính thức của Google** qua `https://generativelanguage.googleapis.com/v1beta`, gọi `models/{model}:generateContent` và header `x-goog-api-key`. Model mặc định `gemini-3.5-flash-lite` có Free Tier (mỗi tài khoản/dự án vẫn có giới hạn). Có thể dùng **🔎 Quét Model từ API** để lấy danh sách model được API key nhìn thấy. Kiểm tra https://aistudio.google.com/usage và https://ai.google.dev/gemini-api/docs/rate-limits.
- Với tài khoản đã dùng app phiên bản cũ, bấm **⚡ Áp dụng cấu hình phù hợp gói miễn phí** để đặt lại đúng Base URL và model mới mà không xóa API key. Các cấu hình Gemini cũ sử dụng đúng Base URL mặc định `/v1beta/openai` được tự nâng sang API gốc; Base URL hoặc model tự nhập không bị thay thế ngoài trường hợp khớp chính xác giá trị mặc định cũ.

**Cách thử:** Nhập key, chọn đúng model, bấm **🧪 Kiểm tra kết nối API** trước. HTTP 401/403: kiểm tra key và quyền API; HTTP 404: có thể sai Model ID; HTTP 429: đã vượt hạn mức. Nếu Gemini báo **limit: 0**, app sẽ giải thích quota miễn phí của model bằng 0 và ngừng tự thử lại vô ích; cần kiểm tra quyền dùng model/hạn mức ở Google AI Studio hoặc chọn model có quyền truy cập. **Không thể đảm bảo xử lý toàn bộ video dài mà không chạm hạn mức miễn phí**. Các lỗi do quota/key/quyền của dự án không thể sửa hoàn toàn bằng phần mềm, và ChatGPT Plus không bao gồm API trả phí của bên thứ ba.

## 🔑 Cấu hình API đa nền tảng

**Giao diện nhập API cơ bản:** Thanh bên vẫn giữ mục đóng mặc định **🔑 Cấu hình API đa nền tảng**. Mở mục này sẽ thấy theo thứ tự **Chọn nền tảng AI → API Key → Base URL → Model ID → Quét Model / Kiểm tra kết nối API**, giống cách nhập đơn giản ban đầu. Các thông báo hướng dẫn theo nhà cung cấp, nút áp dụng cấu hình miễn phí và hai lựa chọn giao thức/cách xác thực của **API bên thứ ba (tùy chỉnh)** được giữ nguyên trong nút **⚙️ Hướng dẫn và tùy chọn nâng cao**. Nút này đóng mặc định; bạn chỉ cần mở khi muốn thay đổi cấu hình nâng cao. Các thông số vẫn hoạt động khi nút đóng, không cần giữ khung mở khi chạy video. Mục **📥 Phụ đề YouTube dự phòng** vẫn được thu gọn như trước.

App hỗ trợ lựa chọn **Groq, Google Gemini, OpenAI, Claude (Anthropic), OpenRouter, DeepSeek, Together AI** hoặc **API tương thích OpenAI (tùy chỉnh)**. Mục **Claude (Anthropic)** nằm trong khung thu gọn **🔑 Cấu hình API đa nền tảng** ở thanh bên; chọn Claude để nhập API key chính thức từ [Anthropic Console](https://platform.claude.com/settings/keys). Claude dùng endpoint `https://api.anthropic.com/v1/messages` với model mặc định `claude-sonnet-4-6`. Dữ liệu Claude lưu dưới tên cũ *Anthropic Claude* được tự chuyển sang tên mới mà không làm mất API key.

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
| Gemini (Google API chính thức) | `https://generativelanguage.googleapis.com/v1beta` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| DeepSeek | `https://api.deepseek.com` |
| Together AI | `https://api.together.xyz/v1` |
| Claude (Anthropic) | `https://api.anthropic.com/v1` |

**Lưu ý:** Các dịch vụ OpenAI-compatible dùng endpoint chat completions; Anthropic dùng Messages API. Không phải mọi model đều hỗ trợ chức năng/dung lượng giống nhau. Quét model có thể không khả dụng trên một số server, nhưng vẫn có thể nhập thủ công. Base URL tùy chỉnh chỉ chấp nhận HTTPS công khai, chặn địa chỉ nội bộ và không tự theo chuyển hướng HTTP. Chỉ cung cấp API key cho máy chủ bạn tin tưởng vì key sẽ được gửi tới Base URL đã nhập. API có thể tính phí. Nếu app ở chế độ công khai và dùng key trong Secrets, cần bật hạn chế truy cập để tránh người khác sử dụng API của bạn.

## Triển khai

Repository: `leminhtuan118071999-web/youtube-translator-studio-pro`; branch: `main`; entry: `streamlit_app.py`.

Triển khai qua https://share.streamlit.io/ . Nếu app đã triển khai, Streamlit Community Cloud thường cập nhật sau khi commit; hãy làm mới trang để xem giao diện mới.

ChatGPT Plus không bao gồm quyền sử dụng API của Groq, Google Gemini, OpenAI hoặc các nhà cung cấp khác. Phụ đề có thể bị YouTube hạn chế trên hạ tầng Streamlit.

Tài liệu: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
