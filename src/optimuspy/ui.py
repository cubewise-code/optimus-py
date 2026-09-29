"""
OptimusPy Workflow UI — Lightweight local web interface for the scan → optimize → set pipeline.

Usage:
    python ui.py                                    # localhost:8765, the config.ini chosen in Settings
    python ui.py --port 9000                        # custom port
    python ui.py --config config/production.ini     # custom config.ini
"""

import argparse
import configparser
import json
import logging
import math
import os
import re
import shutil
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from TM1py.Exceptions import TM1pyRestException

from optimuspy.cli import tm1_connector
from optimuspy.core import (
    get_tm1_config, validate_cube_config,
    main as run_optimuspy, _scan_to_data_light, configure_logging, get_logfile_path, RESULT_PATH,
    set_current_directory, _collect_dimension_metadata, _compute_suggested_order,
    resolve_config_path, load_settings, save_setting, setting_open_browser, setting_ui_port,
    DEFAULT_CONFIG_INI, DEFAULT_PORT, SETTINGS_PATH
)
from optimuspy.executors import OptimizationCancelled
from optimuspy.metrics import detect_is_v12
from optimuspy.optimize_db import (
    find_run, list_runs, optimize_db, plan_path, read_json, restore_chores_for_plan,
    validate_db_config
)

# config.ini keys that carry a credential. The server never sends them to the browser.
SECRET_KEYS = frozenset({
    "password", "api_key", "application_client_secret", "cam_passport", "access_token",
})


def _browser_json(data) -> bytes:
    """JSON for the page. A value that could not be measured is NaN in Python and
    in the run artifact, but JSON.parse rejects NaN, so the page receives null."""
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return value
    return json.dumps(clean(data)).encode("utf-8")


def _error_text(e: Exception) -> str:
    """An exception as the page shows it. A TM1 REST error's own text carries the
    response headers, the session cookie among them; the page gets the status and
    TM1's message only. Any other exception is shown as it is."""
    if not isinstance(e, TM1pyRestException):
        return str(e)
    message = e.response or ""
    with suppress(ValueError, KeyError, TypeError):
        message = json.loads(message)["error"]["message"]
    status = f"TM1 returned {e.status_code} {e.reason}".rstrip()
    return f"{status}: {message}" if message else status


# The folders the UI writes JSON to, which Settings can change: each kind's
# setting in config/settings.ini, and its default.
DEFAULT_CUBE_CONFIGS_DIR = Path("cube-configs")
DEFAULT_EXPORTS_DIR = Path("exports")
FOLDERS = {
    "cube_configs": ("cube_configs_dir", DEFAULT_CUBE_CONFIGS_DIR),
    "exports": ("exports_dir", DEFAULT_EXPORTS_DIR),
}


def _folder(kind: str) -> Path:
    key, default = FOLDERS[kind]
    return Path(load_settings().get(key) or default)


def cube_configs_dir() -> Path:
    """Where the Optimize page saves cube configs."""
    return _folder("cube_configs")


def exports_dir() -> Path:
    """Where Sync Order's Export to Folder writes."""
    return _folder("exports")


def _folders_state() -> dict:
    settings = load_settings()
    return {kind: {"path": os.path.abspath(settings.get(key) or default), "is_default": not settings.get(key)}
            for kind, (key, default) in FOLDERS.items()}


# Global state. The config.ini in use and where it came from: "flag" (--config),
# "linked" or "default" (see core.resolve_config_path). Settings can switch it.
_config_ini_path = DEFAULT_CONFIG_INI
_config_source = "default"


def _resolve_static_dir() -> Path:
    """Resolve the static/ directory — works for pip install and PyInstaller frozen exe."""
    return Path(__file__).parent / "static"


def _create_tm1_connection(instance_name: str, password: str = None):
    """A logged-in TM1 service for one request, built exactly as the CLI builds it."""
    return tm1_connector(_config_ini_path, instance_name, password)()


def _typed_path(text: str) -> Path:
    """A path as it was typed or pasted: surrounding whitespace and one pair of
    quotes removed (Windows "Copy as path" adds them), and ~ expanded."""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return Path(text).expanduser()


def _parse_config_ini(path) -> configparser.ConfigParser:
    """config.ini parsed the way the CLI reads it, but raising on a file that is
    missing, unreadable or malformed instead of reading it as empty."""
    config = configparser.ConfigParser()
    with open(path, encoding="utf-8") as f:
        config.read_file(f)
    return config


