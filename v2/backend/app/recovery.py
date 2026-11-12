"""Classify temporary failures without treating configuration errors as outages."""
import re

TEXT_JOBS = ('full','translation','seo')


def recoverable_error(error):
    value=str(error).casefold()
    branches=re.split(r'; (?=(?:translation|seo):)',value)
    if len(branches)>1:return all(recoverable_error(branch) for branch in branches)
    if any(marker in value for marker in (
        'http 400','http 401','http 403','http 404','invalid api key',
        'api key không hợp lệ','chứng chỉ ssl','certificate verify',
        'daily quota','per day','per_day','billing','insufficient_quota',
        'khóa mã hóa','fernet','đã hủy','đầu vào đã thay đổi',
    )):return False
    return any(marker in value for marker in (
        'http 502','http 503','http 504','http 429',
        'timeout','timed out','quá thời gian chờ','temporarily',
        'temporary failure','connection','kết nối','mất mạng',
        'network is unreachable','network error','name resolution',
        'could not translate host name','server closed',
    ))
