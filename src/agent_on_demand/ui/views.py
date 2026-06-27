import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from agent_on_demand import session_service
from agent_on_demand.analytics import capture as posthog_capture
from agent_on_demand.models import (
    Agent,
    AgentVersion,
    AgentSession,
    AgentSessionLog,
    APIKey,
    Environment,
    EnvironmentVersion,
    SessionTurn,
    UserQuota,
)
from agent_on_demand.models.auth import CREDENTIAL_ENV_VAR, UserCredential
from agent_on_demand.models_catalog import MODELS
from agent_on_demand.runtimes import RUNTIMES
from agent_on_demand.session_service.tracing import inject_carrier
from agent_on_demand.session_state import check_can_accept_prompt, check_can_terminate
from agent_on_demand.ui.forms import (
    AgentCreateForm,
    APIKeyCreateForm,
    EnvironmentCreateForm,
    RegisterForm,
    SessionPromptForm,
)
from agent_on_demand.validation.runtime_model_compat import check_runtime_model_compat


def landing(request):
    return render(request, "ui/landing.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("ui-dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()

            _, raw_key = APIKey.create_key(user=user, name="Onboarding key")

            login(request, user)
            request.session["onboarding_raw_key"] = raw_key

            posthog_capture(user, "user.registered")

            return redirect("ui-welcome")
    else:
        form = RegisterForm()

    return render(request, "ui/register.html", {"form": form})


@login_required(login_url="/ui/login")
def welcome(request):
    raw_key = request.session.pop("onboarding_raw_key", None)
    if not raw_key:
        return redirect("ui-dashboard")

    api_base = request.build_absolute_uri("/").rstrip("/")
    return render(
        request,
        "ui/welcome.html",
        {"raw_key": raw_key, "api_base": api_base},
    )


@login_required(login_url="/ui/login")
def dashboard(request):
    counts = {
        "agents": Agent.objects.filter(user=request.user, archived_at__isnull=True).count(),
        "environments": Environment.objects.filter(
            user=request.user, archived_at__isnull=True
        ).count(),
        "sessions": AgentSession.objects.filter(user=request.user).count(),
        "api_keys": APIKey.objects.filter(user=request.user, is_active=True).count(),
    }
    return render(request, "ui/dashboard.html", {"counts": counts})


@login_required(login_url="/ui/login")
def api_keys(request):
    new_raw_key = None
    if request.method == "POST":
        form = APIKeyCreateForm(request.POST)
        if form.is_valid():
            _, new_raw_key = APIKey.create_key(
                user=request.user,
                name=form.cleaned_data["name"],
                expires_at=form.cleaned_data["expires_at"],
            )
            messages.success(request, "API key created — copy it now, it won't be shown again.")
            form = APIKeyCreateForm()
    else:
        form = APIKeyCreateForm()

    keys = APIKey.objects.filter(user=request.user).order_by("-created_at")
    return render(
        request,
        "ui/api_keys.html",
        {"form": form, "keys": keys, "new_raw_key": new_raw_key},
    )


@require_POST
@login_required(login_url="/ui/login")
def api_key_revoke(request, key_id):
    try:
        key = APIKey.objects.get(pk=key_id, user=request.user)
    except APIKey.DoesNotExist as exc:
        raise Http404("API key not found") from exc
    key.is_active = False
    key.save(update_fields=["is_active"])
    messages.success(request, f"Revoked {key.key_prefix}…")
    return redirect("ui-api-keys")


@require_GET
@login_required(login_url="/ui/login")
def agents_list(request):
    agents = Agent.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "ui/agents_list.html", {"agents": agents})


@login_required(login_url="/ui/login")
@require_http_methods(["GET", "POST"])
def agent_new(request):
    if request.method == "POST":
        form = AgentCreateForm(request.POST, user=request.user)
        if form.is_valid():
            agent = _create_agent_from_form(request, form)
            if agent is not None:
                messages.success(request, "Agent created.")
                return redirect("ui-agent-detail", agent_id=agent.id)
    else:
        form = AgentCreateForm(user=request.user)

    return render(request, "ui/agent_form.html", {"form": form})


@login_required(login_url="/ui/login")
def agent_detail(request, agent_id):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    return render(
        request,
        "ui/agent_detail.html",
        {"agent": agent, "start_form": SessionPromptForm()},
    )


