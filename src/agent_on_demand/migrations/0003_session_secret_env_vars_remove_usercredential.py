import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fairy", "0002_provider_based_agents"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionSecretEnvVars",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("encrypted_env_vars", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_env_vars",
                        to="fairy.agentsession",
                    ),
                ),
            ],
            options={
                "db_table": "session_secret_env_vars",
            },
        ),
        migrations.DeleteModel(
            name="UserCredential",
        ),
    ]
