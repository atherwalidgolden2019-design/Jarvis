"""JARVIS - a voice-enabled AI assistant powered by Claude.

Run:  python server.py   then open http://127.0.0.1:5000 in Chrome or Edge.
"""
import hmac
import os
import platform
import subprocess
import time
import webbrowser
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory

load_dotenv()

MODEL = os.getenv("JARVIS_MODEL", "claude-sonnet-5-5")
USER_NAME = os.getenv("JARVIS_USER_NAME", "sir")
MAX_TOOL_ROUNDS = 6
# "local" = runs on your computer and can open its apps.
# "cloud" = hosted online for your phone: needs an access code, no app launching.
CLOUD = os.getenv("JARVIS_MODE", "local").lower() == "cloud"
ACCESS_CODE = os.getenv("JARVIS_ACCESS_CODE", "")
RATE_LIMIT_PER_MIN = int(os.getenv("JARVIS_RATE_LIMIT", "20"))

app = Flask(__name__, static_folder="static", static_url_path="/static")
client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment

SYSTEM_PROMPT = f"""You are J.A.R.V.I.S., a calm, razor-sharp, subtly witty personal AI assistant.
You address the user as "{USER_NAME}". Your replies are SPOKEN ALOUD, so:
- Keep them short: one to three sentences unless asked for detail.
- Never use markdown, bullet points, emoji, or URLs read out character by character.
- Be direct and competent, with dry understated humor when it fits.
Use your tools whenever they help: check the time, get weather, open websites or apps,
set reminders, and search the web for anything current. After using a tool, confirm briefly
what you did. If a request is impossible, say so plainly and offer an alternative."""
if CLOUD:
    SYSTEM_PROMPT += (
        "\nThe user is talking to you from their iPhone. You cannot launch phone apps, "
        "but you can open websites on the phone and set reminders."
    )

# Only these apps can be launched, so the model can never run arbitrary commands.
APPS = {
    "calculator": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
    "notepad": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
    "file explorer": {"Windows": "explorer", "Darwin": "Finder", "Linux": "xdg-open ."},
    "terminal": {"Windows": "cmd", "Darwin": "Terminal", "Linux": "x-terminal-emulator"},
    "chrome": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "spotify": {"Windows": "spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "excel": {"Windows": "excel", "Darwin": "Microsoft Excel", "Linux": "libreoffice --calc"},
    "word": {"Windows": "winword", "Darwin": "Microsoft Word", "Linux": "libreoffice --writer"},
}

TOOLS = [
    {
        "name": "get_datetime",
        "description": "Get the current local date and time on the user's computer.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather",
        "description": "Get current weather and today's forecast for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City name, e.g. Cairo"}},
            "required": ["city"],
        },
    },
    {
        "name": "open_website",
        "description": "Open a website in the user's default browser. Use a full URL.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "e.g. https://youtube.com"}},
            "required": ["url"],
        },
    },
    {
        "name": "open_app",
        "description": "Launch an application on the user's computer. Allowed apps: "
        + ", ".join(APPS),
        "input_schema": {
            "type": "object",
            "properties": {"app": {"type": "string", "enum": list(APPS)}},
            "required": ["app"],
        },
    },
    {
        "name": "set_reminder",
        "description": "Set a spoken reminder that fires after a number of minutes "
        "(works while the Jarvis page is open).",
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "number", "description": "Minutes from now"},
                "message": {"type": "string", "description": "What to remind about"},
            },
            "required": ["minutes", "message"],
        },
    },
    # Server-side tool run by Anthropic; no code needed on our side.
    {"type": "web_search_20250305", "name": "web_search", "max_uses": 3},
]

if CLOUD:  # a hosted server has no apps worth launching
    TOOLS = [t for t in TOOLS if t["name"] != "open_app"]

WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "violent showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail",
}


def tool_get_datetime(_args, _actions):
    try:  # use the phone's time zone, not the server's
        now = datetime.now(ZoneInfo(getattr(g, "tz", "") or "UTC"))
    except Exception:  # noqa: BLE001
        now = datetime.now()
    return now.strftime("%A, %B %d, %Y, %I:%M %p")


