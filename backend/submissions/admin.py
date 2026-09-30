import html
import io
import json
import re
import zipfile
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from .models import ModerationLog, Notification, Submission
from .services import moderate


def escape_markdown(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|>\-])', r'\\\1', html.escape(value))


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['brief', 'kind', 'status', 'selected', 'created_at', 'reviewed_by']
    list_filter = ['status', 'kind', 'category', 'selected', 'created_at']
    search_fields = ['body', 'song_title', 'artist', 'nickname']
    date_hierarchy = 'created_at'
    readonly_fields = ['id', 'kind', 'category', 'nickname', 'body', 'song_title', 'artist', 'music_url',
                       'created_at', 'reviewed_by', 'reviewed_at']
    fields = ['id', 'kind', 'category', 'nickname', 'created_at', 'body', 'song_title', 'artist',
              'music_url', 'status', 'selected', 'public_reply', 'internal_note', 'reviewed_by', 'reviewed_at']
    actions = ['approve', 'reject', 'hide', 'export_songs']
    list_per_page = 30

    @admin.display(description='投稿内容')
    def brief(self, obj):
        return obj.song_title or obj.body[:45]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and request.user.has_perm('submissions.moderate_submission')

    def save_model(self, request, obj, form, change):
        moderate(obj, request.user, obj.status, obj.public_reply, obj.internal_note, obj.selected, '审核 / 更新回复')

    def transition(self, request, queryset, status):
        count = 0
        for item in queryset:
            moderate(item, request.user, status)
            count += 1
        self.message_user(request, f'已处理 {count} 条投稿。', messages.SUCCESS)

    @admin.action(description='审核通过所选投稿', permissions=['change'])
    def approve(self, request, queryset):
        self.transition(request, queryset, Submission.Status.APPROVED)

    @admin.action(description='拒绝所选投稿', permissions=['change'])
    def reject(self, request, queryset):
        self.transition(request, queryset, Submission.Status.REJECTED)

    @admin.action(description='下架所选投稿', permissions=['change'])
    def hide(self, request, queryset):
        self.transition(request, queryset, Submission.Status.HIDDEN)

    @admin.action(description='导出已通过歌曲的 Markdown 草稿', permissions=['change'])
    def export_songs(self, request, queryset):
        items = queryset.filter(kind=Submission.Kind.SONG, status=Submission.Status.APPROVED)
        if not items.exists():
            self.message_user(request, '请选择至少一条已通过审核的歌曲投稿。', messages.WARNING)
            return
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                title = json.dumps(f'{item.song_title} — {item.artist}', ensure_ascii=False)
                text = (f'---\ntitle: {title}\ndate: {timezone.localdate().isoformat()}\ndraft: true\n'
                        f'type: lyrics\nsubmission_id: "{item.pk}"\n---\n\n'
                        f'{escape_markdown(item.body)}\n\n<!--more-->\n\n'
                        f'试听链接：{escape_markdown(item.music_url)}\n\n'
                        f'推荐人：{escape_markdown(item.nickname or "匿名社员")}\n\n'
                        '编辑说明：请补充封面、歌曲介绍等正式内容，预览确认后将 draft 改为 false。\n')
                archive.writestr(f'song-{item.pk}.md', text)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="weekly-song-drafts.zip"'
        response['Cache-Control'] = 'no-store'
        return response


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['submission', 'status', 'delivery_mode', 'attempts', 'sent_at', 'last_error']
    list_filter = ['status', 'delivery_mode']
    readonly_fields = ['submission', 'status', 'attempts', 'next_attempt_at', 'sent_at', 'last_error', 'delivery_mode']
    fields = readonly_fields
    actions = ['retry_failed']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description='重新排队失败的通知（不会重发已发送邮件）', permissions=['change'])
    def retry_failed(self, request, queryset):
        count = queryset.filter(status='failed').update(status='pending', attempts=0,
                                                       next_attempt_at=timezone.now(), last_error='')
        self.message_user(request, f'{count} 条失败通知已重新排队。')


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ['submission', 'actor', 'old_status', 'new_status', 'action', 'created_at']
    list_filter = ['new_status', 'actor']
    readonly_fields = ['submission', 'actor', 'old_status', 'new_status', 'action', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
