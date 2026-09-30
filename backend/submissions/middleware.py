from django.conf import settings
from django.db import OperationalError
from django.http import HttpResponse
from .services import client_identity, consume_limit


class LoginThrottleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path == '/community/admin/login/':
            try:
                allowed = consume_limit(client_identity(request), 'login', settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_SECONDS)
            except OperationalError:
                return HttpResponse('服务繁忙，请稍后重试。', status=503)
            if not allowed:
                return HttpResponse('登录尝试过多，请十五分钟后重试。', status=429)
        return self.get_response(request)