@require_POST
@login_required(login_url="/ui/login")
def agent_start_session(request, agent_id):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    form = SessionPromptForm(request.POST)
    if not form.is_valid():
        messages.error(request, _first_form_error(form))
        return redirect("ui-agent-detail", agent_id=agent.id)

    err = _validate_agent_can_start_session(agent, request.user)
    if err:
        messages.error(request, err)
        return redirect("ui-agent-detail", agent_id=agent.id)

    environment = agent.environment
    prompt = form.cleaned_data["prompt"]
    timeout = float(form.cleaned_data["timeout"])
    effective_prompt = f"{agent.system}\n\n{prompt}" if agent.system else prompt

    name = f"{settings.SPRITE_NAME_PREFIX}-{uuid.uuid4().hex[:12]}"
    runtime_session_id = str(uuid.uuid4())

    with transaction.atomic():
        locked_quota, _ = UserQuota.objects.get_or_create(user=request.user)
        locked_quota = UserQuota.objects.select_for_update().get(pk=locked_quota.pk)
        locked_max = (
            locked_quota.max_concurrent_sessions or settings.DEFAULT_MAX_CONCURRENT_SESSIONS
        )
        locked_count = UserQuota.active_session_count_for(request.user)
        if locked_count >= locked_max:
            messages.error(
                request,
                (
                    f"Concurrent session limit reached ({locked_count}/{locked_max}). "
                    "Terminate an active session before starting a new one."
                ),
            )
            return redirect("ui-agent-detail", agent_id=agent.id)

        session = AgentSession.objects.create(
            user=request.user,
            agent=agent,
            environment=environment,
            runtime=agent.runtime,
            prompt=prompt,
            backend_handle=name,
            runtime_session_id=runtime_session_id,
            status="pending",
        )
        turn = SessionTurn.objects.create(
            session=session,
            turn_number=1,
            prompt=prompt,
            status="pending",
        )
        transaction.on_commit(
            lambda session_id=str(session.id), turn_id=turn.id: (
                session_service.provision_session_task.defer(
                    session_id=session_id,
                    turn_id=turn_id,
                    prompt=effective_prompt,
                    mode="run",
                    timeout=timeout,
                    _otel_carrier=inject_carrier(),
                )
            )
        )

    posthog_capture(
        request.user,
        "session.created",
        properties={
            "session_id": str(session.id),
            "agent_id": str(agent.id),
            "environment_id": str(environment.id) if environment else None,
            "runtime": agent.runtime,
            "model": agent.model,
            "prompt_length": len(prompt),
            "repo_count": 0,
            "mcp_server_count": len(agent.mcp_servers or []),
            "skill_count": len(agent.skills or []),
            "env_var_count": len((environment.env_vars or {})) if environment else 0,
            "timeout": timeout,
            "source": "dashboard",
        },
    )

    messages.success(request, "Session started.")
    return redirect("ui-session-detail", session_id=session.id)


@require_POST
@login_required(login_url="/ui/login")
def agent_archive(request, agent_id):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    if agent.is_archived:
        messages.warning(request, "Agent is already archived.")
        return redirect("ui-agent-detail", agent_id=agent.id)

    agent.archived_at = timezone.now()
    agent.save(update_fields=["archived_at", "updated_at"])
    posthog_capture(request.user, "agent.archived", properties={"agent_id": str(agent.id)})
    messages.success(request, "Agent archived.")
    return redirect("ui-agent-detail", agent_id=agent.id)


def _create_agent_from_form(request, form: AgentCreateForm) -> Agent | None:
    model = form.cleaned_data["model"]
    runtime = form.cleaned_data["runtime"]
    environment_id = form.cleaned_data["environment_id"].strip()

    if runtime not in RUNTIMES:
        form.add_error("runtime", f"Unknown runtime: {runtime}.")
        return None
    if model not in MODELS:
        form.add_error("model", f"Unknown model: {model}.")
        return None

    compat_err = check_runtime_model_compat(RUNTIMES[runtime], MODELS[model])
    if compat_err is not None:
        form.add_error("model", compat_err)
        return None

    environment = None
    if environment_id:
        try:
            environment = Environment.objects.get(
                pk=environment_id,
                user=request.user,
                archived_at__isnull=True,
            )
        except (Environment.DoesNotExist, ValueError):
            form.add_error("environment_id", "Environment not found")
            return None

    with transaction.atomic():
        agent = Agent.objects.create(
            user=request.user,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
            system=form.cleaned_data["system"],
            model=model,
            runtime=runtime,
            environment=environment,
            version=1,
        )
        AgentVersion.objects.create(
            agent=agent,
            version=agent.version,
            name=agent.name,
            description=agent.description,
            system=agent.system,
            model=agent.model,
            runtime=agent.runtime,
            environment=agent.environment,
            skills=agent.skills,
            mcp_servers=agent.mcp_servers,
            metadata=agent.metadata,
        )

    posthog_capture(
        request.user,
        "agent.created",
        properties={
            "agent_id": str(agent.id),
            "runtime": agent.runtime,
            "model": agent.model,
            "has_environment": agent.environment_id is not None,
            "system_length": len(agent.system or ""),
            "description_length": len(agent.description or ""),
            "skill_count": 0,
            "mcp_server_count": 0,
            "metadata_key_count": 0,
            "source": "dashboard",
        },
    )
    return agent


