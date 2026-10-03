"""Alfred personal ambient dashboard."""

from __future__ import annotations

import logging
import secrets
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from ipaddress import ip_address

from flask import Flask, Response, abort, jsonify, render_template, request, send_file, stream_with_context

from config import settings
from services.assistant import AssistantChannel, AssistantService
from services.calendar import CalendarService
from services.display import DisplayControlChannel
from services.health import HealthService
from services.speech import SpeechError, SpeechService
from services.tasks import TasksService
from services.tv import TvControlError, TvService
from services.voice_input import VoiceInputService
from services.weather import WeatherService


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = Flask(__name__)
calendar_service = CalendarService(settings)
tasks_service = TasksService(settings)
health_service = HealthService(settings)
weather_service = WeatherService(settings)
tv_service = TvService(settings)
assistant_service = AssistantService(
    tasks_service, calendar_service, health_service, weather_service,
    settings.dashboard_time_zone,
)
assistant_channel = AssistantChannel()
display_control_channel = DisplayControlChannel()
speech_service = SpeechService()
voice_input_service = None
SERVICES = {
    "tasks": tasks_service,
    "calendar": calendar_service,
    "health": health_service,
    "weather": weather_service,
}
POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="alfred-api")

LAN_REMOTE_PATHS = {
    "/remote",
    "/api/tv/status",
    "/api/tv/power",
    "/api/tv/command",
    "/api/assistant/query",
    "/api/display/refresh",
    "/api/display/scroll",
    "/static/remote.css",
    "/static/remote.js",
    "/static/assets/space-grotesk-latin-wght-normal.woff2",
}


@app.before_request
def keep_private_dashboard_data_local():
    """Expose only the phone remote when Alfred listens on the home LAN."""
    try:
        is_local = ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        is_local = False
    if not is_local and request.path not in LAN_REMOTE_PATHS:
        abort(404)


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if response.mimetype == "application/json" else "no-cache"
    return response


@app.get("/")
def index():
    return render_template(
        "index.html",
        display_name=settings.display_name,
        dashboard_time_zone=settings.dashboard_time_zone,
    )


@app.get("/remote")
def remote():
    return render_template("remote.html")


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


def _single(name: str):
    return jsonify(SERVICES[name].get())


@app.get("/api/tasks")
def api_tasks():
    return _single("tasks")


@app.get("/api/calendar")
def api_calendar():
    return _single("calendar")


@app.get("/api/health")
def api_health():
    return _single("health")


@app.get("/api/heart-rate")
def api_heart_rate():
    return jsonify(health_service.get_heart_rate())


@app.post("/api/heart-rate/refresh")
def api_heart_rate_refresh():
    return jsonify(health_service.get_heart_rate(force=True))


@app.get("/api/steps")
def api_steps():
    return jsonify(health_service.get_steps())


@app.post("/api/steps/refresh")
def api_steps_refresh():
    return jsonify(health_service.get_steps(force=True))


@app.get("/api/weather")
def api_weather():
    return _single("weather")


@app.get("/api/tv/status")
def api_tv_status():
    status = tv_service.status()
    status["name"] = "Alfred"
    status["protected"] = bool(settings.tv_remote_token)
    return jsonify(status)


def _authorized_remote_request() -> bool:
    # The custom header blocks cross-origin HTML forms. The private token then
    # restricts deliberate requests from other devices on the LAN.
    configured = settings.tv_remote_token
    if not configured or request.headers.get("X-Alfred-Remote") != "1":
        return False
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
        return False
    supplied = request.headers.get("X-Alfred-Remote-Token", "")
    return secrets.compare_digest(supplied, configured)


@app.post("/api/tv/power")
def api_tv_power():
    if not _authorized_remote_request():
        return jsonify({"ok": False, "error": "Remote access denied."}), 403
    try:
        return jsonify(tv_service.power())
    except TvControlError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.post("/api/tv/command")
def api_tv_command():
    if not _authorized_remote_request():
        return jsonify({"ok": False, "error": "Remote access denied."}), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("action") not in (
        "volume_up", "volume_down", "hdmi_1", "hdmi_2",
    ):
        return jsonify({"ok": False, "error": "Invalid TV command."}), 400
    try:
        return jsonify(tv_service.command(payload["action"]))
    except TvControlError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.post("/api/display/refresh")
