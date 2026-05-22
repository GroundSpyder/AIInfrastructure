"""SSH-based control plane for the two Windows Ollama hosts.

Kyle's directive 2026-05-21: cross-host control of MB / Kaydanski from a
Toshi container goes through SSH, not a Flask agent on each Windows host.
The agents "die silently and need rebooting." SSH just works — OpenSSH
server on Windows is a first-class Microsoft service.

See ../memory/feedback_ssh_over_windows_agents.md for the rule.

Reach pattern: the container has openssh-client installed; the host's
private key is mounted read-only at /root/.ssh/id_ed25519. Hostkey
acceptance is `accept-new` on first use — once cached, real verification
happens.

The two hosts:
  - mb        Kyle@192.168.4.33   (Master Blaster, RX 9070 XT, ROCm)
  - kaydanski Kaiden@kaydanskipc  (Kaydanski, RX 6600, Vulkan)

Each Windows SSH session lands in cmd.exe by default. We run commands
that work in cmd directly (curl, nssm, ollama) or wrap in
`powershell -NoProfile -Command "..."` when we need richer semantics.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import Dict

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HostSpec:
    alias: str
    label: str
    ssh_user: str
    ssh_addr: str
    ollama_url: str  # reachable from the Toshi container
    gpu_name: str
    backend: str  # ROCm | Vulkan | CPU


# Static host registry. If a host is added, the dashboard surface
# extends automatically — no per-route plumbing.
HOSTS: Dict[str, HostSpec] = {
    "mb": HostSpec(
        alias="mb",
        label="Master Blaster",
        ssh_user="Kyle",
        ssh_addr="192.168.4.33",
        ollama_url="http://192.168.4.33:11434",
        gpu_name="RX 9070 XT (16 GB)",
        backend="ROCm",
    ),
    "kaydanski": HostSpec(
        alias="kaydanski",
        label="Kaydanski",
        ssh_user="Kaiden",
        ssh_addr="kaydanskipc",
        ollama_url="http://kaydanskipc:11434",
        gpu_name="RX 6600 (8 GB)",
        backend="Vulkan",
    ),
}


class SSHError(Exception):
    """Raised when an SSH command exits non-zero or times out.

    Carries stdout + stderr so the caller can surface the actual error
    rather than swallowing it (per silent-failure-hunter rules — every
    failure path reaches the user with the real message).
    """

    def __init__(self, host: str, command: str, returncode: int, stdout: str, stderr: str):
        self.host = host
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"ssh {host} (rc={returncode}): {stderr.strip() or stdout.strip() or '<no output>'}")


def run_remote(host_alias: str, command: str, timeout: int = 30) -> str:
    """Run a command on the remote host via SSH and return stdout.

    Raises SSHError on non-zero exit or timeout. Stderr is captured and
    included in the error — we never silently discard it.
    """
    if host_alias not in HOSTS:
        raise ValueError(f"unknown host alias: {host_alias!r}")
    spec = HOSTS[host_alias]

    ssh_args = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=10",
        f"{spec.ssh_user}@{spec.ssh_addr}",
        command,
    ]
    log.info('ssh-exec host=%s cmd=%s', host_alias, command[:200])
    try:
        result = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise SSHError(host_alias, command, -1, e.stdout or "", f"ssh timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise SSHError(host_alias, command, -1, "", "ssh binary not found in container") from e

    if result.returncode != 0:
        raise SSHError(host_alias, command, result.returncode, result.stdout, result.stderr)
    return result.stdout


def run_powershell(host_alias: str, ps_script: str, timeout: int = 30) -> str:
    """Run a PowerShell script on the remote host via SSH.

    Wraps the script in `powershell -NoProfile -Command` and base64-encodes
    it so embedded quotes and special characters don't get mangled by
    cmd.exe (the default SSH login shell on Windows).
    """
    import base64
    encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
    cmd = f"powershell -NoProfile -EncodedCommand {encoded}"
    return run_remote(host_alias, cmd, timeout=timeout)


def get_nssm_env(host_alias: str, service: str = "OllamaService") -> Dict[str, str]:
    """Read NSSM AppEnvironmentExtra for a service.

    NSSM emits one KEY=VAL per line. Returns a dict. Empty if no env vars
    are set (NSSM returns a single empty line in that case).
    """
    out = run_remote(host_alias, f"nssm get {service} AppEnvironmentExtra")
    env: Dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip()
    return env


def set_nssm_env(host_alias: str, env: Dict[str, str], service: str = "OllamaService") -> None:
    """Replace AppEnvironmentExtra for a service.

    Each KEY=VAL is passed as a separate positional argument to nssm set —
    space-joined string silently corrupts the env block (2026-04-24
    Kaydanski landmine, root CLAUDE.md). Caller must call restart_service
    separately for the change to take effect.

    Goes through PowerShell (not cmd.exe) so values containing special
    characters like `&`, `|`, `"`, spaces don't get re-parsed by the
    remote shell. PowerShell single-quoted literals are non-interpolating
    — only `'` itself needs escaping (doubled). Caller MUST still
    validate keys/values at the API boundary against control characters.
    """
    if not env:
        run_remote(host_alias, f"nssm set {service} AppEnvironmentExtra")
        return

    def ps_lit(s: str) -> str:
        # Reject control chars early — they'd break the PS literal
        # boundary and aren't valid env-var content anyway.
        if any(ord(c) < 0x20 for c in s):
            raise ValueError(f"control character in env entry: {s!r}")
        return "'" + s.replace("'", "''") + "'"

    pairs_array = ",".join(ps_lit(f"{k}={v}") for k, v in env.items())
    # @-splat the array so nssm sees each KEY=VAL as its own argv slot.
    script = f"$pairs = @({pairs_array}); & nssm set {service} AppEnvironmentExtra @pairs"
    run_powershell(host_alias, script)


def restart_service(host_alias: str, service: str = "OllamaService") -> str:
    """Restart a Windows service via NSSM. Returns the combined output."""
    return run_remote(host_alias, f"nssm restart {service}", timeout=60)


_FILE_MISSING_SENTINEL = "__FLEET_FILE_MISSING__"


def _validate_remote_path(path: str) -> None:
    """Guard the PS single-quoted literal interpolation site.

    PowerShell single-quoted strings don't interpret `$` or backticks,
    but `'` ends the string, and `\\r`/`\\n` would break the script
    boundary. Reject those plus other control chars.
    """
    if not path:
        raise ValueError("empty remote path")
    if "'" in path:
        raise ValueError("remote path may not contain single quotes")
    if any(ord(c) < 0x20 for c in path):
        raise ValueError("remote path may not contain control characters")


def read_remote_file(host_alias: str, path: str) -> str | None:
    """Read a UTF-8 text file from the remote host.

    Returns the file contents, or None if the file doesn't exist. Other
    failures (permission denied, SSH unreachable, etc.) raise SSHError
    so the caller can distinguish "file doesn't exist yet" from "real
    error" without resorting to string-matching stderr.
    """
    _validate_remote_path(path)
    script = (
        f"if (Test-Path -LiteralPath '{path}') {{ "
        f"Get-Content -Raw -LiteralPath '{path}' "
        f"}} else {{ Write-Output '{_FILE_MISSING_SENTINEL}' }}"
    )
    out = run_powershell(host_alias, script)
    if out.strip() == _FILE_MISSING_SENTINEL:
        return None
    return out


def write_remote_file(host_alias: str, path: str, content: str) -> None:
    """Write a UTF-8 text file on the remote host, creating parent dirs.

    Uses [System.IO.File]::WriteAllBytes with a base64-decoded byte
    array to avoid PowerShell's default UTF-16-with-BOM output, which
    would break downstream JSON parsers. Ensures the parent directory
    exists first so first-ever writes don't fail.
    """
    _validate_remote_path(path)
    import base64
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    script = (
        f"$dir = Split-Path -Parent -LiteralPath '{path}';"
        f"if ($dir -and -not (Test-Path -LiteralPath $dir)) {{ "
        f"New-Item -ItemType Directory -Path $dir -Force | Out-Null }};"
        f"$bytes = [System.Convert]::FromBase64String('{encoded}');"
        f"[System.IO.File]::WriteAllBytes('{path}', $bytes)"
    )
    run_powershell(host_alias, script)
