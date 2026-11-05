# LMT Review Studio — bản đầu
Ứng dụng riêng chạy tại http://localhost:8504, không thay đổi V2/V3.

## Chạy trên Mac
```sh
git clone --branch v4/review-studio https://github.com/leminhtuan118071999-web/youtube-translator-studio-pro.git ~/lmt-review-studio
cd ~/lmt-review-studio
python3 review_app/start_review.py
```
Launcher tự tạo môi trường Python riêng. Dựng video cần FFmpeg có trong PATH.
Nhập URL API tương thích OpenAI, Model ID và khóa của bạn. Khóa chỉ ở phiên Streamlit.

## Có trong bản đầu
- Dán toàn bộ kịch bản hoặc lấy phụ đề YouTube khi truy cập được.
- Phân tích từng phần bao phủ toàn nguồn, lập dàn ý, viết 6 phần review và kiểm tra nội dung bằng AI.
- Ngôn ngữ đích và thời lượng mong muốn. Thời lượng chưa được đo bằng file giọng đọc.
- Lưu nguồn, báo cáo nguồn, checkpoint và TXT theo dự án riêng tại ~/.lmt-review-studio.
- Ghép video gốc với file giọng đọc dựa trên SRT nguồn và SRT giọng đọc. Xuất MP4 720p và scene-map.json để kiểm tra cảnh đã chọn.

## Giới hạn hiện tại
Chưa phân tích hình ảnh, tự tạo giọng đọc, tự tạo SRT, chạy nền hoặc tự khôi phục sau khi tắt máy. Cần giữ ứng dụng chạy. Checkpoint giữ các phần đã xử lý để phục vụ bổ sung chức năng tiếp tục, chưa có nút tiếp tục trong giao diện. Kiểm tra AI không bảo đảm tuyệt đối chính xác. Nếu không chọn được cảnh sẽ dừng và báo lỗi, không đoán cảnh. Với cảnh ngắn hơn câu đọc, giữ khung hình cuối. Cần nghe và xem lại trước khi xuất bản. Nguồn YouTube thiếu phụ đề cần dán kịch bản; chưa tải video từ link. Video gốc cần file có sẵn trên máy.

## Kiểm tra
```sh
python3 -m unittest review_app.test_engine
```
