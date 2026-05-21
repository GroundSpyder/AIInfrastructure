"""bug-fairy client for Python apps.

Usage (manual reports):
    from bug_fairy import BugFairy

    fairy = BugFairy(api_key="your-key", app="Spellstorm")
    fairy.report("Login broken", "Users can't log in after password reset", logs=traceback_str)

Usage (automatic error capture — unhandled exceptions):
    fairy = BugFairy(api_key="your-key", app="Spellstorm")
    fairy.install()  # hooks sys.excepthook

Usage (capture handled exceptions in try/except):
    try:
        do_something()
    except SomeError as e:
        fairy.capture_exception(e)  # reports to bug-fairy, then you handle normally
        return error_response()

Usage (Flask middleware — captures all error responses):
    fairy.install_flask(app)  # catches 4xx/5xx responses with exception context

Usage (FastAPI middleware — captures all error responses):
    fairy.install_fastapi(app)  # catches exceptions in request handlers
"""

import atexit
import hashlib
import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
from typing import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.error import URLError

log = logging.getLogger("bug_fairy")


class BugFairy:
    def __init__(
        self,
        api_key: str,
        app: str,
        url: str = "https://bugs.birdmug.com/api/report",
        flush_interval: float = 10.0,
        dedup_window: float = 300.0,
        capture_screenshot: bool = True,
        min_status_code: int = 400,
        should_report_http: Callable[[object, object], bool] | None = None,
        rate_limit_cooldown: float = 60.0,
    ):
        self.api_key = api_key
        self.app = app
        self.url = url
        self.flush_interval = flush_interval
        self.dedup_window = dedup_window
        self.capture_screenshot = capture_screenshot
        self.min_status_code = min_status_code
        self.should_report_http = should_report_http
        self.rate_limit_cooldown = rate_limit_cooldown

        self._queue: queue.Queue = queue.Queue()
        self._recent_fingerprints: dict[str, float] = {}
        self._lock = threading.Lock()
        self._installed = False
        self._original_excepthook = None
        self._flush_thread = None
        self._running = False
        self._rate_limited_until = 0.0

    def install(self):
        """Hook into sys.excepthook to automatically capture unhandled exceptions."""
        if self._installed:
            return

        self._original_excepthook = sys.excepthook
        sys.excepthook = self._excepthook

        try:
            threading.excepthook = self._threading_excepthook
        except AttributeError:
            pass  # Python < 3.8

        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        atexit.register(self.flush)

        self._installed = True
        log.info("bug-fairy installed for %s", self.app)

    def install_flask(self, flask_app):
        """Install Flask middleware that captures all error responses.

        Uses got_request_exception signal to capture exception context (since
        sys.exc_info() is cleared by the time after_request runs), and
        after_request to capture error responses without exceptions (e.g., abort()).
        """
        self.install()
        fairy = self

        # Exception context lives on flask.g (request-scoped) rather than a
        # module-level dict, so concurrent requests don't stomp each other.
        from flask import got_request_exception, g

        def _on_exception(sender, exception, **kwargs):
            """Capture exception details before Flask clears them."""
            try:
                g._bugfairy_exc = exception
                g._bugfairy_tb = "".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                )
            # silent-failure-scan: allow exception-context-capture-must-not-throw
            except Exception:
                pass

        got_request_exception.connect(_on_exception, flask_app)

        @flask_app.after_request
        def _bugfairy_after_request(response):
            if response.status_code >= fairy.min_status_code:
                try:
                    from flask import request as flask_request

                    if fairy.should_report_http is not None:
                        try:
                            if not fairy.should_report_http(flask_request, response):
                                return response
                        except Exception:
                            pass

                    exc = getattr(g, "_bugfairy_exc", None)
                    tb_str = getattr(g, "_bugfairy_tb", "")

                    if exc:
                        title = f"{type(exc).__name__}: {str(exc)[:100]}"
                        exception_type = type(exc).__name__
                    else:
                        title = f"HTTP {response.status_code} on {flask_request.method} {flask_request.path}"
                        exception_type = ""

                    severity = "error" if response.status_code >= 500 else "warning"
                    metadata = {
                        "status_code": response.status_code,
                        "method": flask_request.method,
                        "path": flask_request.path,
                        "url": flask_request.url,
                        "remote_addr": flask_request.remote_addr,
                        "user_agent": str(flask_request.user_agent),
                    }

                    description = (
                        f"**{flask_request.method} {flask_request.path}** returned "
                        f"`{response.status_code}`"
                    )
                    if exc:
                        description += f"\n\n```\n{str(exc)[:500]}\n```"

                    fairy.report_async(
                        title=title,
                        description=description,
                        logs=tb_str[-5000:] if tb_str else "",
                        metadata=metadata,
                        severity=severity,
                        exception_type=exception_type,
                        stack_trace=tb_str,
                    )
                # silent-failure-scan: allow loop-prevention-during-self-report
                except Exception:
                    pass  # never break the app
            # g is auto-cleared when the request context tears down, no
            # explicit reset needed.
            return response

        log.info("bug-fairy Flask middleware installed for %s", self.app)

    def install_asgi(self, asgi_app):
        """Install middleware on any Starlette-based ASGI app.

        Works for FastAPI (which inherits from Starlette) and pure Starlette
        apps including Starlette-mounted FastMCP servers. Captures exceptions
        that escape all handlers (re-raises them) and reports any response
        whose status code is >= ``min_status_code``.

        Use this for FastAPI, Starlette, FastMCP, or any other ASGI framework
        built on Starlette. Use ``install_flask`` for Flask. Use ``install``
        alone for non-HTTP processes (workers, CLIs).
        """
        self.install()
        fairy = self

        # Uses BaseHTTPMiddleware via add_middleware() rather than the
        # FastAPI-specific .middleware("http") decorator, because Starlette
        # itself doesn't have that decorator (FastAPI subclasses Starlette
        # and adds it). Caught 2026-05-08 deploying Kyle-Rag's FastMCP
        # server: AttributeError: 'Starlette' object has no attribute
        # 'middleware'. add_middleware works for both Starlette and FastAPI.
        from starlette.middleware.base import BaseHTTPMiddleware

        async def _dispatch(request, call_next):
            try:
                response = await call_next(request)
            except Exception as exc:
                # Exception escaped all handlers — report and re-raise
                fairy.capture_exception(
                    exc,
                    metadata={
                        "method": request.method,
                        "path": str(request.url.path),
                        "url": str(request.url),
                    },
                )
                raise

            if response.status_code >= fairy.min_status_code:
                if fairy.should_report_http is not None:
                    try:
                        if not fairy.should_report_http(request, response):
                            return response
                    except Exception:
                        pass
                severity = "error" if response.status_code >= 500 else "warning"
                title = f"HTTP {response.status_code} on {request.method} {request.url.path}"
                metadata = {
                    "status_code": response.status_code,
                    "method": request.method,
                    "path": str(request.url.path),
                    "url": str(request.url),
                    "client": request.client.host if request.client else "",
                }
                fairy.report_async(
                    title=title,
                    description=f"**{request.method} {request.url.path}** returned `{response.status_code}`",
                    metadata=metadata,
                    severity=severity,
                )

            return response

        asgi_app.add_middleware(BaseHTTPMiddleware, dispatch=_dispatch)

        log.info("bug-fairy ASGI middleware installed for %s", self.app)

    def install_fastapi(self, fastapi_app):
        """Backward-compatible alias for ``install_asgi``.

        Kept so existing call sites (NPC-PM, Kyle-Rag etc.) keep working;
        new code should prefer ``install_asgi`` since the name is honest about
        what it covers (any Starlette-based ASGI app, not just FastAPI).
        """
        return self.install_asgi(fastapi_app)

    def uninstall(self):
        """Remove exception hooks and stop the flush thread."""
        if not self._installed:
            return
        sys.excepthook = self._original_excepthook
        self._running = False
        self.flush()
        self._installed = False

    def capture_exception(
        self, exc: BaseException, metadata: dict | None = None, severity: str = "error"
    ):
        """Report a caught exception to bug-fairy.

        Use this in except blocks for errors you handle but still want tracked:
            try:
                do_something()
            except SomeError as e:
                fairy.capture_exception(e)
                return fallback_response()
        """
        try:
            exc_type = type(exc)
            tb_str = "".join(
                traceback.format_exception(exc_type, exc, exc.__traceback__)
            )
            title = f"{exc_type.__name__}: {str(exc)[:100]}"
            description = f"Caught `{exc_type.__name__}` in **{self.app}**\n\n```\n{str(exc)}\n```"

            meta = {
                "python_version": sys.version,
                "platform": sys.platform,
                "pid": os.getpid(),
                "handled": True,
            }
            if metadata:
                meta.update(metadata)

            self.report_async(
                title=title,
                description=description,
                logs=tb_str[-5000:],
                metadata=meta,
                severity=severity,
                exception_type=exc_type.__name__,
                stack_trace=tb_str,
            )
        # silent-failure-scan: allow reporter-must-not-break-app
        except Exception:
            pass  # never let bug-fairy break the app

    def report(
        self,
        title: str,
        description: str,
        logs: str = "",
        metadata: dict | None = None,
        severity: str = "error",
        exception_type: str = "",
        stack_trace: str = "",
    ) -> dict | None:
        """Submit a bug report. Returns the response dict or None on failure."""
        payload = {
            "app": self.app,
            "title": title,
            "description": description,
            "logs": logs,
            "metadata": metadata or {},
            "severity": severity,
            "exception_type": exception_type,
            "stack_trace": stack_trace,
        }

        # Client-side dedup
        fp = self._fingerprint(exception_type, stack_trace, title)
        if self._is_duplicate(fp):
            log.debug("bug-fairy: skipping duplicate error: %s", title)
            return None

        return self._send(payload)

    def report_async(
        self,
        title: str,
        description: str,
        logs: str = "",
        metadata: dict | None = None,
        severity: str = "error",
        exception_type: str = "",
        stack_trace: str = "",
    ):
        """Queue a report for async delivery."""
        fp = self._fingerprint(exception_type, stack_trace, title)
        if self._is_duplicate(fp):
            return

        payload = {
            "app": self.app,
            "title": title,
            "description": description,
            "logs": logs,
            "metadata": metadata or {},
            "severity": severity,
            "exception_type": exception_type,
            "stack_trace": stack_trace,
        }
        self._queue.put(payload)

    def flush(self):
        """Send all queued reports immediately."""
        while not self._queue.empty():
            if self._is_rate_limited():
                return
            try:
                payload = self._queue.get_nowait()
                sent = self._send(payload)
                if sent is None and self._is_rate_limited():
                    self._queue.put(payload)
                    return
            except queue.Empty:
                break

    # -- Internal ---------------------------------------------------------------

    def _excepthook(self, exc_type, exc_value, exc_tb):
        """sys.excepthook replacement that reports to bug-fairy."""
        try:
            self._report_exception(exc_type, exc_value, exc_tb)
        # silent-failure-scan: allow reporter-must-not-crash-app
        except Exception:
            pass  # never let bug-fairy crash the app
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_tb)

    def _threading_excepthook(self, args):
        """threading.excepthook replacement."""
        try:
            self._report_exception(args.exc_type, args.exc_value, args.exc_traceback)
        # silent-failure-scan: allow reporter-must-not-crash-app
        except Exception:
            pass

    def _report_exception(self, exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        title = f"{exc_type.__name__}: {str(exc_value)[:100]}"
        description = f"Unhandled `{exc_type.__name__}` in **{self.app}**\n\n```\n{str(exc_value)}\n```"

        metadata = {
            "python_version": sys.version,
            "platform": sys.platform,
            "pid": os.getpid(),
        }

        screenshot_b64 = None
        if self.capture_screenshot:
            screenshot_b64 = self._try_screenshot()

        payload = {
            "app": self.app,
            "title": title,
            "description": description,
            "logs": tb_str[-5000:],
            "metadata": metadata,
            "severity": "error",
            "exception_type": exc_type.__name__,
            "stack_trace": tb_str,
        }
        if screenshot_b64:
            payload["screenshot"] = screenshot_b64

        fp = self._fingerprint(exc_type.__name__, tb_str, title)
        if not self._is_duplicate(fp):
            self._queue.put(payload)
            self.flush()

    def _try_screenshot(self) -> str | None:
        """Attempt to capture a screenshot as base64. Returns None if unavailable."""
        try:
            from PIL import ImageGrab
            import io
            import base64

            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        # silent-failure-scan: allow optional-screenshot-best-effort
        except Exception:
            return None

    def _fingerprint(self, exception_type: str, stack_trace: str, title: str) -> str:
        if exception_type and stack_trace:
            frames = stack_trace.strip().splitlines()
            top = frames[-2] if len(frames) >= 2 else frames[-1] if frames else ""
            key = f"{exception_type}|{top.strip()}"
        else:
            key = f"manual|{title}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _is_duplicate(self, fp: str) -> bool:
        now = time.time()
        with self._lock:
            expired = [
                k
                for k, t in self._recent_fingerprints.items()
                if now - t > self.dedup_window
            ]
            for k in expired:
                del self._recent_fingerprints[k]

            if fp in self._recent_fingerprints:
                return True
            self._recent_fingerprints[fp] = now
            return False

    def _is_rate_limited(self) -> bool:
        with self._lock:
            return time.time() < self._rate_limited_until

    def _enter_rate_limit_cooldown(self, seconds: float) -> None:
        cooldown = max(1.0, float(seconds))
        until = time.time() + cooldown
        with self._lock:
            self._rate_limited_until = max(self._rate_limited_until, until)

    def _flush_loop(self):
        while self._running:
            time.sleep(self.flush_interval)
            try:
                self.flush()
            # silent-failure-scan: allow flush-failure-must-not-kill-loop
            except Exception:
                pass

    def _send(self, payload: dict) -> dict | None:
        data = json.dumps(payload).encode()
        req = Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
                "User-Agent": "bug-fairy-client/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    cooldown = float(retry_after) if retry_after else self.rate_limit_cooldown
                except (TypeError, ValueError):
                    cooldown = self.rate_limit_cooldown
                self._enter_rate_limit_cooldown(cooldown)
                log.warning("bug-fairy: rate limited; cooling down for %.0fs", cooldown)
                return None
            log.warning("bug-fairy: request failed — %s", e)
            return None
        except URLError as e:
            log.warning("bug-fairy: request failed — %s", e)
            return None
