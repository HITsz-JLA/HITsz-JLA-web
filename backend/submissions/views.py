import json
from django.conf import settings
from django.core.paginator import Paginator
from django.db import IntegrityError, OperationalError, connection, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .forms import FeedbackForm, SongForm
from .models import Notification, Submission
from .services import client_identity, consume_limit, form_token, payload_hash, valid_form_token


def failure(message, status=400, **extra):
    return JsonResponse({'ok': False, 'message': message, **extra}, status=status)


def csrf_failure(request, reason=''):
    return failure('表单已过期，请刷新页面后重试。', 403)


@require_GET
@never_cache
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({'csrf_token': get_token(request), 'form_token': form_token()})


@require_GET
@never_cache
def health(request):
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'ok': True, 'service': 'jla-community', 'api_version': 1})


@require_POST
@never_cache
def submit(request, kind):
    if kind not in ('feedback', 'song'):
        return failure('不存在的投稿类型。', 404)
    if request.content_type != 'application/json':
        return failure('请使用网页表单提交。', 415)
    if len(request.body) > 12 * 1024:
        return failure('内容过长。', 413)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return failure('表单格式有误。')
    if not isinstance(data, dict):
        return failure('表单格式有误。')
    if data.get('website') or not valid_form_token(data.get('form_token', '')):
        return failure('提交过快或表单已过期，请稍候刷新后重试。')
    form = (FeedbackForm if kind == 'feedback' else SongForm)(data)
    if not form.is_valid():
        return failure('请检查表单中的内容。', errors=form.errors.get_json_data())
    values = form.cleaned_data
    fingerprint = payload_hash(kind, values)
    try:
        with transaction.atomic():
            previous = Submission.objects.filter(request_id=values['request_id']).first()
            if previous:
                if previous.payload_hash != fingerprint:
                    return failure('这次提交编号已经使用，请刷新后重新提交。', 409)
                return JsonResponse({'ok': True, 'message': '已收到，请等待审核。', 'reference': str(previous.pk)}, status=200)
            if not consume_limit(client_identity(request), 'submit', settings.SUBMISSION_RATE_LIMIT, settings.SUBMISSION_RATE_SECONDS):
                response = failure('提交比较频繁，请十分钟后再试。', 429)
                response['Retry-After'] = str(settings.SUBMISSION_RATE_SECONDS)
                return response
            fields = {k: v for k, v in values.items() if k != 'consent'}
            submission = Submission.objects.create(kind=kind, status=Submission.Status.PENDING,
                                                   payload_hash=fingerprint, **fields)
            Notification.objects.create(submission=submission, next_attempt_at=timezone.now())
    except (IntegrityError, OperationalError):
        return failure('服务正忙，请稍后重试；请保留当前页面。', 503)
    return JsonResponse({'ok': True, 'message': '已收到，请等待审核。', 'reference': str(submission.pk)}, status=201)


@require_GET
@never_cache
def feedback_list(request):
    items = Submission.objects.filter(kind=Submission.Kind.FEEDBACK, status=Submission.Status.APPROVED)
    category = request.GET.get('category', '')
    if category in ('activity', 'suggestion', 'other'):
        items = items.filter(category=category)
    page = Paginator(items.order_by('-created_at'), 10).get_page(request.GET.get('page', 1))
    return JsonResponse({'items': [{
        'id': str(s.pk), 'nickname': s.nickname or '匿名社员', 'body': s.body,
        'category': s.get_category_display(), 'reply': s.public_reply,
        'date': timezone.localtime(s.created_at).strftime('%Y-%m-%d'),
    } for s in page], 'page': page.number, 'pages': page.paginator.num_pages,
        'total': page.paginator.count, 'has_next': page.has_next()})
