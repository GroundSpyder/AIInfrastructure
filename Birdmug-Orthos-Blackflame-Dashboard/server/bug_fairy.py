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
import re
import sys
import threading
import time
import traceback
from collections.abc import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

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
        ignore_status_codes: Iterable[int] = (404, 405),
        max_queue: int = 256,
    ):
        self.api_key = api_key
        self.app = app
        # No key means no destination. Reporting stays a no-op instead of
        # POSTing every captured error and collecting a 401 for each -- which
        # is what a Doppler-less deploy or a test run did, silently, forever.
        self.enabled = bool(api_key and api_key.strip())
        self.url = url
        self.flush_interval = flush_interval
        self.dedup_window = dedup_window
        self.capture_screenshot = capture_screenshot
        self.min_status_code = min_status_code
        self.max_queue = max_queue
        # 404 and 405 are NOT reported: "there is no such route" is a
        # statement about the caller, not about this service. Measured on the
        # live Bug Fairy database 2026-09-04: of 1788 reports, 995 were 4xx
        # and 611 of those were 404/405, with user agents Applebot, Googlebot
        # and scanners walking /.env and /wp-login.php. Not one was a defect,
        # and together they were a third of the database -- which is how a
        # real 5xx gets buried.
        #
        # The threshold stays at 400 rather than moving to 500, because every
        # OTHER 4xx in that sample was real signal: the Squire htmx json-enc
        # mismatch surfaced only as 422 on every form for weeks, 87 reports
        # were `400 POST /mcp/` from the Kyle-Rag MCP session bug, and 401
        # (235 of them) is how JWT drift announces itself.
        #
        # A 404 CAN mean a real broken link to our own asset, but a reporter
        # inside an app cannot tell that from a scanner probe without
        # app-specific knowledge -- so that check belongs in the app, where it
        # can be exhaustive instead of incidental. Pass ignore_status_codes=()
        # to opt back in.
        self.ignore_status_codes = frozenset(ignore_status_codes)

        # BOUNDED. An unbounded queue plus a per-path fingerprint (see
        # _fingerprint) meant a vulnerability scanner walking a thousand URLs
        # produced a thousand queued reports, none of them deduped, held in
        # memory until the flusher drained them one blocking POST at a time.
        # The reporter is not allowed to be the thing that OOMs the process.
        self._queue: queue.Queue = queue.Queue(maxsize=self.max_queue)
        self._dropped = 0
        self._recent_fingerprints: dict[str, float] = {}
        self._lock = threading.Lock()
        self._installed = False
        self._original_excepthook = None
        self._original_threading_excepthook = None
        self._flask_exc_receiver = None
        self._flask_app = None
        self._flush_thread = None
        self._running = False

    def should_report_status(self, status_code: int) -> bool:
        """Whether an error RESPONSE with this status is worth a report.

        Exceptions are always reported regardless of the status they produce;
        this governs only the response-code middleware. See
        ignore_status_codes in __init__ for the data behind the default.
        """
        return (
            status_code >= self.min_status_code
            and status_code not in self.ignore_status_codes
        )

    def install(self):
        """Hook into sys.excepthook to automatically capture unhandled exceptions."""
        if self._installed:
            return

        self._original_excepthook = sys.excepthook
        sys.excepthook = self._excepthook

        try:
            # Keep the hook we are replacing and call it afterwards. Replacing
            # it outright suppressed the interpreter's own stderr traceback, so
            # an exception escaping a thread produced NO record anywhere once
            # the Bug Fairy POST itself was failing (a stale API key 401ing was
            # exactly that situation).
            self._original_threading_excepthook = threading.excepthook
            threading.excepthook = self._threading_excepthook
        # silent-failure-scan: allow Python < 3.8 has no threading.excepthook; nothing to chain
        except AttributeError:
            self._original_threading_excepthook = None

        self._running = True
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        atexit.register(self.flush)

        self._installed = True
        if self.enabled:
            log.info("bug-fairy installed for %s", self.app)
        else:
            # Announce the no-op at startup. Logging a clean install while
            # holding no API key is how a Doppler-less deploy reported
            # nothing for months and looked correctly wired the whole time.
            log.warning(
                "bug-fairy installed for %s but DISABLED: no API key. "
                "Errors will be logged but not reported.",
                self.app,
            )

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

        # connect() defaults to a WEAK reference to the receiver, and
        # _on_exception is a local function whose last strong reference dies
        # when this method returns -- measured: zero receivers registered
        # right after install_flask() returns, no gc.collect() needed. Every
        # Flask exception report therefore shipped with an empty
        # exception_type and stack_trace, which is why they were
        # undiagnosable: 49 of the 187 real-exception reports in the live
        # database have neither (PMA 6/6, snoop-worker 28/28).
        #
        # Both halves matter: weak=False stops blinker dropping it, and the
        # instance attribute keeps a strong reference alive for the object's
        # lifetime so this cannot regress if the connect call is edited back.
        self._flask_exc_receiver = _on_exception
        self._flask_app = flask_app
        got_request_exception.connect(_on_exception, flask_app, weak=False)

        @flask_app.after_request
        def _bugfairy_after_request(response):
            if fairy.should_report_status(response.status_code):
                try:
                    from flask import request as flask_request

                    # POP, not getattr: g is APP-context scoped and Flask
                    # REUSES an already-pushed context, so a context left
                    # behind was read again by the next request and filed
                    # one endpoint's traceback against another's response.
                    exc = g.pop("_bugfairy_exc", None)
                    tb_str = g.pop("_bugfairy_tb", "")

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
                    # Must never break the app -- but must not vanish either.
                    log.warning(
                        "bug-fairy: failed to report an error response", exc_info=True
                    )
            # g is auto-cleared when the request context tears down, no
            # explicit reset needed.
            else:
                # Below the reporting threshold. Drop any captured context
                # so it cannot outlive this request: an app context that
                # wraps several requests would otherwise carry it forward.
                g.pop("_bugfairy_exc", None)
                g.pop("_bugfairy_tb", "")
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

            if fairy.should_report_status(response.status_code):
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
        """Put back everything install() and install_flask() replaced.

        Restoring only sys.excepthook was how install/uninstall/install
        made the reporter chain into itself: the second install captured
        the hook the FIRST install had left in place -- its own -- and one
        thread exception then recursed until RecursionError, logging a full
        traceback on every level. The atexit and blinker cleanup is here for
        the same reason: without it every instance ever created is pinned
        alive by the atexit registry, along with its queue.
        """
        if not self._installed:
            return
        sys.excepthook = self._original_excepthook
        if self._original_threading_excepthook is not None:
            threading.excepthook = self._original_threading_excepthook
            self._original_threading_excepthook = None
        receiver = getattr(self, "_flask_exc_receiver", None)
        if receiver is not None:
            try:
                from flask import got_request_exception

                got_request_exception.disconnect(receiver, self._flask_app)
            except Exception:
                log.warning(
                    "bug-fairy: could not disconnect the Flask receiver", exc_info=True
                )
            self._flask_exc_receiver = None
            self._flask_app = None
        try:
            atexit.unregister(self.flush)
        except Exception:
            log.warning(
                "bug-fairy: could not unregister the atexit flush", exc_info=True
            )
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
            # Never break the app -- but this is the call an app makes when it
            # explicitly WANTS something reported, so it must not vanish.
            log.warning("bug-fairy: capture_exception failed", exc_info=True)

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
        if not self._enqueue(payload):
            # Release the fingerprint. Recording it before the payload was
            # accepted meant the burst that filled the queue also blinded
            # dedup to those errors for the whole window, so the first
            # report AFTER the queue drained was dropped as a duplicate of
            # one that was never sent.
            self._forget_fingerprint(fp)

    def _enqueue(self, payload: dict) -> bool:
        """Queue a report, or drop it loudly if the queue is full.

        A full queue means reports are arriving faster than they can be
        delivered, which is exactly when the old unbounded version grew
        without limit -- so the payload is dropped and counted, and the count
        is logged once per hundred rather than turning a flood of reports
        into a flood of log lines.
        """
        try:
            self._queue.put_nowait(payload)
            return True
        except queue.Full:
            # Under the lock: this counter is the only evidence drops
            # happened, and a full queue is by definition the moment several
            # threads are incrementing it at once.
            with self._lock:
                self._dropped += 1
                dropped = self._dropped
            if dropped % 100 == 1:
                log.warning(
                    "bug-fairy: report queue full (%d), dropped %d report(s) so far",
                    self.max_queue,
                    dropped,
                )
            return False

    def flush(self):
        """Send all queued reports immediately."""
        while not self._queue.empty():
            try:
                payload = self._queue.get_nowait()
                self._send(payload)
            except queue.Empty:
                break

    # -- Internal ---------------------------------------------------------------

    def _excepthook(self, exc_type, exc_value, exc_tb):
        """sys.excepthook replacement that reports to bug-fairy."""
        try:
            self._report_exception(exc_type, exc_value, exc_tb)
        # silent-failure-scan: allow reporter-must-not-crash-app
        # silent-failure-scan: allow the original excepthook below still prints the traceback
        except Exception:
            pass
        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_tb)

    def _threading_excepthook(self, args):
        """threading.excepthook replacement."""
        try:
            self._report_exception(args.exc_type, args.exc_value, args.exc_traceback)
        # silent-failure-scan: allow the log.error below is unconditional and carries the record
        except Exception:
            pass

        # Log it and hand it back to whoever we displaced, so the record
        # survives even when the report does not.
        log.error(
            "Unhandled exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        if self._original_threading_excepthook is not None:
            self._original_threading_excepthook(args)

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
            self._enqueue(payload)
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

    # Titles the Flask/ASGI middleware generates for a response with no
    # exception, e.g. "HTTP 404 on GET /wp-login.php".
    _HTTP_TITLE_RE = re.compile(r"^HTTP (\d{3}) on ([A-Z]+) ")

    def _fingerprint(self, exception_type: str, stack_trace: str, title: str) -> str:
        if exception_type and stack_trace:
            frames = stack_trace.strip().splitlines()
            top = frames[-2] if len(frames) >= 2 else frames[-1] if frames else ""
            key = f"{exception_type}|{top.strip()}"
        else:
            # An error RESPONSE with no exception is fingerprinted on status
            # and method, NOT on the path -- the path made every scanner probe
            # unique, so dedup never applied and a thousand 404s for a thousand
            # made-up URLs became a thousand reports, which both filled the
            # queue and buried any real 5xx. The path is still in the report
            # metadata, so the first one in each dedup window carries it; what
            # is lost is only the nine-hundred-and-ninety-nine repeats.
            http = self._HTTP_TITLE_RE.match(title)
            # Only 4xx loses its path. A 5xx keeps it, because the path IS
            # the diagnosis there and the ASGI middleware never passes an
            # exception_type -- so every one of its error reports lands in
            # this branch, and stripping the path collapsed two unrelated
            # 500s into one dedup window and reported only the first.
            if http and int(http.group(1)) >= 500:
                http = None
            key = f"http|{http.group(1)}|{http.group(2)}" if http else f"manual|{title}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def _forget_fingerprint(self, fp: str) -> None:
        """Undo _is_duplicate's record, for a report that was never queued."""
        with self._lock:
            self._recent_fingerprints.pop(fp, None)

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

    def _flush_loop(self):
        while self._running:
            time.sleep(self.flush_interval)
            try:
                self.flush()
            # silent-failure-scan: allow flush-failure-must-not-kill-loop
            except Exception:
                # Keep looping -- one bad flush must not end reporting for the
                # life of the process -- but say so. Swallowed, a permanently
                # broken reporter looked exactly like a quiet one.
                log.warning("bug-fairy: flush failed, will retry", exc_info=True)

    def _send(self, payload: dict) -> dict | None:
        if not self.enabled:
            return
        try:
            data = json.dumps(payload).encode()
        except (TypeError, ValueError) as e:
            # Unserialisable metadata -- a datetime, a Decimal, a model
            # object -- used to raise straight out of report() and into the
            # caller's except block. And only where an API key is set, since
            # the enabled gate above returns first, so dev and CI never saw
            # it and production did.
            log.warning("bug-fairy: report payload is not JSON-serialisable: %s", e)
            return None
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
        except URLError as e:
            log.warning("bug-fairy: request failed — %s", e)
            return None
        except Exception as e:
            # NOT just URLError: a proxy's HTML error page raises
            # JSONDecodeError, and a read-phase timeout raises TimeoutError,
            # which is not a URLError subclass. Either one escaping here killed
            # the flush thread and every report after it.
            log.warning("bug-fairy: report POST failed: %s: %s", type(e).__name__, e)
