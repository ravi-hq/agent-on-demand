import json

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from agent_on_demand.models import Environment
from agent_on_demand.providers import SUPPORTED_PROVIDERS
from agent_on_demand.validation.environment_validation import (
    validate_env_vars,
    validate_networking,
    validate_packages,
)


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


class AgentCreateForm(forms.Form):
    name = forms.CharField(max_length=200, label="Name")
    provider = forms.ChoiceField(
        choices=[(provider, provider.title()) for provider in SUPPORTED_PROVIDERS],
        label="Provider",
    )
    model = forms.CharField(
        max_length=100,
        label="Model",
        initial="claude-sonnet",
        widget=forms.TextInput(
            attrs={
                "placeholder": "claude-sonnet or claude-opus",
                "title": (
                    "Use the provider's model alias/name only. Do not include a provider/ prefix."
                ),
            }
        ),
    )
    environment_id = forms.CharField(
        required=False,
        label="Environment",
        widget=forms.Select(choices=[("", "No environment")]),
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    system = forms.CharField(
        required=False,
        label="System prompt",
        widget=forms.Textarea(attrs={"rows": 6}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        envs = Environment.objects.none()
        if user is not None:
            envs = Environment.objects.filter(user=user, archived_at__isnull=True).order_by("name")
        self.fields["environment_id"].widget.choices = [("", "No environment")] + [
            (str(env.id), f"{env.name} v{env.version}") for env in envs
        ]


class EnvironmentCreateForm(forms.Form):
    name = forms.CharField(max_length=200, label="Name")
    packages_json = forms.CharField(
        required=False,
        label="Packages JSON",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": '{"pip": ["pytest"], "npm": ["typescript"]}',
            }
        ),
    )
    env_vars_json = forms.CharField(
        required=False,
        label="Environment variables JSON",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": '{"ANTHROPIC_API_KEY": "..."}',
            }
        ),
    )
    setup_script = forms.CharField(
        required=False,
        label="Setup script",
        widget=forms.Textarea(attrs={"rows": 6}),
    )
    networking_type = forms.ChoiceField(
        choices=[("unrestricted", "Unrestricted"), ("limited", "Limited")],
        label="Networking",
    )
    allowed_hosts = forms.CharField(
        required=False,
        label="Allowed hosts",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "api.example.com"}),
        help_text="One host per line. Used only when networking is limited.",
    )

    def clean_packages_json(self) -> dict:
        value = _load_optional_json_object(self.cleaned_data["packages_json"])
        for _manager, packages in value.items():
            if not isinstance(packages, list) or not all(isinstance(p, str) for p in packages):
                raise forms.ValidationError("Package values must be lists of strings.")
        try:
            return validate_packages(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_env_vars_json(self) -> dict:
        value = _load_optional_json_object(self.cleaned_data["env_vars_json"])
        for key, env_value in value.items():
            if not isinstance(env_value, str):
                raise forms.ValidationError(f"Environment variable {key!r} must be a string.")
        try:
            return validate_env_vars(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean(self) -> dict:
        cleaned = super().clean()
        networking_type = cleaned.get("networking_type") or "unrestricted"
        allowed_hosts_raw = cleaned.get("allowed_hosts") or ""
        allowed_hosts = [line.strip() for line in allowed_hosts_raw.splitlines() if line.strip()]
        networking = {"type": networking_type}
        if networking_type == "limited":
            networking["allowed_hosts"] = allowed_hosts
        try:
            cleaned["networking"] = validate_networking(networking)
        except ValueError as exc:
            self.add_error("networking_type", str(exc))
        return cleaned


def _load_optional_json_object(raw: str) -> dict:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise forms.ValidationError("Enter valid JSON.") from exc
    if not isinstance(value, dict):
        raise forms.ValidationError("Enter a JSON object.")
    return value


class SessionPromptForm(forms.Form):
    prompt = forms.CharField(
        label="Prompt",
        strip=True,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    timeout = forms.IntegerField(
        min_value=10,
        max_value=3600,
        initial=600,
        label="Timeout seconds",
    )
