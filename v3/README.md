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

Giao diện chỉ giữ hai mục **04 · Xuất video** và **05 · Dựng kiểu video mẫu**.

1. Tạo/mở dự án có tên riêng ở thanh bên.
2. Trong **04**, chọn khung hình, độ phân giải, chuyển cảnh, âm lượng, cỡ chữ và cách hiện phụ đề ; cấu hình hiện tại tự được lưu khi bấm bắt đầu.
3. Trong **05**, thêm ảnh nhân vật, giọng mở đầu, giọng chính và video nền trên máy hoặc chọn Pixabay. Có thể tách nền/xem trước nếu cần; không bắt buộc bấm lưu riêng.
4. Ở **cuối mục 05**, chọn thư mục lưu, chọn lưu cả dự án/nguyên liệu nếu cần, rồi bấm **Bắt đầu dựng MP4**. Nút này tự lưu nguyên liệu, bố cục và cấu hình hiện tại, kiểm tra phần còn thiếu rồi chạy đến khi kết quả được sao chép vào nơi đã chọn. Cần chọn nơi lưu trước khi bắt đầu.
5. Có thể lưu thêm bản hoàn tất vào thư mục khác bằng **Lưu vào thư mục đã chọn**, và giữ bản đầy đủ để mở lại sau. Mỗi lần lưu tạo thư mục mới, không ghi đè dự án cũ. Video lớn vẫn giữ trên ổ đĩa; tải trực tiếp từ trình duyệt giới hạn 250 MB.

Các dự án cũ và nguyên liệu đã lưu vẫn được giữ. Các mục timeline thủ công, âm thanh và phụ đề riêng không còn hiển thị thành tab 01–03.

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

1. Tải ảnh nhân vật, giọng chính, giọng mở đầu riêng (tùy chọn) và nhiều video nền. Ảnh nhân vật là lớp phía trước, không phải một cảnh thay thế nền. Thông tin vừa nhập được lưu khi bấm bắt đầu.
2. Có thể tìm video Pixabay bằng từ khóa, chọn tối đa 15 clip khác nhau cho **toàn bộ dự án**. Khóa API nhập trong mục cấu hình Pixabay, chỉ lưu trên máy và không vào bundle. Tìm kiếm do người dùng bấm hoặc khi bấm bắt đầu với tùy chọn tự tìm nền và chưa có nền; kết quả cache 24 giờ; không quét hoặc tải hàng loạt nền. Clip đã tải được giữ để dựng lại; giới hạn không đặt lại khi thử lại/đổi từ khóa. Chưa có khóa vẫn dùng video nền tải lên được.
3. Bấm **Tách nền để xem trước**. Model rembg u2netp chạy CPU trên máy; lần đầu tải model. PNG trong suốt có thể bỏ tách nền. Các vùng chữ nhật “Giữ thêm chi tiết” khôi phục nguyên ảnh trong vùng đó (bao gồm nền trong vùng), không phải cọ chỉnh mặt nạ. Có thể dùng PNG đã chỉnh bên ngoài khi cần đường viền chính xác. Xem thử bố cục từ một video nền đã lưu, chỉnh kích thước và vị trí rồi lưu lại.
4. Chỉnh cấu hình trong **04 · Xuất video**, rồi chọn nơi lưu và bấm bắt đầu ở cuối **05 · Dựng kiểu video mẫu**. Không cần bấm nút lưu nguyên liệu/cấu hình riêng. Khi chế độ kể chuyện được bật, tác vụ tự tách nền → tải clip đã chọn → nối mở đầu và giọng chính → nhận diện từng file giọng → dựng MP4 và lưu kết quả. Tắt chế độ trong mục 05 để quay lại timeline thủ công.
5. Nền giữ tốc độ thật, nối theo thứ tự rồi lặp **cả danh sách**, cắt vừa tổng thời lượng hai file giọng. Không sao chép video thành nhiều tệp. Âm thanh gốc của nền bị tắt; nhạc nền đã lưu trong dự án cũ vẫn được giữ.
6. Phụ đề giữ ngôn ngữ của từng file, thời điểm giọng chính được cộng đúng thời lượng phần mở đầu. Tách nền, giọng đã nối và phụ đề được cache theo đầu vào. Có nút hủy; đổi/tạo dự án không hủy tác vụ cũ. Mỗi máy xử lý một tác vụ nặng một lần để hạn chế quá tải.

Launcher trên Mac tự ưu tiên ffmpeg-full đã cài bằng Homebrew. Chưa kiểm tra trực tiếp trên Mac M2; chất lượng tách tóc/vật thể mảnh và nhận diện tên riêng cần xem lại. Bản xuất đầy đủ giữ ảnh gốc, ảnh tách nền, hai giọng gốc, giọng đã nối, nền và phụ đề để mở lại. Chưa có khóa Pixabay trong môi trường kiểm thử nên tải trực tiếp với tài khoản người dùng chưa được xác minh; kiểm thử tải/cache/giới hạn dùng phản hồi mô phỏng và media thật.

Tiến trình hiển thị theo từng dự án: 1/6 tách nền, 2/6 chuẩn bị nền Pixabay/local, 3/6 nối giọng, 4/6 nhận diện phụ đề, 5/6 dựng MP4, 6/6 sao chép vào nơi lưu. Có thể hủy. Nếu thiếu đầu vào, nút bắt đầu báo tên phần cần bổ sung thay vì bị mờ theo thông tin lưu cũ.

## Tách nền ảnh nhiều nhân vật

Dùng BiRefNet General thay model nhẹ u2netp. Ảnh ngang từ 600 pixel được quét toàn ảnh và hai vùng chồng lấn, hợp nhất alpha để hạn chế bỏ sót người nhỏ hoặc ở rìa. Giữ RGB gốc, độ trong suốt đầu vào và mọi thành phần mask, không chỉ thành phần lớn nhất. Cache cũ tự hết hiệu lực ở lần dựng tiếp theo. Lần đầu cần mạng tải model; CPU/RAM và thời gian xử lý cao hơn.

Không bảo đảm nhận ra mọi người bị che khuất, không tạo phần cơ thể ngoài ảnh. Xem trước trước khi dựng; dùng vùng khôi phục nếu còn thiếu (vùng khôi phục giữ cả nền trong hình chữ nhật) hoặc PNG trong suốt đã chỉnh. Không dùng model nhẹ làm dự phòng âm thầm nếu tải model lỗi.
## Danh sách dự án

Thanh bên chỉ có tên dự án mới và nút tạo ở phía trên. Bên dưới là các nút tên dự án để mở trực tiếp, kèm trạng thái/tiến trình cập nhật tự động. Không còn ô chọn dự án hoặc mục nhập thư mục trên thanh bên.

**Xóa tất cả phiên → Xác nhận xóa tất cả** hủy các tác vụ V3 đang chạy/chờ, đợi tiến trình dừng rồi xóa toàn bộ dự án/nguyên liệu/kết quả nội bộ. Bản đã xuất ra thư mục bạn chọn, khóa Pixabay và các model đã tải được giữ. V2 không bị ảnh hưởng.