def _config_ini_to_use(text: str) -> Path:
    """The absolute path of the config.ini that a typed path names: the file itself,
    or config.ini inside a folder. Raises ValueError naming the path and the reason."""
    if not (text or "").strip():
        raise ValueError("Enter the path to a config.ini, or to the folder that holds one")
    path = _typed_path(text)
    if path.is_dir():
        path = path / "config.ini"
    if not path.is_file():
        raise ValueError(f"{path}: no such file")
    try:
        config = _parse_config_ini(path)
    except (configparser.Error, OSError, UnicodeDecodeError) as e:
        raise ValueError(f"{path} can't be read as a config.ini: {e}")
    if not config.sections():
        raise ValueError(f"{path} has no instance sections")
    return Path(os.path.abspath(path))


def _config_state() -> dict:
    """The config.ini in use as Settings shows it. `error` says why a linked or
    --config file cannot be read; a default file that does not exist yet is not
    an error, it is the empty state."""
    instances, error = [], None
    try:
        instances = _parse_config_ini(_config_ini_path).sections()
    except FileNotFoundError:
        if _config_source != "default":
            error = f"config.ini not found: {_config_ini_path}"
    except (configparser.Error, OSError, UnicodeDecodeError) as e:
        error = f"{_config_ini_path} can't be read: {e}"
    return {
        "instances": instances,
        "config_path": os.path.abspath(_config_ini_path),
        "source": _config_source,
        "own_copy_exists": os.path.isfile(DEFAULT_CONFIG_INI),
        "error": error,
    }


# ---------------------------------------------------------------------------
# Job Manager — tracks background optimize/set jobs with SSE progress
# ---------------------------------------------------------------------------

# Set on every thread that is serving an HTTP request. A running job copies log
# records from the root logger; the records a request emits while it is served —
# a scan, a plan build — belong to that request, not to the job's terminal.
_request_thread = threading.local()


class JobLogHandler(logging.Handler):
    """Copies log records into a job's event log, so the page's terminal shows them."""

    def __init__(self, job):
        super().__init__(level=logging.INFO)
        self.job = job

    def emit(self, record):
        if getattr(_request_thread, "serving", False):
            return
        try:
            self.job.emit("log", {
                "timestamp": time.strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage(),
            })
        except Exception:
            pass


class Job:
    """One background job and its event log.

    Events are appended and never consumed. Every reader walks the log from its
    own cursor, so two tabs, or a stream that reconnects, each see all of it, and
    a reader that arrives after the job ended replays it. The last event is always
    `complete`, `cancelled` or `error_event`, and its data carries the final status.
    """

    def __init__(self, job_id: str, mode: str, label: str, instance: str):
        self.job_id = job_id
        self.mode = mode
        self.label = label
        self.instance = instance
        self.status = "running"
        self.error = None
        self.result_files = []
        self.started_at = time.time()
        self.completed_at = None
        self.cancel_event = threading.Event()
        # Work whose in-flight server calls Stop may abort publishes its TM1
        # service here as {"tm1": service}. See JobManager.cancel.
        self.tm1_holder = {}
        self._events = []
        self._cond = threading.Condition()

    def emit(self, event: str, data: dict):
        with self._cond:
            self._events.append({"event": event, "data": data})
            self._cond.notify_all()

    def finish(self, status: str, event: str, data: dict, error: str = None):
        with self._cond:
            self.status = status
            self.error = error
            self.completed_at = time.time()
            self._events.append({"event": event, "data": dict(data, status=status)})
            self._cond.notify_all()

    def events_after(self, cursor: int, timeout: float):
        """The events past `cursor`, waiting up to `timeout` seconds for the first.

        Returns `(events, done)`. When `done` is true the list ends with the final
        event and nothing will follow it.
        """
        with self._cond:
            if cursor >= len(self._events) and self.completed_at is None:
                self._cond.wait(timeout)
            return self._events[cursor:], self.completed_at is not None

    def summary(self) -> dict:
        with self._cond:
            return {
                "job_id": self.job_id,
                "status": self.status,
                "mode": self.mode,
                "label": self.label,
                "instance": self.instance,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "result_files": self.result_files,
                "error": self.error,
            }


