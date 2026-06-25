from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username",)


class APIKeyCreateForm(forms.Form):
    name = forms.CharField(max_length=100, label="Label")
    expires_at = forms.DateTimeField(
        required=False,
        label="Expires at (optional)",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
