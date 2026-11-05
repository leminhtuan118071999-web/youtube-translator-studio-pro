# LMT Film Builder alpha

## Mở bản có lấy phụ đề YouTube
```sh
git clone --branch v4/film-builder https://github.com/leminhtuan118071999-web/youtube-translator-studio-pro.git ~/lmt-film-builder
cd ~/lmt-film-builder
python3 movie_app/start.py
```
Mở http://127.0.0.1:8505. Launcher tạo Python venv riêng và cài youtube-transcript-api 1.2.3. Giữ Terminal trong lúc sử dụng. Không thay V2/V3.

Nhập link YouTube, bấm Lấy phụ đề YouTube. Chỉ lấy caption có sẵn, không tải hình ảnh/video, không tách người nói, không tự chuyển thể hoặc dịch. Nếu YouTube chặn hoặc không có phụ đề, thông báo lỗi và giữ nội dung cũ; dùng TXT/SRT/VTT hoặc dán nguồn. Không cắt nguồn vượt giới hạn.

46 ngôn ngữ đích trong danh sách; lựa chọn áp dụng cho prompt, không bảo đảm công cụ video hỗ trợ giọng đó.

Mở index.html trực tiếp vẫn dùng được phần nhập tay/xuất bộ, nhưng nút lấy YouTube cần máy chủ cục bộ.

## Lưu / xuất
Dữ liệu đang chỉnh ở trong phiên trình duyệt. Tải JSON trước khi đóng trang. JSON gồm cả ảnh và phụ đề theo mốc nếu lấy từ YouTube. ZIP xuất ảnh + mỗi dòng một prompt TXT + CSV + JSON. Chưa tạo clip/ảnh/thoại, chưa dựng MP4; chuyển cảnh chỉ lưu metadata.

## Kiểm tra
`python3 -m unittest movie_app.test_server`

## Tự động nhân vật và đoạn phim
Mở Cấu hình AI, nhập URL API tương thích OpenAI, Model ID và key. Nguồn sẽ gửi tới nhà cung cấp đó; có thể phát sinh phí. URL, model và key tự lưu trong localStorage của trình duyệt trên máy này đến khi thay đổi hoặc xóa cấu hình. Khóa không nằm trong JSON/ZIP. Lưu trữ không mã hóa; không dùng trên máy dùng chung. Xóa dữ liệu trình duyệt hoặc đổi địa chỉ mở app sẽ không còn cấu hình đó.
Bấm Nhận diện nhân vật từ nguồn, kiểm tra tên/thiết kế, rồi Tự tạo đoạn phim. Nguồn được phân tích theo từng phần đầy đủ, sau đó lập dàn ý và tạo tối đa 150 đoạn x 8 giây. Không ép đủ 20 phút. Ngoại hình và giọng là đề xuất, không phải nhận diện hình ảnh. Thoại được chuyển thể, không cam kết trích nguyên văn. Kết quả cần duyệt trước khi tạo video.
Checkpoint giữ trong dự án, tải JSON trước khi đóng. Thử lại cùng nguồn và ngôn ngữ sẽ dùng lại các phần đã nhận; đổi nguồn hoặc ngôn ngữ sẽ phân tích lại. Chưa tự tạo ảnh/clip. Kiểm tra tự động JSON và dữ liệu không bảo đảm AI đúng toàn bộ nội dung.

## Prompt tạo ảnh bên ngoài
Mỗi nhân vật có prompt ảnh tham chiếu riêng; mỗi đoạn có prompt ảnh đầu cảnh 16:9, nêu tên ảnh nhân vật cần đính kèm. Mở prompt rồi Sao chép; tạo ảnh bằng công cụ ngoài và tải PNG/JPG về đúng nhân vật/đoạn. Nút Tải prompt tạo ảnh (TXT) hoạt động trước khi có ảnh; ZIP cũng gồm image-prompts.txt. Prompt dùng mô tả hiện tại và cập nhật khi sửa mô tả. App chưa tự gọi API tạo ảnh.

## Chạy liên tiếp
Nút Chạy toàn bộ tự phân tích nguồn → nhận diện nhân vật → lập dàn ý → tạo mọi đoạn phim. Hiện phần trăm theo các bước hoàn tất, không phải ước tính thời gian hoặc tiến độ xử lý bên trong máy chủ AI. Hai nút chạy riêng vẫn dùng được. Lỗi/dừng giữ checkpoint để thử lại; tải JSON để lưu trước khi đóng trang. Giữ trang và máy chủ đang chạy đến hết. Chưa bao gồm tạo ảnh/video MP4.

## Đồng bộ nhân vật
Chế độ xuất mặc định Đồng bộ nhân vật: ZIP yêu cầu ảnh tham chiếu của các nhân vật xuất hiện, không yêu cầu ảnh đầu cảnh. Nạp ảnh characters/ vào Phúc Anh, đặt tên đúng tên file, dán prompts.txt (mỗi dòng một đoạn). Nút Tải prompt VIDEO xuất riêng không cần ZIP. Prompt ảnh image-prompts.txt chỉ dùng tạo ảnh ngoài. Các tên vắng mặt được thay bằng mô tả người ngoài khung trong chỉ dẫn hình ảnh; thoại giữ nguyên. Nếu prompt còn nhắc trên 3 tên trong thoại, xuất bị chặn kèm mã đoạn để sửa/tách, không tự sửa nghĩa lời thoại. Chưa kiểm thử trực tiếp trong Phúc Anh.

## Kiểm tra người nói và lời thoại
Sau khi tạo đoạn phim, app tự kiểm tra theo lô tối đa 8 đoạn với ngữ cảnh liền kề và nguồn văn bản (nguồn dài dùng ghi chú phân tích). Nút Kiểm tra người nói / lời thoại dùng cho dự án cũ. Chỉ sửa người nói nếu AI đưa căn cứ và người đó có trong khung hình; giữ nguyên câu thoại. Hiện lý do/căn cứ trong từng đoạn. Câu chưa rõ, nghi nhiều người nói hoặc trùng nguyên câu được đánh dấu cần xác nhận và chặn xuất video/ZIP. Có nút xác nhận thủ công sau khi đối chiếu. Sửa thoại/người nói yêu cầu kiểm tra lại. Kết quả/checkpoint lưu cùng JSON. Đây là kiểm tra bằng AI trên văn bản, không phải nhận diện giọng nói/hình ảnh và không bảo đảm đúng tuyệt đối. Tăng số lượt gọi API.

Cảnh không người: mở đoạn thiếu nhân vật và đánh dấu xác nhận cảnh phong cảnh/chuyển cảnh không có người, hoặc chọn đúng nhân vật nếu có người. Cảnh không người đã xác nhận xuất cùng TXT Đồng bộ nhân vật mà không yêu cầu ảnh nhân vật; cảnh có thoại vẫn cần người nói. Không tự gán nhân vật hoặc mặc định mọi đoạn thiếu tên đều là cảnh không người.

## Tách đoạn
Mở đoạn → Tách đoạn thành 2 form. Chia hành động/thoại, chọn tên nhân vật và người nói mỗi phần. Nội dung gốc nằm sẵn ở phần 1; phần 2 để trống để không tự bịa/lặp. Nếu đổi tổng nội dung lời thoại cần xác nhận. Mặc định chia đôi thời gian giữ lại, vẫn tạo clip 8 giây. Mã đoạn mới không trùng, hai phần nằm liền nhau, ảnh gốc chỉ giữ phần 1; kiểm tra thoại lại trước khi xuất. Không tự xử lý giới hạn 3 tên được nhắc trong lời thoại bằng cách thay đổi nghĩa.
