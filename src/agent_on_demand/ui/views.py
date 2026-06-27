from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from agent_on_demand.analytics import capture as posthog_capture
from agent_on_demand.models import (
    Agent,
    AgentSession,
    AgentSessionLog,
    APIKey,
    Environment,
)
from agent_on_demand.ui.forms import APIKeyCreateForm, RegisterForm


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


@login_required(login_url="/ui/login")
def agents_list(request):
    agents = Agent.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "ui/agents_list.html", {"agents": agents})


@login_required(login_url="/ui/login")
def agent_detail(request, agent_id):
    agent = get_object_or_404(Agent, pk=agent_id, user=request.user)
    return render(request, "ui/agent_detail.html", {"agent": agent})


@login_required(login_url="/ui/login")
def environments_list(request):
    envs = Environment.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "ui/environments_list.html", {"envs": envs})


@login_required(login_url="/ui/login")
def environment_detail(request, environment_id):
    env = get_object_or_404(Environment, pk=environment_id, user=request.user)
    return render(request, "ui/environment_detail.html", {"env": env})


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
        {"session": session, "logs": logs, "resources": session.resources.all()},
    )
<<<<<<< Updated upstream
||||||| Stash base


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
=======


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
                SessionTurn.objects.filter(session=locked).aggregate(n=Max("turn_number"))["n"] or 0
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
>>>>>>> Stashed changes
