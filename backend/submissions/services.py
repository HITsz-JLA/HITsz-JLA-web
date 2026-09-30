import hashlib
import hmac
import json
import time
from datetime import timedelta
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
from .models import ModerationLog, RateBucket, Submission


def client_identity(request):
    address = request.META.get('REMOTE_ADDR', '')
    if settings.TRUST_LOOPBACK_PROXY and address in ('127.0.0.1', '::1'):
        # Nginx must overwrite X-Real-IP, never append a client-supplied header.
        address = request.META.get('HTTP_X_REAL_IP', address)
    return hmac.new(settings.SECRET_KEY.encode(), address.encode(), hashlib.sha256).hexdigest()


def consume_limit(identity, scope, limit, seconds):
    now = timezone.now()
    window = int(now.timestamp()) // seconds
    key = hashlib.sha256(f'{scope}:{identity}:{window}'.encode()).hexdigest()
    with transaction.atomic():
        bucket, _ = RateBucket.objects.get_or_create(
            key=key, defaults={'expires_at': now + timedelta(seconds=seconds * 2)})
        if bucket.count >= limit:
            return False
        bucket.count += 1
        bucket.save(update_fields=['count'])
    return True


def form_token():
    return signing.dumps({'issued': time.time()}, salt='community-form')


def valid_form_token(token):
    try:
        value = signing.loads(token, salt='community-form', max_age=7200)
        return time.time() - value['issued'] >= settings.FORM_MIN_SECONDS
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return False


def payload_hash(kind, values):
    public = {k: str(v) for k, v in values.items() if k not in ('request_id', 'consent')}
    return hashlib.sha256(json.dumps([kind, public], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@transaction.atomic
def moderate(submission, actor, status, public_reply=None, internal_note=None, selected=None, action='审核'):
    if not actor.has_perm('submissions.moderate_submission'):
        raise PermissionError('Missing moderation permission')
    if status not in Submission.Status.values:
        raise ValueError('Invalid moderation status')
    current = Submission.objects.select_for_update().get(pk=submission.pk)
    old_status = current.status
    current.status = status
    if public_reply is not None:
        current.public_reply = public_reply
    if internal_note is not None:
        current.internal_note = internal_note
    if selected is not None:
        current.selected = bool(selected) and current.kind == Submission.Kind.SONG and status == Submission.Status.APPROVED
    if status != Submission.Status.APPROVED:
        current.selected = False
    current.reviewed_by = actor
    current.reviewed_at = timezone.now()
    current.save()
    ModerationLog.objects.create(submission=current, actor=actor, old_status=old_status, new_status=status, action=action)
    return current
