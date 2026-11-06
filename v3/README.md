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

## Cấu hình xuất dùng chung

Mục 04 tự lưu thông số xuất trên máy khi thay đổi: khung hình, độ phân giải, căn hình, chuyển cảnh, khớp giọng, ba mức âm lượng, hạ nhạc, cỡ chữ và kiểu phụ đề. Mặc định ban đầu: 16:9, 720p, cover, cut, khớp giọng, 0%/15%/100%, hạ nhạc bật, chữ 48, tô từng từ. Cấu hình giữ qua khởi động lại và áp dụng cho dự án mới hoặc lần dựng tiếp theo của dự án cũ. Snapshot đang chạy không đổi. Tệp output-defaults.json lưu cạnh cấu hình V3, không xóa khi xóa tất cả dự án. Cấu hình theo máy, không đồng bộ sang máy khác.

## 15 nền Pixabay riêng cho mỗi dự án

Khi bật tự tải Pixabay và không dùng video nền tải lên, dự án mới chọn đúng 15 ID chưa dùng trên máy, lưu bộ chọn trước khi tải và dùng lại khi retry. Lịch sử giữ qua xóa dự án để tránh lặp lại; các bản dự án cũ đã tải nền vẫn dùng bộ cũ. Tìm có phân trang/cache 24 giờ và tối đa 10 truy vấn mỗi lần chọn. Nếu không đủ video mới, tự thử từ gần nghĩa theo các nhóm rừng, biển, sông, núi, thác, thành phố, mưa, hoa, mây, giữ các từ mô tả còn lại. Chủ đề chưa có nhóm gần nghĩa giữ nguyên từ khóa; không tự nhảy sang chủ đề khác. Nếu vẫn không đủ 15 thì báo rõ để đổi chủ đề. ID khác không bảo đảm cảnh quay khác biệt hoàn toàn về thị giác. Lịch sử theo máy, không đồng bộ giữa nhiều máy. Giới hạn 15 video mỗi phiên, không phải tải kho hàng loạt.

## Tự tiếp tục sau khi mở lại máy

Launcher V3 chạy bước khôi phục trước Streamlit. Sau khi đăng nhập Mac, LaunchAgent tự gọi launcher; dự án có tác vụ mới nhất đang queued/running/interrupted nhưng không còn khóa worker được khởi động lại từ chính snapshot cũ, giữ nơi xuất và nguyên liệu. Worker còn sống được bỏ qua để tránh chạy trùng. Các dự án được xử lý qua khóa renderer dùng chung. Tác vụ completed/failed/cancelled hoặc có dấu cancel không tự chạy lại. Chỉ xét tác vụ mới nhất của mỗi dự án, tránh hồi sinh tác vụ cũ đã được thay thế.

Render MP4 bị ngắt được dựng lại; không nối tiếp từ phần trăm cũ. File tải/cutout/phụ đề được tái sử dụng khi cache còn hợp lệ. Máy phải đăng nhập, có mạng khi cần tải và không ngủ. Dữ liệu chưa bấm bắt đầu/lưu không thể khôi phục. V2 worker vốn tự nhận tác vụ queued/retry_wait và running hết lease, trong giới hạn số lần thử; lỗi nội dung/API và tác vụ đã hủy cần kiểm tra thủ công.

Nếu LaunchAgent đã cài, sau khi cập nhật mã chỉ cần khởi động lại riêng dịch vụ V3, không cài lại hai agent:

```sh
launchctl kickstart -k "gui/$(id -u)/com.lmtstudio.v3.editor"
```


## Bộ cài Windows x64

Mã đóng gói tại v3/windows; GitHub Actions **V3 Windows Installer** build Setup.exe bằng Inno Setup và runtime Python riêng. Người nhận không cần Git/Python/Terminal; mở shortcut, chọn thư mục, nhập Pixabay nếu dùng rồi thiết lập. Wizard tải FFmpeg có libass từ Gyan, xác minh SHA256, kiểm tra runtime và hỗ trợ cài Microsoft VC++ Runtime nếu thiếu (Windows có thể hỏi quyền quản trị cho thành phần hệ thống này). App chạy cục bộ trong trình duyệt. Windows 10/11 x64; ARM/32-bit chưa hỗ trợ. Có tùy chọn tự mở sau đăng nhập. Không kèm dự án/khóa của người phát triển.

Bản Windows cần qua kiểm tra runtime/renderer Windows và thử cài trên máy sạch trước khi phát hành rộng rãi. Setup hiện chưa ký số. Chi tiết và cách build: v3/windows/README.md.


## Video nền đa dạng từ nhiều từ khóa

Khi bật tự tải Pixabay, V3 mở rộng từ khóa đã nhập hoặc chủ đề thumbnail được nhận diện thành các từ khóa gần nghĩa, giữ các điều kiện như ban đêm, mùa đông. Lấy kết quả từ tối đa 3 từ khóa trước rồi chọn xen kẽ đủ 15 video mới. Chỉ tìm thêm từ khóa/trang khi thiếu; tối đa 10 lượt tìm mỗi lần chọn. Không gọi thêm AI để mở rộng từ khóa. Chủ đề chưa có từ gần nghĩa giữ nguyên từ khóa gốc, không thay bằng chủ đề ngẫu nhiên.

Lịch sử ID dùng chung loại video đã dùng giữa các dự án; danh sách đã chọn và các tệp tải xong được tái sử dụng khi chạy tiếp dự án. Kết quả tìm kiếm được giữ trong cache 24 giờ. Tiến trình hiển thị từ khóa đang tìm và số video đã chọn. Dự án đã có bộ video được giữ nguyên; cơ chế đa từ khóa áp dụng khi chọn bộ mới.

Video Pixabay mới chỉ được tải khi tỷ lệ là 16:9 (chấp nhận sai số làm tròn 1 pixel). Lọc theo kích thước từng bản video, làm mới cache tìm kiếm cũ và kiểm tra lại kích thước tệp tải về trước khi lưu. Không cắt video dọc/vuông thành 16:9 để thay thế. Tệp cũ không bị xóa; bộ đã chọn cũ sai tỷ lệ cần tạo dự án mới.

Tự phối chủ đề liên quan: các bối cảnh quen thuộc như rừng được mở rộng thành sông và núi, thành phố thành đường phố/công viên/đường chân trời; giữ điều kiện ngày đêm, mùa và ánh sáng. Không cần gọi AI thêm. Chủ đề hoặc điều kiện không nhận diện rõ chỉ dùng từ gần nghĩa. Tỷ lệ 16:9, giới hạn 15 video, tối đa 10 lượt tìm và lịch sử chống trùng vẫn giữ nguyên.
