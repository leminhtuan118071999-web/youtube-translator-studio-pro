from app.recovery import recoverable_error
import pytest


@pytest.mark.parametrize('error',[
    'translation: Nhà cung cấp AI phản hồi quá thời gian chờ (300 giây).',
    'translation: API trả về thành công nhưng không có nội dung văn bản (OpenAI / gpt-6.1-sol, finish_reason=stop).',
    'Kết nối tới nhà cung cấp AI bị lỗi hoặc bị ngắt.',
    'HTTP 503: Service temporarily unavailable',
    'Temporary failure in name resolution',
    'translation: HTTP 502; seo: HTTP 504',
])
def test_outages_are_recoverable(error):assert recoverable_error(error)


@pytest.mark.parametrize('error',[
    'HTTP 401: API key không hợp lệ.',
    'HTTP 403: Tài khoản chưa có quyền.',
    'HTTP 404: model not found',
    'Kết nối HTTPS lỗi chứng chỉ SSL.',
    'translation: HTTP 503; seo: Thiếu tiêu đề hoặc mô tả.',
    'HTTP 429: daily quota exceeded',
    'Đã hủy',
])
def test_user_action_and_configuration_failures_are_not_retried(error):assert not recoverable_error(error)