def _create_environment_from_form(request, form: EnvironmentCreateForm) -> Environment | None:
    try:
        with transaction.atomic():
            env = Environment.objects.create(
                user=request.user,
                name=form.cleaned_data["name"],
                packages=form.cleaned_data["packages_json"],
                env_vars=form.cleaned_data["env_vars_json"],
                setup_script=form.cleaned_data["setup_script"],
                networking_type=form.cleaned_data["networking"].get("type", "unrestricted"),
                networking_config={
                    k: v for k, v in form.cleaned_data["networking"].items() if k != "type"
                },
                version=1,
            )
            EnvironmentVersion.objects.create(
                environment=env,
                version=env.version,
                name=env.name,
                packages=env.packages,
                env_vars=env.env_vars,
                setup_script=env.setup_script,
                networking_type=env.networking_type,
                networking_config=env.networking_config,
            )
    except IntegrityError:
        form.add_error("name", f"An active environment named {form.cleaned_data['name']!r} exists.")
        return None

    posthog_capture(
        request.user,
        "environment.created",
        properties={
            "environment_id": str(env.id),
            "package_count": sum(len(pkgs) for pkgs in (env.packages or {}).values()),
            "package_managers": sorted((env.packages or {}).keys()),
            "env_var_count": len(env.env_vars or {}),
            "has_setup_script": bool((env.setup_script or "").strip()),
            "setup_script_length": len(env.setup_script or ""),
            "networking_type": env.networking_type,
            "allowed_hosts_count": len((env.networking_config or {}).get("allowed_hosts", [])),
            "source": "dashboard",
        },
    )
    return env


@require_GET
@login_required(login_url="/ui/login")
def environments_list(request):
    envs = Environment.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "ui/environments_list.html", {"envs": envs})


@login_required(login_url="/ui/login")
@require_http_methods(["GET", "POST"])
def environment_new(request):
    if request.method == "POST":
        form = EnvironmentCreateForm(request.POST)
        if form.is_valid():
            env = _create_environment_from_form(request, form)
            if env is not None:
                messages.success(request, "Environment created.")
                return redirect("ui-environment-detail", environment_id=env.id)
    else:
        form = EnvironmentCreateForm()

    return render(request, "ui/environment_form.html", {"form": form})


@login_required(login_url="/ui/login")
def environment_detail(request, environment_id):
    env = get_object_or_404(Environment, pk=environment_id, user=request.user)
    return render(request, "ui/environment_detail.html", {"env": env})


@require_POST
@login_required(login_url="/ui/login")
def environment_archive(request, environment_id):
    env = get_object_or_404(Environment, pk=environment_id, user=request.user)
    if env.is_archived:
        messages.warning(request, "Environment is already archived.")
        return redirect("ui-environment-detail", environment_id=env.id)

    env.archived_at = timezone.now()
    env.save(update_fields=["archived_at", "updated_at"])
    posthog_capture(
        request.user,
        "environment.archived",
        properties={"environment_id": str(env.id)},
    )
    messages.success(request, "Environment archived.")
    return redirect("ui-environment-detail", environment_id=env.id)


@login_required(login_url="/ui/login")
def sessions_list(request):
    sessions = (
        AgentSession.objects.filter(user=request.user)
        .select_related("agent", "environment")
        .order_by("-created_at")
    )
    return render(request, "ui/sessions_list.html", {"sessions": sessions})


@login_required(login_url="/ui/login")
def session_detail(request, session_id):
    session = get_object_or_404(
        AgentSession.objects.select_related("agent", "environment"),
        pk=session_id,
        user=request.user,
    )
    logs = AgentSessionLog.objects.filter(session=session).order_by("id")
    return render(
        request,
        "ui/session_detail.html",
        {
            "session": session,
            "logs": logs,
            "resources": session.resources.all(),
            "prompt_form": SessionPromptForm(),
        },
    )


