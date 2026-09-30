from django import forms
from django.core.validators import URLValidator


class SubmissionForm(forms.Form):
    request_id = forms.UUIDField()
    nickname = forms.CharField(max_length=30, required=False, strip=True)
    body = forms.CharField(min_length=5, max_length=2000, strip=True)
    consent = forms.BooleanField(required=True)


class FeedbackForm(SubmissionForm):
    # Keep accepting valid categories from older pages; new forms omit this field.
    category = forms.ChoiceField(required=False, choices=[('activity', '活动心愿'), ('suggestion', '社团建议'), ('other', '其他留言')])


class SongForm(SubmissionForm):
    body = forms.CharField(max_length=2000, required=False, strip=True)
    song_title = forms.CharField(max_length=150, strip=True)
    artist = forms.CharField(max_length=100, strip=True)
    music_url = forms.CharField(max_length=500, required=False, validators=[URLValidator(schemes=['https'])])

    def clean_music_url(self):
        from urllib.parse import urlsplit
        value = self.cleaned_data['music_url']
        parts = urlsplit(value)
        if parts.username or parts.password:
            raise forms.ValidationError('请使用不包含登录凭据的 HTTPS 试听链接。')
        return value
