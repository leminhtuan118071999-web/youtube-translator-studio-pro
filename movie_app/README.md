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
