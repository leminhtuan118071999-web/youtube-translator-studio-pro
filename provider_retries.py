"""Bounded retries for temporary upstream responses in direct UI actions."""
import math
from time import sleep as _sleep

from api_clients import TransientProviderError


def retry_transient_provider(operation, *, report=None, wait=None, max_retries=3):
    """Retry only the failed request; leave completed chunks and caller data alone.

    Do not retry authentication, invalid models, quota exhaustion or read
    timeouts here. A gateway failure may hide a completed billable request,
    so bound duplicate POSTs to three retries, as in the full-job worker.
    """
    if type(max_retries) is not int or not 0 <= max_retries <= 3:
        raise ValueError("Số lần thử lại phải từ 0 đến 3.")
    pause = wait if wait is not None else _sleep
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except TransientProviderError as exc:
            if exc.status_code not in (502, 503, 504):
                raise
            if attempt == max_retries:
                raise TransientProviderError(
                    f"Dịch vụ AI vẫn lỗi HTTP {exc.status_code} sau {max_retries} lần thử lại. "
                    "Kết quả đã lưu được giữ nguyên. Hãy thử lại sau hoặc đổi "
                    "nhà cung cấp/gateway trong Cấu hình API.",
                    status_code=exc.status_code, retry_after=exc.retry_after,
                ) from exc
            delay = 3.0 * (2 ** attempt)
            if exc.retry_after is not None:
                try:
                    stated = float(exc.retry_after)
                    if math.isfinite(stated) and stated >= 0:
                        delay = stated
                except (ValueError, TypeError):
                    pass
            delay = min(180.0, max(1.0, delay))
            if report:
                report(
                    f"⏳ API tạm lỗi HTTP {exc.status_code}. "
                    f"Tự thử lại {attempt + 1}/{max_retries} sau {int(math.ceil(delay))} giây…"
                )
            pause(delay)
