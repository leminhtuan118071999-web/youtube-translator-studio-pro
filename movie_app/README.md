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
Mở Cấu hình AI, nhập URL API tương thích OpenAI, Model ID và key. Nguồn sẽ gửi tới nhà cung cấp đó; có thể phát sinh phí. Khóa chỉ ở phiên, không lưu JSON.
Bấm Nhận diện nhân vật từ nguồn, kiểm tra tên/thiết kế, rồi Tự tạo đoạn phim. Nguồn được phân tích theo từng phần đầy đủ, sau đó lập dàn ý và tạo tối đa 150 đoạn x 8 giây. Không ép đủ 20 phút. Ngoại hình và giọng là đề xuất, không phải nhận diện hình ảnh. Thoại được chuyển thể, không cam kết trích nguyên văn. Kết quả cần duyệt trước khi tạo video.
Checkpoint giữ trong dự án, tải JSON trước khi đóng. Thử lại cùng nguồn và ngôn ngữ sẽ dùng lại các phần đã nhận; đổi nguồn hoặc ngôn ngữ sẽ phân tích lại. Chưa tự tạo ảnh/clip. Kiểm tra tự động JSON và dữ liệu không bảo đảm AI đúng toàn bộ nội dung.
