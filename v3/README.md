# LMT Video Editor V3 — bản dựng đầu tiên

App dựng video từ ảnh/video của bạn, chạy trong trình duyệt tại **http://localhost:8503**. FFmpeg xử lý trên Mac; không dùng Render để lưu hoặc dựng tệp lớn, không cần API key. V1/V2 và worker V2 không thay đổi.

## Chạy trên Mac M2

Cần Python 3.12 trở lên và FFmpeg/ffprobe. Nếu đã dùng Homebrew:

```bash
brew install ffmpeg-full
```

Nếu đã có worktree riêng `~/lmt-video-editor-v3`, cập nhật trong Terminal V3 (Ctrl+C và đợi dấu nhắc shell trước):

```bash
cd ~/lmt-video-editor-v3
git fetch origin v3/auto-video-editor
git merge --ff-only FETCH_HEAD
python3 v3/start_editor.py
```

Lần đầu, từ thư mục repository V2, tạo worktree riêng để không đổi file đang chạy của V2:

```bash
git fetch origin v3/auto-video-editor
git worktree add --detach ../lmt-video-editor-v3 FETCH_HEAD
cd ../lmt-video-editor-v3
python3 v3/start_editor.py
```

Có thể mở file `v3/Start-LMT-Editor.command` để khởi động lại. Launcher tự cập nhật thư viện trong môi trường riêng `v3/.venv-editor`, chỉ nghe `127.0.0.1:8503`. Để Terminal worker V2 tiếp tục chạy.

## Quy trình

1. Nhập tên riêng để tạo dự án (tên trống hoặc trùng sẽ được nhắc đổi). Có thể đổi tên tại **Tên và thông tin dự án → Lưu tên dự án** khi không dựng. Mỗi dự án có mã riêng và tiến trình riêng trên thanh bên. Tạo hoặc mở dự án khác không hủy tiến trình cũ; nếu dựng dự án mới, tác vụ mới chờ đến lượt. Tải ảnh/video. Tệp được xếp theo số trong tên: SC2 trước SC10.
2. Chỉnh thứ tự và thời lượng cảnh rồi **Lưu timeline**. Bỏ dấu “Dùng” để loại cảnh khỏi timeline; nguyên liệu trên đĩa vẫn giữ lại.
3. Tải giọng đọc và nhạc nền nếu cần. Có thể dựng không giọng đọc hoặc giữ âm thanh gốc.
4. Trong **03 · Phụ đề**, bấm **Nghe giọng đọc và tạo phụ đề**. App tự nhận diện ngôn ngữ, giữ nguyên ngôn ngữ lời đọc và lấy mốc từng từ bằng faster-whisper trên CPU. Lần đầu cần Internet để tải model đa ngôn ngữ (Small mặc định; Base/Tiny nhẹ hơn); các lần sau dùng model đã lưu. Âm thanh không gửi lên dịch vụ nhận diện. Có tiến trình riêng và nút hủy; tạo dự án mới không dừng tác vụ đang chạy. Có thể tải SRT UTF-8 hoặc nhập lời kể V2 thay thế; phụ đề từ văn bản vẫn chỉ ước lượng thời gian.
5. Chọn 9:16, 16:9 hoặc 1:1, 1080p/720p, căn đầy/có viền, cắt thẳng/mờ qua đen; chỉnh âm lượng, cỡ chữ và chọn tô sáng từng từ đang đọc hoặc hiển thị theo cụm lời, rồi lưu cấu hình.
6. Nhấn **Bắt đầu dựng MP4**. Tự khớp giọng đọc phân bổ tổng thời lượng theo tỷ lệ thời lượng cảnh đã nhập. Video ngắn lặp lại khi cần; không tự phân tích ngữ nghĩa để chọn đoạn hình.
7. Ngay trên nút **Bắt đầu dựng MP4**, dùng **Chọn thư mục lưu trên Mac** hoặc nhập đường dẫn. Khi dựng xong, tiến trình tự sao chép kết quả vào nơi đã chọn, kể cả khi đóng tab trình duyệt. Nếu ổ đĩa không khả dụng, MP4 nội bộ vẫn được giữ và app báo để lưu lại. Có thể bấm **Lưu vào thư mục đã chọn** sau khi hoàn tất để lưu thêm bản khác. Có thể lưu chỉ MP4 hoặc cả dự án/nguyên liệu để chỉnh sửa lại. Mỗi lần lưu tạo thư mục riêng, không ghi đè kết quả cũ. Có thể chọn thư mục khác và lưu lại mà không dựng lại.
8. Muốn mở lại bản đầy đủ đã lưu, dùng **Nhập dự án từ thư mục** ở thanh bên. App nhập một bản sao vào danh sách dự án; bản đã lưu tại nơi bạn chọn vẫn được giữ nguyên.
9. Ngoài ra vẫn có thể tải MP4 trực tiếp (tệp ≤250 MB) hoặc mở thư mục kết quả nội bộ. Tệp lớn giữ nguyên trên ổ đĩa.

## Lưu trữ và chạy ngầm

Dự án nằm tại `~/Library/Application Support/LMTStudioPro/V3`, ngoài Git. Mỗi lần dựng có bản chụp đầu vào riêng và thư mục kết quả riêng; lần dựng sau không ghi đè MP4 cũ.