class JobManager:
    """Runs one background job at a time and keeps every job for the session."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self._active = None

    def start(self, mode: str, label: str, instance: str, work) -> str:
        """Run `work(job)` on a background thread and return the job id.

        `work` returns `(status, data)` — status "completed", "failed" or
        "cancelled" — and `data` becomes the final `complete` event. Raising
        OptimizationCancelled ends the job as cancelled; any other exception ends
        it as failed. Log records at INFO and above are copied into the job's log
        while it runs. Raises RuntimeError while another job is running.
        """
        with self._lock:
            if self._active is not None and self._active.status == "running":
                raise RuntimeError("A job is already running")
            job = Job(uuid.uuid4().hex[:8], mode, label, instance)
            self._jobs[job.job_id] = job
            self._active = job
        threading.Thread(target=self._run, args=(job, work), daemon=True).start()
        return job.job_id

    def _run(self, job: Job, work):
        handler = JobLogHandler(job)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            status, data = work(job)
            final = (status, "complete", data, None)
        except OptimizationCancelled:
            logging.info("Job cancelled by user")
            final = ("cancelled", "cancelled", {"message": "Cancelled by user"}, None)
        except Exception as e:
            text = _error_text(e)
            logging.error(f"Job failed: {text}")
            final = ("failed", "error_event", {"error": text}, text)
        finally:
            root.removeHandler(handler)
        job.finish(*final)

    def cancel(self, job_id: str) -> bool:
        """Ask a running job to stop. Returns False if it is not running.

        Sets the job's cancel event, which every kind of work checks at its own
        safe boundary. If the work published a TM1 service in `job.tm1_holder`,
        that session's in-flight threads are cancelled too. Only single-cube
        Optimize does: aborting a benchmark query is safe, while aborting a
        ReorderDimensions throws away the rebuild the operator asked to finish.
        """
        job = self.get(job_id)
        if job is None or job.status != "running":
            return False
        job.cancel_event.set()
        tm1 = job.tm1_holder.get("tm1")
        if tm1 is not None:
            with suppress(Exception):
                for thread in tm1.monitoring.get_active_session_threads():
                    with suppress(Exception):
                        tm1.monitoring.cancel_thread(thread["ID"])
        return True

    def get(self, job_id: str):
        with self._lock:
            return self._jobs.get(job_id)

    def summaries(self) -> list:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted((job.summary() for job in jobs), key=lambda s: s["started_at"], reverse=True)


def _recent_result_files(instance: str, cube: str) -> list:
    """Up to four newest result files for a cube, as paths relative to results/."""
    result_files = []
    if RESULT_PATH.exists():
        candidates = [f for f in RESULT_PATH.rglob("*") if f.is_file()]
        for f in sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True):
            if f.name.startswith("checkpoint"):
                continue
            # New format (<instance>_<cube>_<ts>) or legacy (<cube>_<ts>)
            if f.name.startswith(f"{instance}_{cube}_") or f.name.startswith(f"{cube}_"):
                result_files.append(f.relative_to(RESULT_PATH).as_posix())
                if len(result_files) >= 4:
                    break
    return result_files


# Singleton
job_manager = JobManager()


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class OptimusPyHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress default HTTP logging to avoid cluttering the console
        pass

    def handle(self):
        _request_thread.serving = True
        super().handle()

    def parse_request(self):
        # The UI is a page served by this process, and nothing else should call
        # it. Refusing any other Host (DNS rebinding) or Origin (a page open in
        # another tab) before dispatch is what stops a site the user happens to
        # visit from reading config.ini or reordering cubes with its credentials.
        if not super().parse_request():
            return False
        port = self.server.server_address[1]
        own = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in own or (
                origin is not None and origin.split("://", 1)[-1] not in own):
            self._send_json(403, {"error": "Forbidden"})
            return False
        return True

    def _send_json(self, status: int, data: dict):
        body = _browser_json(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _start_job(self, mode: str, label: str, instance: str, work):
        """Start `work` as the background job and answer with its id, or 409 while one runs."""
        try:
            job = job_manager.get(job_manager.start(mode, label, instance, work))
        except RuntimeError as e:
            return self._send_json(409, {"error": _error_text(e)})
        self._send_json(200, {"job_id": job.job_id, "status": "running", "started_at": job.started_at})

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    # ---- Routing ----

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        # Static file serving
        if path == "/":
            return self._serve_static_file("index.html")
        elif path.startswith("/static/"):
            return self._serve_static_file(path[len("/static/"):])
        elif path.startswith("/images/"):
            return self._serve_image_file(path[len("/images/"):])
        # API endpoints
        elif path == "/api/instances":
            return self._handle_instances()
        elif path.startswith("/api/instance/"):
            instance_name = unquote(path[len("/api/instance/"):])
            return self._handle_get_instance(instance_name)
        elif path == "/api/saved-cubes":
            return self._handle_list_saved_cubes()
        elif path == "/api/folders":
            return self._send_json(200, _folders_state())
        elif path == "/api/results":
            return self._handle_list_results()
        elif path.startswith("/api/result/"):
            return self._handle_serve_result(path[len("/api/result/"):])
        elif path == "/api/jobs":
            return self._handle_list_jobs()
        elif path.startswith("/api/job/") and path.endswith("/stream"):
            job_id = path[len("/api/job/"):-len("/stream")]
            return self._handle_job_stream(job_id, parse_qs(url.query))
        elif path.startswith("/api/optimize-db/run/"):
            return self._handle_optimize_db_run_state(unquote(path[len("/api/optimize-db/run/"):]))
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            body = self._read_body()
        except Exception as e:
            return self._send_json(400, {"error": f"Invalid JSON: {_error_text(e)}"})

        if path == "/api/connect":
            return self._handle_connect(body)
        elif path == "/api/scan":
            return self._handle_scan(body)
        elif path == "/api/views":
            return self._handle_views(body)
        elif path == "/api/processes":
            return self._handle_processes(body)
        elif path == "/api/config":
            return self._handle_save_config(body)
        elif path == "/api/validate":
            return self._handle_validate(body)
        elif path == "/api/job/start":
            return self._handle_start_job(body)
        elif path == "/api/process_parameters":
            return self._handle_process_parameters(body)
        elif path == "/api/cube_intelligence":
            return self._handle_cube_intelligence(body)
        elif path.startswith("/api/job/") and path.endswith("/cancel"):
            job_id = path.split("/")[3]
            return self._handle_cancel_job(job_id)
        elif path == "/api/config-source":
            return self._handle_config_source(body)
        elif path == "/api/folders":
            return self._handle_set_folder(body)
        elif path == "/api/transfer/scan":
            return self._handle_transfer_scan(body)
        elif path == "/api/transfer/target-orders":
            return self._handle_transfer_target_orders(body)
        elif path == "/api/transfer/apply":
            return self._handle_transfer_apply(body)
        elif path == "/api/transfer/export":
            return self._handle_transfer_export(body)
        elif path == "/api/optimize-db/plan":
            return self._handle_optimize_db_plan(body)
        elif path == "/api/optimize-db/run":
            return self._handle_optimize_db_run(body)
        elif path == "/api/optimize-db/runs":
            return self._handle_optimize_db_runs()
        elif path == "/api/optimize-db/restore-chores":
            return self._handle_optimize_db_restore_chores(body)
        else:
            self._send_json(404, {"error": "Not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith("/api/config/"):
            filename = unquote(path[len("/api/config/"):])
            return self._handle_delete_config(filename)
        else:
            self._send_json(404, {"error": "Not found"})

    # ---- Static File Serving ----

    def _serve_static_file(self, filename: str):
        static_dir = _resolve_static_dir()
        # Sanitize: resolve and ensure the file is under static_dir
        try:
            requested = (static_dir / filename).resolve()
            if not str(requested).startswith(str(static_dir.resolve())):
                return self._send_json(403, {"error": "Forbidden"})
        except (ValueError, OSError):
            return self._send_json(400, {"error": "Invalid path"})

        if not requested.exists() or not requested.is_file():
            return self._send_json(404, {"error": "Not found"})

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
            ".json": "application/json",
        }
        ct = content_types.get(requested.suffix.lower(), "application/octet-stream")

        with open(requested, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_image_file(self, filename: str):
        images_dir = Path(__file__).parent / "images"
        try:
            requested = (images_dir / filename).resolve()
            if not str(requested).startswith(str(images_dir.resolve())):
                return self._send_json(403, {"error": "Forbidden"})
        except (ValueError, OSError):
            return self._send_json(400, {"error": "Invalid path"})

        if not requested.exists() or not requested.is_file():
            return self._send_json(404, {"error": "Not found"})

        content_types = {
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        ct = content_types.get(requested.suffix.lower(), "application/octet-stream")

        with open(requested, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    # ---- API Handlers ----

    def _handle_instances(self):
        self._send_json(200, _config_state())

    def _handle_get_instance(self, instance_name: str):
        try:
            config = get_tm1_config(_config_ini_path)
            if instance_name not in config:
                return self._send_json(404, {"error": f"Instance '{instance_name}' not found"})
            params = {key: value for key, value in config[instance_name].items()
                      if key.lower() not in SECRET_KEYS}
            self._send_json(200, {"instance": instance_name, "params": params})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_config_source(self, body: dict):
        """Switch the config.ini in use: `link` reads a file where it is, `copy`
        snapshots one into config/config.ini, `own` goes back to that copy. The
        choice is saved in the settings file, so the CLI uses it too."""
        global _config_ini_path, _config_source
        if _config_source == "flag":
            return self._send_json(409, {"error":
                "Set by --config at launch; restart without it to change the file here"})
        mode = body.get("mode")
        own = Path(DEFAULT_CONFIG_INI)
        try:
            if mode == "own":
                if not own.is_file():
                    return self._send_json(400, {"error": f"{own} does not exist"})
                save_setting("config_ini", None)
            elif mode in ("link", "copy"):
                try:
                    source = _config_ini_to_use(body.get("path"))
                except ValueError as e:
                    return self._send_json(400, {"error": _error_text(e)})
                if mode == "link":
                    save_setting("config_ini", str(source))
                else:
                    if own.is_file() and os.path.samefile(source, own):
                        return self._send_json(400, {"error":
                            f"{source} is OptimusPy's own copy already"})
                    if own.exists() and body.get("overwrite") is not True:
                        return self._send_json(409, {"exists": True,
                                                     "error": f"{own} already exists"})
                    own.parent.mkdir(parents=True, exist_ok=True)
                    # Byte for byte, so the comments and the key order survive.
                    shutil.copyfile(source, own)
                    save_setting("config_ini", None)
            else:
                return self._send_json(400, {"error": "'mode' must be link, copy or own"})
        except (OSError, configparser.Error) as e:
            return self._send_json(500, {"error": _error_text(e)})
        # A job already running keeps the path it started with.
        _config_ini_path, _config_source = resolve_config_path(None)
        self._send_json(200, _config_state())

    def _handle_set_folder(self, body: dict):
        """Change where one kind of JSON is written, or `reset` it to the default.
        The folder is created now, so a path that can't be written fails here and
        not at the first save. Files already in the old folder stay there."""
        kind = body.get("kind")
        if kind not in FOLDERS:
            return self._send_json(400, {"error": "'kind' must be cube_configs or exports"})
        key, default = FOLDERS[kind]
        try:
            if body.get("reset") is True:
                save_setting(key, None)
            else:
                if not (body.get("path") or "").strip():
                    return self._send_json(400, {"error": "Enter the path to a folder"})
                path = Path(os.path.abspath(_typed_path(body["path"])))
                if path.exists() and not path.is_dir():
                    return self._send_json(400, {"error": f"{path} is a file, not a folder"})
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    return self._send_json(400, {"error": f"{path} can't be created: {_error_text(e)}"})
                # The default is stored as no setting at all.
                save_setting(key, None if path == Path(os.path.abspath(default)) else str(path))
        except (OSError, configparser.Error) as e:
            return self._send_json(500, {"error": _error_text(e)})
        self._send_json(200, _folders_state())

    def _handle_connect(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                server_name = tm1.server.get_server_name()
                cubes = tm1.cubes.get_all_names()
                self._send_json(200, {
                    "success": True,
                    "server_name": server_name,
                    "cube_count": len(cubes),
                })
        except Exception as e:
            self._send_json(502, {"error": f"Connection failed: {_error_text(e)}"})

    def _handle_scan(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        ram_percent = body.get("ram_percent", 60)
        include_optimized = body.get("include_optimized", False)
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                is_v12 = detect_is_v12(tm1)
                data = _scan_to_data_light(tm1, instance, ram_percent, include_optimized, is_v12=is_v12)
                self._send_json(200, data)
        except Exception as e:
            self._send_json(500, {"error": f"Scan failed: {_error_text(e)}"})

    def _handle_views(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        cube = body.get("cube")
        if not instance or not cube:
            return self._send_json(400, {"error": "Missing 'instance' or 'cube'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                private_views, public_views = tm1.views.get_all_names(cube_name=cube)
                self._send_json(200, {"views": sorted(public_views)})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_processes(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                processes = tm1.processes.get_all_names()
                # Filter out control processes
                processes = [p for p in processes if not p.startswith("}")]
                self._send_json(200, {"processes": sorted(processes)})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_process_parameters(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        process_name = body.get("process_name")
        if not instance or not process_name:
            return self._send_json(400, {"error": "Missing 'instance' or 'process_name'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                process = tm1.processes.get(process_name)
                params = [
                    {"name": p["Name"], "prompt": p.get("Prompt", ""),
                     "value": p.get("Value", ""), "type": p.get("Type", "String")}
                    for p in process.parameters
                ]
                self._send_json(200, {"process_name": process_name, "parameters": params})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_cube_intelligence(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        cube = body.get("cube")
        if not instance or not cube:
            return self._send_json(400, {"error": "Missing 'instance' or 'cube'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                visible_order = tm1.cubes.get_dimension_names(cube_name=cube)
                storage_order = tm1.cubes.get_storage_dimension_order(cube_name=cube)
                dimensions_metadata = _collect_dimension_metadata(tm1, visible_order)
                suggested = _compute_suggested_order(dimensions_metadata)
            self._send_json(200, {
                "cube": cube,
                "storage_order": list(storage_order),
                "dimensions_metadata": dimensions_metadata,
                "suggested_order": suggested,
            })
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_save_config(self, body: dict):
        config_data = body.get("config")
        filename = body.get("filename")
        if not config_data or not filename:
            return self._send_json(400, {"error": "Missing 'config' or 'filename'"})

        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        if not safe_name.endswith(".json"):
            safe_name += ".json"

        config_path = cube_configs_dir() / safe_name
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)
        except OSError as e:
            return self._send_json(500, {"error": _error_text(e)})

        self._send_json(200, {"path": os.path.abspath(config_path), "filename": safe_name})

    def _handle_delete_config(self, filename: str):
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        config_path = cube_configs_dir() / safe_name
        if not config_path.exists():
            return self._send_json(404, {"error": "Config not found"})
        try:
            config_path.unlink()
            self._send_json(200, {"success": True})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_list_saved_cubes(self):
        configs = []
        configs_dir = cube_configs_dir()
        if configs_dir.exists():
            for f in sorted(configs_dir.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    configs.append({
                        "filename": f.name,
                        "cube": data.get("cube", ""),
                        "instance": data.get("instance", ""),
                        "mode": "predefined" if data.get("predefined_orders") else "greedy",
                        "views": data.get("views", []),
                        "executions": data.get("executions", 5),
                        "last_modified": f.stat().st_mtime,
                    })
                except Exception:
                    pass
        self._send_json(200, {"saved_cubes": configs})

    def _handle_validate(self, body: dict):
        config = body.get("config")
        mode = body.get("mode", "optimize")
        if not config:
            return self._send_json(400, {"error": "Missing 'config'"})
        try:
            validate_cube_config(config, mode)
            self._send_json(200, {"valid": True})
        except ValueError as e:
            self._send_json(200, {"valid": False, "error": _error_text(e)})

    def _handle_start_job(self, body: dict):
        mode = body.get("mode", "optimize")
        cube_config = body.get("cube_config")
        password = body.get("password")
        if not cube_config:
            return self._send_json(400, {"error": "Missing 'cube_config'"})
        cube = cube_config.get("cube", "unknown")
        instance = cube_config.get("instance", "unknown")

        def work(job):
            success = run_optimuspy(
                mode=mode, cube_config=cube_config, config_ini_path=_config_ini_path,
                password=password, cancel_event=job.cancel_event, tm1_holder=job.tm1_holder)
            job.result_files = _recent_result_files(instance, cube)
            return ("completed" if success else "failed"), {
                "success": success, "result_files": job.result_files}

        self._start_job(mode, cube, instance, work)

    def _handle_cancel_job(self, job_id: str):
        if job_manager.cancel(job_id):
            return self._send_json(200, {"status": "cancelling"})
        self._send_json(404, {"error": "Job not found or not running"})

    def _handle_job_stream(self, job_id: str, query: dict):
        job = job_manager.get(job_id)
        if job is None:
            return self._send_json(404, {"error": "Job not found"})
        # EventSource sends Last-Event-ID when it reconnects by itself; a page that
        # reopens a stream it has already read passes ?after= instead.
        try:
            cursor = max(0, int(self.headers.get("Last-Event-ID") or query.get("after", ["0"])[0]))
        except ValueError:
            cursor = 0

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        while True:
            events, done = job.events_after(cursor, timeout=15)
            try:
                if not events and not done:
                    self.wfile.write(b": heartbeat\n\n")
                for event in events:
                    cursor += 1
                    self.wfile.write(f"id: {cursor}\nevent: {event['event']}\n"
                                     f"data: {_browser_json(event['data']).decode()}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return
            if done:
                return

    def _handle_transfer_scan(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        ram_percent = body.get("ram_percent", 60)
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                is_v12 = detect_is_v12(tm1)
                data = _scan_to_data_light(tm1, instance, ram_percent, include_optimized=True, is_v12=is_v12)
                self._send_json(200, data)
        except Exception as e:
            self._send_json(500, {"error": f"Scan failed: {_error_text(e)}"})

    def _handle_transfer_target_orders(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        cubes = body.get("cubes", [])
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        if not cubes:
            return self._send_json(400, {"error": "Missing 'cubes'"})
        try:
            with _create_tm1_connection(instance, password) as tm1:
                orders = {}
                missing = []
                for cube_name in cubes:
                    if not tm1.cubes.exists(cube_name):
                        missing.append(cube_name)
                        continue
                    storage_order = tm1.cubes.get_storage_dimension_order(cube_name=cube_name)
                    orders[cube_name] = list(storage_order)
                self._send_json(200, {"orders": orders, "missing": missing})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_transfer_apply(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        orders = body.get("orders", {})
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        if not orders:
            return self._send_json(400, {"error": "Missing 'orders'"})
        def work(job):
            results = []
            total = len(orders)
            with _create_tm1_connection(instance, password) as tm1:
                for index, (cube, order) in enumerate(orders.items(), 1):
                    # Between cubes is the only safe place to stop: a storage
                    # reorder already sent runs to completion on the server.
                    if job.cancel_event.is_set():
                        break
                    try:
                        if list(tm1.cubes.get_storage_dimension_order(cube_name=cube)) == list(order):
                            result = {"cube": cube, "status": "skipped"}
                            logging.info(f"'{cube}' already has this order — skipped ({index}/{total})")
                        else:
                            tm1.cubes.update_storage_dimension_order(cube, order)
                            result = {"cube": cube, "status": "applied"}
                            logging.info(f"Applied dimension order to '{cube}' ({index}/{total})")
                    except Exception as e:
                        result = {"cube": cube, "status": "failed", "error": str(e)}
                        logging.error(f"Failed to apply order to '{cube}': {e}")
                    results.append(result)
                    job.emit("progress", dict(result, index=index, total=total))
            if len(results) < total:
                status = "cancelled"
            elif any(r["status"] == "failed" for r in results):
                status = "failed"
            else:
                status = "completed"
            return status, {"success": status == "completed", "results": results}

        self._start_job("transfer", f"{len(orders)} cubes", instance, work)

    def _handle_transfer_export(self, body: dict):
        instance = body.get("instance", "")
        orders = body.get("orders", {})
        if not orders:
            return self._send_json(400, {"error": "Missing 'orders'"})
        try:
            export_dir = exports_dir()
            export_dir.mkdir(parents=True, exist_ok=True)
            files = []
            for cube_name, dim_order in orders.items():
                safe_name = "".join(c for c in cube_name if c.isalnum() or c in "._-")
                safe_name = safe_name.strip() or "cube"
                config_data = {
                    "instance": instance,
                    "cube": cube_name,
                    "predefined_orders": [dim_order],
                    "executions": 1,
                    "output": "csv",
                }
                file_path = export_dir / f"{safe_name}.json"
                with open(file_path, "w") as f:
                    json.dump(config_data, f, indent=2)
                files.append(os.path.abspath(file_path))
            self._send_json(200, {"files": files, "folder": os.path.abspath(export_dir)})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    # Instruction fields the Optimize DB form can set; everything else in the
    # request body (instance, password) is connection detail, not an option.
    OPTIMIZE_DB_OPTION_KEYS = (
        "time_limit_hours", "order", "exclude_cubes", "min_cube_mb", "string_policy",
        "include_optimized", "revert_on_regression", "disable_active_chores", "max_consecutive_failures",
    )

    def _optimize_db_config(self, body: dict) -> dict:
        config = {"instance": body.get("instance")}
        for key in self.OPTIMIZE_DB_OPTION_KEYS:
            if key in body:
                config[key] = body[key]
        return config

    def _handle_optimize_db_plan(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        if not instance:
            return self._send_json(400, {"error": "Missing 'instance'"})
        config = self._optimize_db_config(body)
        try:
            validate_db_config(config)
        except ValueError as e:
            return self._send_json(400, {"error": _error_text(e)})
        try:
            connect = tm1_connector(_config_ini_path, instance, password)
            plan = optimize_db(connect, config=config, dry_run=True)
            self._send_json(200, plan)
        except Exception as e:
            self._send_json(500, {"error": f"Plan failed: {_error_text(e)}"})

    def _handle_optimize_db_run(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        plan_id = body.get("plan_id")
        if not instance or not plan_id:
            return self._send_json(400, {"error": "Missing 'instance' or 'plan_id'"})
        if instance not in get_tm1_config(_config_ini_path) or Path(plan_id).name != plan_id:
            return self._send_json(400, {"error": "Unknown instance or malformed plan id"})
        # A plan that already has a run on disk was started before: running it
        # again continues that run against its original deadline. Otherwise the
        # plan file the operator reviewed is executed as written. Nothing is
        # re-planned here.
        try:
            _, existing = find_run(plan_id)
        except FileNotFoundError:
            path = plan_path(plan_id, instance)
            if not path.is_file():
                return self._send_json(404, {"error": f"No plan '{plan_id}' for instance '{instance}'"})
            source = {"plan": read_json(path)}
        else:
            if existing.get("instance") != instance:
                return self._send_json(400, {
                    "error": f"Plan '{plan_id}' belongs to instance '{existing.get('instance')}'"})
            source = {"resume_plan_id": plan_id}
        connect = tm1_connector(_config_ini_path, instance, password)

        def work(job):
            run = optimize_db(connect, cancel_event=job.cancel_event, **source)
            # A cancelled or time-limited sweep stops at a cube boundary and still
            # returns a complete run artifact — a partial result, not a failure.
            # A plan with no cube to reorder comes back as the plan itself, with
            # no status: nothing to do is a clean finish.
            status = {None: "completed", "completed": "completed",
                      "stopped_time_limit": "completed",
                      "cancelled": "cancelled"}.get(run.get("status"), "failed")
            return status, {"success": status == "completed", "run": run}

        self._start_job("optimize-db", plan_id, instance, work)

    def _handle_optimize_db_runs(self):
        try:
            self._send_json(200, {"runs": list_runs()})
        except Exception as e:
            self._send_json(500, {"error": _error_text(e)})

    def _handle_optimize_db_run_state(self, plan_id: str):
        if Path(plan_id).name != plan_id:
            return self._send_json(400, {"error": "Malformed plan id"})
        try:
            _, run = find_run(plan_id)
        except FileNotFoundError:
            return self._send_json(404, {"error": f"No Optimize DB run for plan '{plan_id}'"})
        self._send_json(200, {"run": run})

    def _handle_optimize_db_restore_chores(self, body: dict):
        instance = body.get("instance")
        password = body.get("password")
        plan_id = body.get("plan_id")
        if not instance or not plan_id:
            return self._send_json(400, {"error": "Missing 'instance' or 'plan_id'"})
        try:
            connect = tm1_connector(_config_ini_path, instance, password)
            restored = restore_chores_for_plan(connect, plan_id)
            self._send_json(200, {"restored": restored})
        except Exception as e:
            self._send_json(500, {"error": f"Chore restore failed: {_error_text(e)}"})

    def _handle_list_results(self):
        results = []
        ts_pattern = re.compile(r'_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$')
        if RESULT_PATH.exists():
            files = [f for f in RESULT_PATH.rglob("*") if f.is_file()]
            for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
                if f.name.startswith("checkpoint"):
                    continue
                # Instance is the immediate parent dir (or "" for legacy top-level files)
                parent = f.parent
                instance = parent.name if parent != RESULT_PATH else ""
                # Extract cube name: strip instance prefix (if present) and trailing timestamp
                stem = f.stem
                if instance and stem.startswith(f"{instance}_"):
                    stem = stem[len(instance) + 1:]
                m = ts_pattern.search(stem)
                cube_name = stem[:m.start()] if m else stem
                rel = f.relative_to(RESULT_PATH).as_posix()
                results.append({
                    "filename": rel,
                    "cube": cube_name,
                    "instance": instance,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                    "type": f.suffix[1:],
                })
        self._send_json(200, {"results": results})

    def _handle_list_jobs(self):
        self._send_json(200, {"jobs": job_manager.summaries()})

    def _handle_serve_result(self, filename: str):
        # Sanitize: only serve from results/, decode URL-encoded names (e.g. spaces).
        # Support one level of subdirectory (results/<instance>/<file>) while blocking
        # path traversal.
        decoded = unquote(filename)
        rel = Path(decoded)
        if rel.is_absolute() or any(part in ("..", "") for part in rel.parts):
            return self._send_json(400, {"error": "Invalid path"})
        if len(rel.parts) > 2:
            return self._send_json(400, {"error": "Invalid path"})

        root = Path(RESULT_PATH).resolve()
        safe = (root / rel).resolve()
        try:
            safe.relative_to(root)
        except ValueError:
            return self._send_json(400, {"error": "Invalid path"})

        if not safe.exists() or not safe.is_file():
            return self._send_json(404, {"error": "File not found"})

        content_types = {
            ".html": "text/html",
            ".csv": "text/csv",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".png": "image/png",
        }
        ct = content_types.get(safe.suffix, "application/octet-stream")

        with open(safe, "rb") as f:
            data = f.read()

        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)




# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    global _config_ini_path, _config_source

    parser = argparse.ArgumentParser(description="OptimusPy Workflow UI")
    parser.add_argument('--port', type=int, default=None,
                        help=f"Port to listen on (default: ui_port in {SETTINGS_PATH.as_posix()}, "
                             f"else {DEFAULT_PORT})")
    parser.add_argument('--config', dest='config_ini', default=None,
                        help="Path to TM1 connection config.ini (default: the file chosen on "
                             f"the Settings page, else {DEFAULT_CONFIG_INI})")
    args = parser.parse_args(argv)

    # Only change CWD for frozen exe — pip/script users expect CWD-relative paths.
    # Before anything is read: the settings file is relative to it.
    if getattr(sys, 'frozen', False):
        set_current_directory()

    # Every way in (`optimuspy ui`, a double-click, `python ui.py`) arrives here
    # with logging not yet set up.
    configure_logging()
    log_path = get_logfile_path()

    # A linked file that is missing still starts the UI: Settings reports it, and
    # that is where the link is changed.
    try:
        _config_ini_path, _config_source = resolve_config_path(args.config_ini)
    except FileNotFoundError as e:
        print(f"ERROR: config.ini not found: {e}")
        sys.exit(1)

    port = args.port if args.port is not None else setting_ui_port()
    server = ThreadingHTTPServer(('127.0.0.1', port), OptimusPyHandler)
    url = f"http://127.0.0.1:{port}"

    sources = {"flag": "set by --config", "linked": "linked from Settings", "default": "OptimusPy's own copy"}
    print("\n  OptimusPy Workflow UI")
    print(f"  {'─' * 40}")
    print(f"  URL:        {url}")
    print(f"  Config:     {_config_ini_path} ({sources[_config_source]})")
    if SETTINGS_PATH.is_file():
        print(f"  Settings:   {SETTINGS_PATH}")
    print(f"  Log:        {log_path}")
    print("  Press Ctrl+C to stop\n")

    if setting_open_browser():
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
