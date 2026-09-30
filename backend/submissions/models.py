import uuid
from django.conf import settings
from django.db import models


class Submission(models.Model):
    class Kind(models.TextChoices):
        FEEDBACK = 'feedback', '匿名留言'
        SONG = 'song', '每周一曲投稿'

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已通过'
        REJECTED = 'rejected', '已拒绝'
        HIDDEN = 'hidden', '已下架'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(unique=True, editable=False)
    payload_hash = models.CharField(max_length=64, editable=False)
    kind = models.CharField('类型', max_length=12, choices=Kind.choices)
    status = models.CharField('审核状态', max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    category = models.CharField('留言分类', max_length=16, blank=True,
                                choices=[('activity', '活动心愿'), ('suggestion', '社团建议'), ('other', '其他留言')])
    nickname = models.CharField('自愿署名', max_length=30, blank=True)
    body = models.TextField('留言 / 推荐理由', max_length=2000)
    song_title = models.CharField('歌曲名称', max_length=150, blank=True)
    artist = models.CharField('歌手 / 演奏者', max_length=100, blank=True)
    music_url = models.URLField('试听链接', max_length=500, blank=True)
    selected = models.BooleanField('已选为每周一曲', default=False)
    public_reply = models.TextField('公开回复', max_length=2000, blank=True)
    internal_note = models.TextField('内部备注（不公开）', max_length=4000, blank=True)
    created_at = models.DateTimeField('提交时间', auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField('审核时间', null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='审核人', null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='reviewed_submissions')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '投稿'
        verbose_name_plural = '留言与歌曲投稿'
        permissions = [('moderate_submission', '可以审核、回复和下架投稿')]
        indexes = [models.Index(fields=['kind', 'status', '-created_at'])]

    def __str__(self):
        return f'{self.get_kind_display()} · {self.song_title or self.body[:35]}'


class Notification(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE, verbose_name='投稿')
    status = models.CharField('通知状态', max_length=12, default='pending',
                             choices=[('pending', '待发送'), ('sending', '发送中'), ('sent', '已发送'), ('failed', '发送失败')])
    attempts = models.PositiveIntegerField('尝试次数', default=0)
    next_attempt_at = models.DateTimeField('下次尝试时间', db_index=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField('发送时间', null=True, blank=True)
    last_error = models.CharField('错误类型', max_length=120, blank=True)
    delivery_mode = models.CharField('发送方式', max_length=12, blank=True)

    class Meta:
        verbose_name = '邮件通知'
        verbose_name_plural = '邮件通知'


class ModerationLog(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, verbose_name='投稿')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name='管理员')
    old_status = models.CharField('原状态', max_length=12)
    new_status = models.CharField('新状态', max_length=12)
    action = models.CharField('操作', max_length=60)
    created_at = models.DateTimeField('操作时间', auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = '审核记录'
        verbose_name_plural = '审核记录'


class RateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