def tool_get_weather(args, _actions):
    city = args["city"]
    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=10,
    ).json()
    if not geo.get("results"):
        return f"Could not find a city called {city}."
    place = geo["results"][0]
    data = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=10,
    ).json()
    cur, day = data["current"], data["daily"]
    return (
        f"{place['name']}, {place.get('country', '')}: {cur['temperature_2m']}°C "
        f"(feels like {cur['apparent_temperature']}°C), "
        f"{WEATHER_CODES.get(cur['weather_code'], 'mixed conditions')}, "
        f"wind {cur['wind_speed_10m']} km/h. Today's range "
        f"{day['temperature_2m_min'][0]}°C to {day['temperature_2m_max'][0]}°C."
    )


def tool_open_website(args, actions):
    url = args["url"].strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if CLOUD:  # the phone opens it, not the server
        actions.append({"type": "open_url", "url": url})
    else:
        webbrowser.open(url)
    return f"Opened {url} in the browser."


def tool_open_app(args, actions):
    name = args["app"]
    if name not in APPS:
        return f"I am not allowed to launch {name}."
    system = platform.system()
    cmd = APPS[name].get(system)
    if not cmd:
        return f"{name} is not supported on {system}."
    try:
        if system == "Windows":
            subprocess.Popen(f"start \"\" {cmd}", shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", cmd])
        else:
            subprocess.Popen(cmd.split())
        return f"Launched {name}."
    except Exception as exc:  # noqa: BLE001
        return f"Could not launch {name}: {exc}"


def tool_set_reminder(args, actions):
    minutes = max(0.1, float(args["minutes"]))
    actions.append({"type": "reminder", "seconds": minutes * 60, "text": args["message"]})
    return f"Reminder set for {minutes:g} minutes from now."


HANDLERS = {
    "get_datetime": tool_get_datetime,
    "get_weather": tool_get_weather,
    "open_website": tool_open_website,
    "open_app": tool_open_app,
    "set_reminder": tool_set_reminder,
}


def run_agent(messages):
    """Run Claude with tools until it produces a final spoken answer."""
    actions = []
    resp = None
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "tool_use":
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                handler = HANDLERS.get(block.name)
                try:
                    out = handler(block.input, actions) if handler else "Unknown tool."
                except Exception as exc:  # noqa: BLE001
                    out = f"Tool error: {exc}"
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": str(out)}
                )
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason == "pause_turn":  # long server-side search; just continue
            continue
        break

    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text or "I'm afraid I have nothing to report.", actions


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/health")
def health():
    return jsonify(
        ok=True,
        has_key=bool(os.getenv("ANTHROPIC_API_KEY")),
        needs_code=bool(ACCESS_CODE),
        cloud=CLOUD,
    )


_hits = defaultdict(deque)


def rate_limited(ip):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return True
    q.append(now)
    return False


@app.post("/api/chat")
def chat():
    if CLOUD and not ACCESS_CODE:
        return jsonify(error="Server misconfigured: set JARVIS_ACCESS_CODE."), 503
    if ACCESS_CODE and not hmac.compare_digest(
        request.headers.get("X-Access-Code", ""), ACCESS_CODE
    ):
        return jsonify(error="Wrong access code."), 401
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if rate_limited(ip):
        return jsonify(error="Too many requests. Give me a minute."), 429
    body = request.get_json(silent=True) or {}
    g.tz = str(body.get("tz", ""))[:64]
    history = body.get("messages", [])[-20:]
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    if not messages or messages[-1]["role"] != "user":
        return jsonify(error="No user message."), 400
    try:
        reply, actions = run_agent(messages)
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 500
    return jsonify(reply=reply, actions=actions)


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n!! ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.\n")
    # Local mode is bound to localhost only: Jarvis can open apps on this machine.
    # In cloud mode, gunicorn serves the app instead (see Procfile).
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