Tiến trình dựng chạy độc lập với tab trình duyệt. Trên Mac có `caffeinate` ngăn ngủ do không thao tác trong khi đang dựng. **Máy phải còn bật, không gập nắp và còn dung lượng đĩa**. Tắt máy hoặc buộc dừng tiến trình sẽ làm lần dựng gián đoạn; mở lại app có thể dựng lại từ dự án đã lưu. Bản đầu chưa tiếp tục mã hóa từ frame dở dang.

Mỗi máy dựng một dự án tại một thời điểm; dự án khác sẽ chờ. Nút **Hủy dựng video** hủy cả tác vụ đang chờ. Không xóa nguyên liệu gốc. Dự án và tệp xuất chưa có cơ chế tự dọn dung lượng.

## Giới hạn hiện tại

- Đây là app **local trên Mac**, chưa phải giao diện upload từ xa trên Render.
- Tối đa 300 cảnh, 4 giờ cho timeline, uploader tối đa 1 GB mỗi tệp. Cần đủ ổ đĩa cho nguyên liệu, các cảnh đã chuẩn hóa và MP4 cuối.
- Chưa có tạo video AI, nhận diện người nói, chọn cảnh theo nội dung hoặc tách nhiều người nói.
- Nhận diện có thể sai với tên riêng, tiếng ồn hoặc giọng khó nghe; tự nhận diện ngôn ngữ có thể sai với đoạn quá ngắn. Cần xem thử trước khi đăng. Thay file giọng đọc sẽ bỏ phụ đề tự nhận diện cũ. Chưa có màn hình chỉnh từng từ.
- Phụ đề cần bản FFmpeg có bộ lọc `subtitles` (libass); engine báo rõ nếu thiếu.
- Xác minh FFmpeg và Streamlit trong Linux CI; chưa kiểm thử trực tiếp trên Mac M2 của người dùng.

## Kiểm thử

```bash
python3 -m pip install -r v3/requirements.txt
python3 -m unittest discover -s v3/tests -p 'test_*.py' -v
```

Các test thực sự chạy FFmpeg: ghép ảnh/video, kiểm tra pixel/thứ tự cảnh, độ dài theo giọng đọc, audio, Unicode/SRT, khung hình, hủy và chạy process độc lập. AppTest xác minh tạo và mở lại dự án không cần cấu hình tài khoản.

## Dựng kể chuyện như video mẫu (mục 05)

1. Tải ảnh nhân vật, giọng chính, giọng mở đầu riêng (tùy chọn) và nhiều video nền. Ảnh nhân vật là lớp phía trước, không phải một cảnh thay thế nền. Lưu nguyên liệu và bố cục.
2. Có thể tìm video Pixabay bằng từ khóa, chọn tối đa 15 clip khác nhau cho **toàn bộ dự án**. Khóa API nhập trong mục cấu hình Pixabay, chỉ lưu trên máy và không vào bundle. Tìm kiếm do người dùng bấm, kết quả cache 24 giờ; không quét hoặc tải hàng loạt nền. Clip đã tải được giữ để dựng lại; giới hạn không đặt lại khi thử lại/đổi từ khóa. Chưa có khóa vẫn dùng video nền tải lên được.
3. Bấm **Tách nền để xem trước**. Model rembg u2netp chạy CPU trên máy; lần đầu tải model. PNG trong suốt có thể bỏ tách nền. Các vùng chữ nhật “Giữ thêm chi tiết” khôi phục nguyên ảnh trong vùng đó (bao gồm nền trong vùng), không phải cọ chỉnh mặt nạ. Có thể dùng PNG đã chỉnh bên ngoài khi cần đường viền chính xác. Xem thử bố cục từ một video nền đã lưu, chỉnh kích thước và vị trí rồi lưu lại.
4. Sang **04 · Xuất video**, chọn nơi lưu trước nút bắt đầu. Khi chế độ kể chuyện được bật, tác vụ tự tách nền → tải clip đã chọn → nối mở đầu và giọng chính → nhận diện từng file giọng → dựng MP4 và lưu kết quả. Tắt chế độ trong mục 05 để quay lại timeline thủ công.
5. Nền giữ tốc độ thật, nối theo thứ tự rồi lặp **cả danh sách**, cắt vừa tổng thời lượng hai file giọng. Không sao chép video thành nhiều tệp. Âm thanh gốc của nền bị tắt; nhạc nền tùy chọn vẫn dùng từ mục 02.
6. Phụ đề giữ ngôn ngữ của từng file, thời điểm giọng chính được cộng đúng thời lượng phần mở đầu. Tách nền, giọng đã nối và phụ đề được cache theo đầu vào. Có nút hủy; đổi/tạo dự án không hủy tác vụ cũ. Mỗi máy xử lý một tác vụ nặng một lần để hạn chế quá tải.

Launcher trên Mac tự ưu tiên ffmpeg-full đã cài bằng Homebrew. Chưa kiểm tra trực tiếp trên Mac M2; chất lượng tách tóc/vật thể mảnh và nhận diện tên riêng cần xem lại. Bản xuất đầy đủ giữ ảnh gốc, ảnh tách nền, hai giọng gốc, giọng đã nối, nền và phụ đề để mở lại. Chưa có khóa Pixabay trong môi trường kiểm thử nên tải trực tiếp với tài khoản người dùng chưa được xác minh; kiểm thử tải/cache/giới hạn dùng phản hồi mô phỏng và media thật.
