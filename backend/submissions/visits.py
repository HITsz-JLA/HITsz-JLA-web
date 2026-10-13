"""Private page-view records; no public count or visitor-list endpoint."""
import ipaddress
import json
import uuid
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.db import OperationalError
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import PageVisit
from .services import client_identity, consume_limit


@csrf_exempt
@require_POST
@never_cache
def record_visit(request):
    # Cookie-free telemetry: require the exact same origin AND a custom header.
    # A cross-origin form cannot supply these; CORS is intentionally not enabled.
    origin = f'{request.scheme}://{request.get_host()}'
    if request.headers.get('Origin') != origin or request.headers.get('X-JLA-Visit') != '1':
        return HttpResponse(status=403)
    if request.content_type != 'application/json' or len(request.body) > 2048:
        return HttpResponse(status=400)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not isinstance(data.get('path'), str):
            raise ValueError()
        path = unquote(data['path'], errors='strict')
        parts = urlsplit(path)
        if (not path.startswith('/') or path.startswith('//') or '\\' in path
                or parts.query or parts.fragment or '?' in path or '#' in path
                or len(path) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in path)
                or any(p in ('.', '..') for p in path.split('/'))
                or path == '/community' or path.startswith('/community/')):
            raise ValueError()
        event_id = uuid.UUID(str(data.get('event_id', '')))
        address = request.META.get('REMOTE_ADDR', '')
        if settings.TRUST_LOOPBACK_PROXY and address in ('127.0.0.1', '::1'):
            address = request.META.get('HTTP_X_REAL_IP', address)
        address = str(ipaddress.ip_address(address))
    except (ValueError, TypeError, UnicodeError):
        return HttpResponse(status=400)
    try:
        if not consume_limit(client_identity(request), 'page-visit', 120, 60):
            response = HttpResponse(status=429)
            response['Retry-After'] = '60'
            return response
        PageVisit.objects.get_or_create(event_id=event_id, defaults={'path': path, 'ip_address': address})
    except OperationalError:
        return HttpResponse(status=503)
    return HttpResponse(status=204)
