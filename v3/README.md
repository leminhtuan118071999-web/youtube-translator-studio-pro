# LMT Video Editor V3 — bản dựng đầu tiên

App dựng video từ ảnh/video của bạn, chạy trong trình duyệt tại **http://localhost:8503**. FFmpeg xử lý trên Mac; không dùng Render để lưu hoặc dựng tệp lớn, không cần API key. V1/V2 và worker V2 không thay đổi.

## Chạy trên Mac M2

Cần Python 3.12 trở lên và FFmpeg/ffprobe. Nếu đã dùng Homebrew:

```bash
brew install ffmpeg
```

Trong thư mục repository, ở một Terminal **riêng** với worker V2:

```bash
git fetch origin
git switch v3/auto-video-editor
python3 v3/start_editor.py
```

Nếu Mac chưa có nhánh local, lệnh `git switch` tự tạo nhánh theo `origin/v3/auto-video-editor`. Không chạy các lệnh cập nhật trong lúc worker V2 đang xử lý tác vụ; đợi tác vụ kết thúc trước. Có thể mở file `v3/Start-LMT-Editor.command` để khởi động lại sau khi cài xong. Launcher tạo môi trường Python riêng tại `v3/.venv-editor` và chỉ nghe trên `127.0.0.1:8503`.

## Quy trình

1. Nhập tên riêng để tạo dự án (tên trống hoặc trùng sẽ được nhắc đổi). Có thể đổi tên tại **Tên và thông tin dự án → Lưu tên dự án** khi không dựng. Mỗi dự án có mã riêng và tiến trình riêng trên thanh bên. Tạo hoặc mở dự án khác không hủy tiến trình cũ; nếu dựng dự án mới, tác vụ mới chờ đến lượt. Tải ảnh/video. Tệp được xếp theo số trong tên: SC2 trước SC10.
2. Chỉnh thứ tự và thời lượng cảnh rồi **Lưu timeline**. Bỏ dấu “Dùng” để loại cảnh khỏi timeline; nguyên liệu trên đĩa vẫn giữ lại.
3. Tải giọng đọc và nhạc nền nếu cần. Có thể dựng không giọng đọc hoặc giữ âm thanh gốc.
4. Tải SRT UTF-8, hoặc dán văn bản, hoặc nhập bản dịch từ **Xuất phiên JSON** của V2. SRT được ưu tiên. **Phụ đề từ văn bản chỉ ước lượng thời gian**, không phải nhận diện/đồng bộ từng từ từ giọng nói; cần kiểm tra khi xem thử.
5. Chọn 9:16, 16:9 hoặc 1:1, 1080p/720p, căn đầy/có viền, cắt thẳng/mờ qua đen; chỉnh âm lượng và lưu cấu hình.
6. Nhấn **Bắt đầu dựng MP4**. Tự khớp giọng đọc phân bổ tổng thời lượng theo tỷ lệ thời lượng cảnh đã nhập. Video ngắn lặp lại khi cần; không tự phân tích ngữ nghĩa để chọn đoạn hình.
7. Sau khi hoàn tất, dùng **Chọn thư mục lưu trên Mac** hoặc nhập đường dẫn, rồi nhấn **Lưu vào thư mục đã chọn**. Có thể lưu chỉ MP4 hoặc cả dự án/nguyên liệu để chỉnh sửa lại. Mỗi lần lưu tạo thư mục riêng, không ghi đè kết quả cũ. Có thể chọn thư mục khác và lưu lại mà không dựng lại.
8. Muốn mở lại bản đầy đủ đã lưu, dùng **Nhập dự án từ thư mục** ở thanh bên. App nhập một bản sao vào danh sách dự án; bản đã lưu tại nơi bạn chọn vẫn được giữ nguyên.
9. Ngoài ra vẫn có thể tải MP4 trực tiếp (tệp ≤250 MB) hoặc mở thư mục kết quả nội bộ. Tệp lớn giữ nguyên trên ổ đĩa.

## Lưu trữ và chạy ngầm

Dự án nằm tại `~/Library/Application Support/LMTStudioPro/V3`, ngoài Git. Mỗi lần dựng có bản chụp đầu vào riêng và thư mục kết quả riêng; lần dựng sau không ghi đè MP4 cũ.

Tiến trình dựng chạy độc lập với tab trình duyệt. Trên Mac có `caffeinate` ngăn ngủ do không thao tác trong khi đang dựng. **Máy phải còn bật, không gập nắp và còn dung lượng đĩa**. Tắt máy hoặc buộc dừng tiến trình sẽ làm lần dựng gián đoạn; mở lại app có thể dựng lại từ dự án đã lưu. Bản đầu chưa tiếp tục mã hóa từ frame dở dang.

Mỗi máy dựng một dự án tại một thời điểm; dự án khác sẽ chờ. Nút **Hủy dựng video** hủy cả tác vụ đang chờ. Không xóa nguyên liệu gốc. Dự án và tệp xuất chưa có cơ chế tự dọn dung lượng.

## Giới hạn hiện tại

- Đây là app **local trên Mac**, chưa phải giao diện upload từ xa trên Render.
- Tối đa 300 cảnh, 4 giờ cho timeline, uploader tối đa 1 GB mỗi tệp. Cần đủ ổ đĩa cho nguyên liệu, các cảnh đã chuẩn hóa và MP4 cuối.
- Chưa có tạo video AI, nhận diện người nói, chọn cảnh theo nội dung hoặc nhận diện tiếng nói tự động.
- Phụ đề cần bản FFmpeg có bộ lọc `subtitles` (libass); engine báo rõ nếu thiếu.
- Xác minh FFmpeg và Streamlit trong Linux CI; chưa kiểm thử trực tiếp trên Mac M2 của người dùng.

## Kiểm thử

```bash
python3 -m pip install -r v3/requirements.txt
python3 -m unittest discover -s v3/tests -p 'test_*.py' -v
```

Các test thực sự chạy FFmpeg: ghép ảnh/video, kiểm tra pixel/thứ tự cảnh, độ dài theo giọng đọc, audio, Unicode/SRT, khung hình, hủy và chạy process độc lập. AppTest xác minh tạo và mở lại dự án không cần cấu hình tài khoản.