def api_display_refresh():
    """Ask the local Chromium kiosk to force-refresh its data and reload once."""
    if not _authorized_remote_request():
        return jsonify({"ok": False, "error": "Remote access denied."}), 403
    sequence = display_control_channel.publish("refresh")
    return jsonify({"ok": True, "sequence": sequence})


@app.post("/api/display/scroll")
def api_display_scroll():
    """Move the local kiosk to a normalized vertical position from the phone."""
    if not _authorized_remote_request():
        return jsonify({"ok": False, "error": "Remote access denied."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        position = max(0.0, min(1.0, float(payload.get("position", 0))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid scroll position."}), 400
    sequence = display_control_channel.publish("scroll", position=position)
    return jsonify({"ok": True, "sequence": sequence, "position": position})


@app.get("/api/display/control")
def api_display_control():
    # This route is intentionally absent from LAN_REMOTE_PATHS, so only the
    # local kiosk can consume pending display commands.
    return jsonify(display_control_channel.take())


@app.post("/api/assistant/query")
def api_assistant_query():
    if not _authorized_remote_request():
        return jsonify({"ok": False, "error": "Remote access denied."}), 403

    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"ok": False, "error": "Type or say a question first."}), 400
    if len(query) > 500:
        return jsonify({"ok": False, "error": "That question is too long."}), 400

    try:
        return jsonify(_execute_assistant_query(query))
    except TvControlError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


def _execute_assistant_query(query: str) -> dict:
    """Run one command from either the phone or the local USB microphone."""
    if assistant_service.is_power_command(query):
        tv_service.power()
        result = {
            "ok": True,
            "intent": "tv_power",
            "answer": "TV power signal sent.",
            "warning": "The Sony power command is a toggle.",
        }
    else:
        result = assistant_service.answer(query)
    result["sequence"] = assistant_channel.publish(result["answer"])
    return result


def _execute_usb_voice_command(query: str) -> dict:
    try:
        return _execute_assistant_query(query)
    except TvControlError as exc:
        answer = f"I couldn't control the television. {exc}"
        return {
            "ok": False,
            "intent": "tv_power",
            "answer": answer,
            "sequence": assistant_channel.publish(answer),
        }


@app.get("/api/assistant/latest")
def api_assistant_latest():
    after = request.args.get("after", type=int)
    return jsonify(assistant_channel.latest(after))


@app.get("/api/voice/status")
def api_voice_status():
    return jsonify(voice_input_service.status())


@app.get("/api/assistant/speech/<int:sequence>")
def api_assistant_speech(sequence: int):
    message = assistant_channel.message_for(sequence)
    if message is None:
        return jsonify({"ok": False, "error": "That response is no longer available."}), 404
    try:
        audio, mimetype, suffix = speech_service.prepared_audio(sequence, message)
    except SpeechError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    return send_file(
        BytesIO(audio),
        mimetype=mimetype,
        download_name=f"alfred-{sequence}.{suffix}",
        max_age=0,
    )


@app.get("/api/assistant/speech-stream/<int:sequence>")
def api_assistant_speech_stream(sequence: int):
    """Stream the natural voice immediately; the WAV route remains fallback."""
    message = assistant_channel.message_for(sequence)
    if message is None:
        return jsonify({"ok": False, "error": "That response is no longer available."}), 404
    return Response(
        stream_with_context(speech_service.stream_edge(message)),
        mimetype="audio/mpeg",
        headers={"X-Accel-Buffering": "no"},
    )


@app.get("/api/dashboard")
def api_dashboard():
    return jsonify(_dashboard_payload(force=False))


@app.post("/api/refresh")
def api_refresh():
    return jsonify(_dashboard_payload(force=True))


def _dashboard_payload(force: bool) -> dict:
    futures = {
        name: POOL.submit(service.get, force)
        for name, service in SERVICES.items()
    }
    return {name: future.result() for name, future in futures.items()}


voice_input_service = VoiceInputService(settings, _execute_usb_voice_command)
voice_input_service.start()


if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=False, threaded=True)
