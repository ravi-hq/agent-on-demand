from django.db import migrations, models


KNOWN_PREFIXES = {"anthropic", "openai", "google", "kimi"}
RUNTIME_PROVIDER = {
    "claude": "anthropic",
    "codex": "openai",
    "gemini": "google",
}
PROVIDER_RUNTIME = {provider: runtime for runtime, provider in RUNTIME_PROVIDER.items()}


def _provider_and_model(model: str, runtime: str) -> tuple[str, str]:
    model = (model or "").strip()
    runtime = (runtime or "").strip()
    prefix, sep, suffix = model.partition("/")
    if sep and prefix in KNOWN_PREFIXES:
        return prefix, suffix.strip()
    return RUNTIME_PROVIDER.get(runtime, "anthropic"), model


def forwards(apps, schema_editor):
    Agent = apps.get_model("fairy", "Agent")
    AgentVersion = apps.get_model("fairy", "AgentVersion")
    for obj in Agent.objects.all():
        provider, model = _provider_and_model(obj.model, obj.runtime)
        obj.provider = provider
        obj.model = model
        obj.save(update_fields=["provider", "model"])
    for obj in AgentVersion.objects.all():
        provider, model = _provider_and_model(obj.model, obj.runtime)
        obj.provider = provider
        obj.model = model
        obj.save(update_fields=["provider", "model"])


def backwards(apps, schema_editor):
    Agent = apps.get_model("fairy", "Agent")
    AgentVersion = apps.get_model("fairy", "AgentVersion")
    for obj in Agent.objects.all():
        obj.runtime = PROVIDER_RUNTIME.get(obj.provider, "claude")
        obj.model = f"{obj.provider}/{obj.model}" if "/" not in obj.model else obj.model
        obj.save(update_fields=["runtime", "model"])
    for obj in AgentVersion.objects.all():
        obj.runtime = PROVIDER_RUNTIME.get(obj.provider, "claude")
        obj.model = f"{obj.provider}/{obj.model}" if "/" not in obj.model else obj.model
        obj.save(update_fields=["runtime", "model"])


class Migration(migrations.Migration):
    dependencies = [
        ("fairy", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="agent",
            name="provider",
            field=models.CharField(default="anthropic", max_length=32),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="agentversion",
            name="provider",
            field=models.CharField(default="anthropic", max_length=32),
            preserve_default=False,
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="agent", name="runtime"),
        migrations.RemoveField(model_name="agentversion", name="runtime"),
    ]