@require_POST
@login_required(login_url="/ui/login")
def session_send_prompt(request, session_id):
    session = get_object_or_404(AgentSession, pk=session_id, user=request.user)
    form = SessionPromptForm(request.POST)
    if not form.is_valid():
        messages.error(request, _first_form_error(form))
        return redirect("ui-session-detail", session_id=session.id)

    err = check_can_accept_prompt(session.status)
    if err is not None:
        messages.error(request, _detail_from_json_response(err))
        return redirect("ui-session-detail", session_id=session.id)

    try:
        session_service.resume_session(session.backend_handle)
    except session_service.NoBackendCredentialsError as e:
        messages.error(request, str(e))
        return redirect("ui-session-detail", session_id=session.id)
    except session_service.SessionHandleNotFound:
        messages.error(request, "Session backend is no longer available; start a new session.")
        return redirect("ui-session-detail", session_id=session.id)

    prompt = form.cleaned_data["prompt"]
    timeout = float(form.cleaned_data["timeout"])

    try:
        with transaction.atomic():
            locked = AgentSession.objects.select_for_update().get(
                pk=session.id,
                user=request.user,
            )
            err = check_can_accept_prompt(locked.status)
            if err is not None:
                messages.error(request, _detail_from_json_response(err))
                return redirect("ui-session-detail", session_id=locked.id)
            if locked.status == "pending":
                messages.error(request, "Session already has a pending turn.")
                return redirect("ui-session-detail", session_id=locked.id)

            next_turn_number = (
                SessionTurn.objects.filter(session=locked).aggregate(n=Max("turn_number"))["n"]
                or 0
            ) + 1
            turn = SessionTurn.objects.create(
                session=locked,
                turn_number=next_turn_number,
                prompt=prompt,
                status="pending",
            )
            locked.prompt = prompt
            locked.status = "pending"
            locked.exit_code = None
            locked.save(update_fields=["prompt", "status", "exit_code", "updated_at"])
            session_service.run_turn(locked, turn, prompt, "continue", timeout)
            session = locked
    except AgentSession.DoesNotExist as exc:
        raise Http404("Session not found") from exc

    posthog_capture(
        request.user,
        "session.prompt_sent",
        properties={
            "session_id": str(session.id),
            "turn_number": turn.turn_number,
            "prompt_length": len(prompt),
            "timeout": timeout,
            "source": "dashboard",
        },
    )
    messages.success(request, "Follow-up sent.")
    return redirect("ui-session-detail", session_id=session.id)


@require_POST
@login_required(login_url="/ui/login")
def session_terminate(request, session_id):
    try:
        with transaction.atomic():
            session = AgentSession.objects.select_for_update().get(
                pk=session_id,
                user=request.user,
            )
            err = check_can_terminate(session.status)
            if err is not None:
                messages.error(request, _detail_from_json_response(err))
                return redirect("ui-session-detail", session_id=session.id)
            handle = session.backend_handle
            session.status = "terminated"
            session.backend_handle = ""
            session.save(update_fields=["status", "backend_handle", "updated_at"])
    except AgentSession.DoesNotExist as exc:
        raise Http404("Session not found") from exc

    if handle:
        session_service.destroy_session_task.defer(
            handle=handle,
            _otel_carrier=inject_carrier(),
        )

    posthog_capture(
        request.user,
        "session.terminated",
        properties={"session_id": str(session.id), "source": "dashboard"},
    )
    messages.success(request, "Session terminated.")
    return redirect("ui-session-detail", session_id=session.id)


def _validate_agent_can_start_session(agent: Agent, user) -> str | None:
    if agent.is_archived:
        return "Cannot create session with archived agent."
    if agent.environment and agent.environment.is_archived:
        return "Cannot create session with archived environment."
    if agent.runtime not in RUNTIMES:
        return f"Unknown runtime: {agent.runtime}. Must be one of: {list(RUNTIMES)}"

    runtime_obj = RUNTIMES[agent.runtime]
    accepted_kinds = {f"provider:{p}" for p in runtime_obj.providers}
    accepted_kinds |= {
        kind for kind in CREDENTIAL_ENV_VAR if kind.startswith(f"runtime_token:{agent.runtime}")
    }
    if not UserCredential.objects.filter(user=user, kind__in=accepted_kinds).exists():
        return f"No API key configured for runtime: {agent.runtime}"

    if agent.model not in MODELS:
        return f"Unknown model: {agent.model}"
    model = MODELS[agent.model]
    if model.provider not in runtime_obj.providers:
        return (
            f"Runtime {agent.runtime} cannot serve model {agent.model}: "
            f"provider {model.provider} not in {sorted(runtime_obj.providers)}"
        )
    if session_service.get_client() is None:
        return "Session backend is not configured."
    return None


def _first_form_error(form) -> str:
    field, errors = next(iter(form.errors.items()))
    label = form.fields[field].label if field in form.fields else field
    return f"{label}: {errors[0]}"


def _detail_from_json_response(response) -> str:
    try:
        payload = json.loads(response.content.decode())
    except (TypeError, ValueError):
        return "Action failed."
    return payload.get("detail", "Action failed.")
