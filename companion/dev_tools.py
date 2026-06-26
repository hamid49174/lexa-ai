"""Lexa AI — Developer Tools (Phase 22)
Git-Integration, Docker-Kontrolle, API-Tester, Log-Analyse,
Server-Monitor, Code-Snippets-Erweiterung
"""

import json
import logging
import subprocess
import socket
import re
import ipaddress
import urllib.request
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from backend.i18n import t

logger = logging.getLogger("lexa.dev_tools")

_BLOCKED_HTTP_HOSTS: frozenset[str] = frozenset({
    "169.254.169.254",
    "169.254.169.253",
    "metadata.google.internal",
    "metadata.google",
    "100.100.100.200",
    "169.254.0.1",
})
_LOCAL_HTTP_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
})


def _is_dangerous_ip_address(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _normalize_public_http_url(url: str) -> tuple[str, str | None]:
    url = (url or "").strip()
    if not url:
        return "", "URL erforderlich."
    if not url.startswith(("http://", "https://")):
        if "://" in url:
            return "", "Nur http:// und https:// URLs erlaubt."
        url = "https://" + url

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not hostname:
        return "", "Nur http:// und https:// URLs erlaubt."

    if hostname in _BLOCKED_HTTP_HOSTS:
        return "", t("security.blockedInternal", host=hostname)
    if hostname in _LOCAL_HTTP_HOSTNAMES or hostname.endswith(".localhost"):
        return "", t("security.blockedInternal", host=hostname)

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return url, None

    if _is_dangerous_ip_address(addr):
        return "", t("security.blockedSsrf", ip=addr)
    return url, None


class _SafePublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        normalized_url, url_error = _normalize_public_http_url(newurl)
        if url_error:
            raise ValueError(url_error)

        parsed = urlparse(normalized_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        resolved_error = _resolved_public_host_error(parsed.hostname or "", port)
        if resolved_error:
            raise ValueError(resolved_error)

        return super().redirect_request(req, fp, code, msg, headers, normalized_url)


def _validate_repo_path(path: str) -> str | None:
    """Returns error message if path is invalid, None if OK."""
    if not path:
        return "Repository-Pfad erforderlich."
    p = Path(path)
    if not p.exists():
        return f"Verzeichnis nicht gefunden: {path}"
    if not p.is_dir():
        return f"Kein Verzeichnis: {path}"
    # Block system directories
    path_lower = str(p.resolve()).lower()
    if any(b in path_lower for b in ["system32", "syswow64", "windows\\system"]):
        return t("security.blockedSystemDir")
    return None


# ══════════════════════════════════════════════════════
#  GIT INTEGRATION
# ══════════════════════════════════════════════════════

def git_status(repo_path: str = "") -> dict:
    """Git-Status eines Repositories anzeigen."""
    err = _validate_repo_path(repo_path)
    if err:
        return {"error": err}
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "Git-Status fehlgeschlagen."}
        lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        branch = ""
        modified = []
        untracked = []
        staged = []

        for line in lines:
            if len(line) < 2:
                continue
            if line.startswith("##"):
                branch = line[3:].split("...")[0] if "..." in line else line[3:]
                continue
            if line.startswith("??"):
                untracked.append(line[3:])
                continue
            # Porcelain format: XY <path> — X = index/staged, Y = working tree.
            # A file can be both staged AND modified (e.g. "MM").
            index_status = line[0]
            worktree_status = line[1]
            if index_status in ("M", "A", "D", "R", "C"):
                staged.append(line.strip())
            if worktree_status in ("M", "D"):
                modified.append(line.strip())

        return {
            "branch": branch,
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
            "clean": len(modified) == 0 and len(staged) == 0 and len(untracked) == 0,
            "total_changes": len(modified) + len(staged) + len(untracked),
        }
    except FileNotFoundError:
        return {"error": "Git ist nicht installiert."}
    except Exception as e:
        return {"error": str(e)}


def git_log(repo_path: str = "", count: int = 10) -> list[dict]:
    """Git-Log anzeigen (letzte N Commits)."""
    err = _validate_repo_path(repo_path)
    if err:
        return [{"error": err}]
    count = max(1, min(50, count))
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={count}", "--pretty=format:%H|%h|%an|%ae|%ar|%s"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        if result.returncode != 0:
            return [{"error": result.stderr.strip() or "Git-Log fehlgeschlagen."}]
        commits = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 5)
                if len(parts) == 6:
                    commits.append({
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "author": parts[2],
                        "email": parts[3],
                        "date": parts[4],
                        "message": parts[5],
                    })
        return commits
    except Exception as e:
        return [{"error": str(e)}]


def git_diff(repo_path: str = "", staged: bool = False, full: bool = False) -> str:
    """Git-Diff anzeigen (staged oder unstaged).

    Shows both stat summary AND actual code diff (truncated to 5000 chars).
    full=True returns only code diff without stat.
    """
    err = _validate_repo_path(repo_path)
    if err:
        return err
    try:
        # Get stat summary
        stat_cmd = ["git", "diff"]
        if staged:
            stat_cmd.append("--cached")
        stat_cmd.append("--stat")

        stat_result = subprocess.run(
            stat_cmd, capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        stat_output = stat_result.stdout.strip()

        # Get actual code diff
        diff_cmd = ["git", "diff"]
        if staged:
            diff_cmd.append("--cached")

        diff_result = subprocess.run(
            diff_cmd, capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        diff_output = diff_result.stdout.strip()

        if not stat_output and not diff_output:
            return t("error.noChanges")

        if full:
            if diff_output:
                return diff_output[:10000]
            # git diff (without --stat) emits no text diff for pure binary/mode/rename
            # changes — fall back to the stat summary so we don't claim "no changes".
            if stat_output:
                return stat_output
            return t("error.noChanges")

        # Combine stat + truncated diff
        parts = []
        if stat_output:
            parts.append(stat_output)
        if diff_output:
            truncated = diff_output[:5000]
            if len(diff_output) > 5000:
                truncated += f"\n\n... ({len(diff_output) - 5000} weitere Zeichen abgeschnitten)"
            parts.append(truncated)

        return "\n\n".join(parts)
    except Exception as e:
        return t("error.generic", error=str(e))


def git_branch_list(repo_path: str = "") -> dict:
    """Alle Git-Branches auflisten."""
    err = _validate_repo_path(repo_path)
    if err:
        return {"error": err}
    try:
        result = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)|%(objectname:short)|%(subject)"],
            capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        # Get current branch
        curr = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
            cwd=repo_path,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "Git-Branch-Liste fehlgeschlagen."}
        current = curr.stdout.strip()

        branches = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 2)
                branches.append({
                    "name": parts[0],
                    "hash": parts[1] if len(parts) > 1 else "",
                    "message": parts[2] if len(parts) > 2 else "",
                    "current": parts[0] == current,
                })
        return {"current": current, "branches": branches}
    except Exception as e:
        return {"error": str(e)}


def git_commit(repo_path: str = "", message: str = "") -> str:
    """Git-Commit (alle staged Änderungen)."""
    err = _validate_repo_path(repo_path)
    if err:
        return err
    if not message:
        return "Commit-Message erforderlich."
    message = message[:500]
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True, text=True, timeout=15,
            cwd=repo_path,
        )
        if result.returncode == 0:
            return f"Commit erstellt: {message}\n{result.stdout.strip()}"
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def git_add(repo_path: str = "", files: str = ".") -> str:
    """Dateien zum Git-Staging hinzufügen."""
    err = _validate_repo_path(repo_path)
    if err:
        return err
    files = (files or "").strip() or "."
    if files.startswith("-"):
        return "Ungültige Dateiangabe: darf nicht mit '-' beginnen."
    try:
        result = subprocess.run(
            # "--" ensures the value is treated as a pathspec, never as a git option.
            ["git", "add", "--", files],
            capture_output=True, text=True, timeout=10,
            cwd=repo_path,
        )
        if result.returncode == 0:
            return f"Dateien gestaged: {files}"
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def git_pull(repo_path: str = "") -> str:
    """Git Pull with merge conflict detection and actionable error messages.

    Detects: merge conflicts, diverged branches, uncommitted changes blocking pull,
    authentication failures, and network errors.
    """
    err = _validate_repo_path(repo_path)
    if err:
        return err
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, timeout=60,
            cwd=repo_path,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        combined = f"{stdout}\n{stderr}".strip()

        if result.returncode == 0:
            return stdout or "Pull abgeschlossen — bereits aktuell."

        # Detect specific failure types
        lower = combined.lower()

        if "conflict" in lower or "merge conflict" in lower or "CONFLICT" in combined:
            # List conflicted files
            conf_result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                capture_output=True, text=True, timeout=5, cwd=repo_path,
            )
            files = conf_result.stdout.strip()
            msg = "Merge-Konflikt! Folgende Dateien haben Konflikte:\n"
            if files:
                msg += files + "\n"
            msg += "\nOptionen:\n"
            msg += "1. Konflikte manuell lösen, dann: git add . && git commit\n"
            msg += "2. Pull abbrechen: git merge --abort"
            return msg

        if "uncommitted changes" in lower or "local changes" in lower:
            return ("Pull fehlgeschlagen: Ungespeicherte lokale Änderungen.\n"
                    "Optionen:\n"
                    "1. Änderungen committen: git add . && git commit -m 'WIP'\n"
                    "2. Änderungen stashen: git stash && git pull && git stash pop")

        if "divergent branches" in lower or "diverged" in lower:
            return ("Branches sind divergiert.\n"
                    "Optionen:\n"
                    "1. Rebase: git pull --rebase\n"
                    "2. Merge: git pull --no-rebase")

        if "authentication" in lower or "403" in lower or "401" in lower:
            return "Pull fehlgeschlagen: Authentifizierung fehlgeschlagen. Git-Credentials prüfen."

        if "could not resolve" in lower or "network" in lower:
            return "Pull fehlgeschlagen: Netzwerk-Fehler. Internetverbindung prüfen."

        return combined or "Pull fehlgeschlagen (unbekannter Fehler)."
    except subprocess.TimeoutExpired:
        return "Pull-Timeout (60s). Möglicherweise große Änderungen oder langsame Verbindung."
    except Exception as e:
        return t("error.generic", error=str(e))


def git_push(repo_path: str = "") -> str:
    """Git Push with rejection detection and actionable error messages.

    Detects: push rejections (non-fast-forward), no upstream, authentication,
    protected branch blocks, and large file blocks.
    """
    err = _validate_repo_path(repo_path)
    if err:
        return err
    try:
        result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, timeout=60,
            cwd=repo_path,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        combined = f"{stdout}\n{stderr}".strip()

        if result.returncode == 0:
            # Parse useful info from stderr (git push writes progress to stderr)
            if "Everything up-to-date" in combined:
                return "Push: Bereits aktuell — keine neuen Commits."
            return combined or "Push erfolgreich abgeschlossen."

        lower = combined.lower()

        if "non-fast-forward" in lower or "rejected" in lower or "fetch first" in lower:
            return ("Push abgelehnt: Remote hat neuere Commits.\n"
                    "Optionen:\n"
                    "1. Erst pullen: git pull && git push\n"
                    "2. Rebase: git pull --rebase && git push\n"
                    "⚠️ NICHT git push --force (überschreibt Remote-Änderungen)")

        if "no upstream" in lower or "set-upstream" in lower or "no such remote" in lower:
            # Get current branch name
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=5, cwd=repo_path,
            )
            branch = branch_result.stdout.strip() or "BRANCH"
            return f"Kein Upstream-Branch gesetzt.\nLösung: git push -u origin {branch}"

        if "authentication" in lower or "403" in lower or "401" in lower:
            return "Push fehlgeschlagen: Authentifizierung fehlgeschlagen. Git-Credentials prüfen."

        if "protected branch" in lower:
            return "Push fehlgeschlagen: Branch ist geschützt. Pull Request erstellen statt direkt pushen."

        if "large file" in lower or "exceeded" in lower:
            return ("Push fehlgeschlagen: Datei zu groß.\n"
                    "Lösung: git lfs track '*.EXTENSION' oder große Datei aus History entfernen.")

        return combined or "Push fehlgeschlagen (unbekannter Fehler)."
    except subprocess.TimeoutExpired:
        return "Push-Timeout (60s). Große Dateien oder langsame Verbindung."
    except Exception as e:
        return t("error.generic", error=str(e))


# ══════════════════════════════════════════════════════
#  DOCKER KONTROLLE
# ══════════════════════════════════════════════════════

def docker_ps(all_containers: bool = False) -> list[dict]:
    """Laufende Docker-Container auflisten."""
    try:
        cmd = ["docker", "ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"]
        if all_containers:
            cmd.insert(2, "-a")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return [{"error": result.stderr.strip() or "Docker-Daemon nicht erreichbar."}]
        containers = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 4)
                containers.append({
                    "id": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3],
                    "ports": parts[4] if len(parts) > 4 else "",
                })
        return containers
    except FileNotFoundError:
        return [{"error": "Docker ist nicht installiert."}]
    except Exception as e:
        return [{"error": str(e)}]


def docker_images() -> list[dict]:
    """Docker-Images auflisten."""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}|{{.Tag}}|{{.ID}}|{{.Size}}|{{.CreatedSince}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return [{"error": result.stderr.strip() or "Docker-Daemon nicht erreichbar."}]
        images = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 4)
                images.append({
                    "repository": parts[0],
                    "tag": parts[1],
                    "id": parts[2],
                    "size": parts[3],
                    "created": parts[4] if len(parts) > 4 else "",
                })
        return images
    except FileNotFoundError:
        return [{"error": "Docker ist nicht installiert."}]
    except Exception as e:
        return [{"error": str(e)}]


def docker_start(container: str = "") -> str:
    """Docker-Container starten."""
    if not container:
        return "Container-Name oder ID erforderlich."
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$', container):
        return t("validation.invalidContainerName")
    try:
        result = subprocess.run(
            ["docker", "start", container],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return f"Container '{container}' gestartet."
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def docker_stop(container: str = "") -> str:
    """Docker-Container stoppen."""
    if not container:
        return "Container-Name oder ID erforderlich."
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$', container):
        return t("validation.invalidContainerName")
    try:
        result = subprocess.run(
            ["docker", "stop", container],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return f"Container '{container}' gestoppt."
        return t("error.stderr", stderr=result.stderr.strip())
    except Exception as e:
        return t("error.generic", error=str(e))


def docker_logs(container: str = "", tail: int = 50) -> str:
    """Docker-Container-Logs anzeigen."""
    if not container:
        return "Container-Name oder ID erforderlich."
    if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$', container):
        return t("validation.invalidContainerName")
    tail = max(10, min(200, tail))
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), container],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output[-3000:] if len(output) > 3000 else output or t("system.noLogs")
    except Exception as e:
        return t("error.generic", error=str(e))


def docker_stats() -> list[dict]:
    """Docker-Container Ressourcenverbrauch."""
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.PIDs}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return [{"error": result.stderr.strip() or "Docker-Daemon nicht erreichbar."}]
        stats = []
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                parts = line.split("|", 4)
                stats.append({
                    "name": parts[0],
                    "cpu": parts[1],
                    "memory": parts[2],
                    "network": parts[3],
                    "pids": parts[4] if len(parts) > 4 else "",
                })
        return stats
    except Exception as e:
        return [{"error": str(e)}]


# ══════════════════════════════════════════════════════
#  API-TESTER (HTTP Requests)
# ══════════════════════════════════════════════════════

def http_request(url: str = "", method: str = "GET", headers: str = "", body: str = "", timeout: int = 10) -> dict:
    """HTTP-Request senden (API-Tester)."""
    url, url_error = _normalize_public_http_url(url)
    if url_error:
        return {"error": url_error}

    method = (method or "GET").strip().upper()
    allowed_methods = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
    if method not in allowed_methods:
        return {"error": f"HTTP-Methode '{method}' nicht erlaubt. Erlaubt: {', '.join(sorted(allowed_methods))}"}

    timeout = max(3, min(30, timeout))

    try:
        import urllib.request
        import urllib.error

        req = urllib.request.Request(url, method=method)

        # Parse custom headers
        if headers:
            try:
                header_dict = json.loads(headers)
                if not isinstance(header_dict, dict):
                    raise ValueError("Headers must be a JSON object")
                for k, v in header_dict.items():
                    req.add_header(k, v)
            except json.JSONDecodeError:
                # Try key: value format
                for line in headers.split("\n"):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        req.add_header(k.strip(), v.strip())

        # Add body for POST/PUT
        if body and method in ("POST", "PUT", "PATCH"):
            req.data = body.encode("utf-8")
            if "Content-Type" not in (headers or ""):
                req.add_header("Content-Type", "application/json")

        try:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname or ""
            # Resolve and block private/loopback/link-local IPs
            try:
                resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for _, _, _, _, addr in resolved:
                    ip = ipaddress.ip_address(addr[0])
                    if _is_dangerous_ip_address(ip):
                        return {"error": t("security.blockedSsrf", ip=ip)}
            except socket.gaierror:
                pass  # Let the actual request fail naturally
        except Exception:
            pass

        start = datetime.now()
        opener = urllib.request.build_opener(_SafePublicRedirectHandler)
        response = opener.open(req, timeout=timeout)
        elapsed = (datetime.now() - start).total_seconds()

        resp_body = response.read(500_000).decode("utf-8", errors="replace")
        resp_headers = dict(response.headers)

        # Try to parse as JSON
        try:
            resp_json = json.loads(resp_body)
            resp_body_display = json.dumps(resp_json, indent=2, ensure_ascii=False)[:3000]
        except json.JSONDecodeError:
            resp_body_display = resp_body[:3000]

        return {
            "status_code": response.status,
            "reason": response.reason,
            "elapsed_sec": round(elapsed, 3),
            "headers": resp_headers,
            "body": resp_body_display,
            "body_length": len(resp_body),
        }

    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", errors="replace")[:2000]
        return {
            "status_code": e.code,
            "reason": e.reason,
            "error": True,
            "body": resp_body,
        }
    except urllib.error.URLError as e:
        return {"error": t("error.connectionError", error=str(e.reason))}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════
#  LOG-ANALYSE
# ══════════════════════════════════════════════════════

def log_analyze(path: str = "", lines: int = 100, pattern: str = "", level: str = "") -> dict:
    """Log-Datei analysieren (letzte N Zeilen, optional filtern)."""
    if not path:
        return {"error": "Log-Pfad erforderlich."}

    log_path = Path(path)
    if not log_path.exists():
        return {"error": f"Datei nicht gefunden: {path}"}

    # Prevent reading sensitive system files
    path_str = str(log_path.resolve())
    BLOCKED_LOG_PATHS = ["system32", "syswow64", "windows\\system", "/etc/shadow", "/etc/passwd"]
    if any(b in path_str.lower() for b in BLOCKED_LOG_PATHS):
        return {"error": t("security.blockedSystemPath")}
    # Only allow known log file extensions
    if log_path.suffix.lower() not in {".log", ".txt", ".out", ".err", ".json", ".csv", ""}:
        return {"error": f"Dateityp '{log_path.suffix}' nicht erlaubt."}

    try:
        lines = max(10, min(500, lines))

        # Read last N lines efficiently
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        tail = all_lines[-lines:]

        # Filter by level
        if level:
            level_upper = level.upper()
            tail = [line for line in tail if level_upper in line.upper()]

        # Filter by pattern
        if pattern:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
                tail = [line for line in tail if regex.search(line)]
            except re.error:
                tail = [line for line in tail if pattern.lower() in line.lower()]

        # Count log levels
        level_counts = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0}
        for line in all_lines[-500:]:
            upper = line.upper()
            for lvl in level_counts:
                if lvl in upper:
                    level_counts[lvl] += 1

        return {
            "file": str(log_path),
            "total_lines": len(all_lines),
            "shown_lines": len(tail),
            "level_counts": level_counts,
            "content": "".join(tail)[-5000:],
        }
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════
#  SERVER-MONITOR
# ══════════════════════════════════════════════════════

def _server_target_from_url(url: str) -> tuple[str, int, str, str | None]:
    normalized_url, url_error = _normalize_public_http_url(url)
    if url_error:
        return "", 0, "", url_error

    parsed = urlparse(normalized_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port, normalized_url, None


def _resolved_public_host_error(host: str, port: int) -> str | None:
    try:
        resolved = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    for _, _, _, _, addr in resolved:
        ip = ipaddress.ip_address(addr[0])
        if _is_dangerous_ip_address(ip):
            return t("security.blockedSsrf", ip=ip)
    return None


# Loopback is explicitly allowed for local diagnostics (default servers, dev ports);
# all other private/link-local/reserved targets are blocked like in the URL path.
_LOCAL_DIAGNOSTIC_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
})


def _host_target_error(host: str, port: int) -> str | None:
    """SSRF/private-IP check for the bare host:port path.

    Loopback/localhost is allowed (local diagnostics); every other host is
    routed through the same validation as the URL path.
    """
    candidate = host.lower().rstrip(".")
    if candidate in _LOCAL_DIAGNOSTIC_HOSTS:
        return None
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError:
        # Hostname — resolve and block dangerous answers (loopback already handled).
        return _resolved_public_host_error(host, port)
    if addr.is_loopback:
        return None
    if _is_dangerous_ip_address(addr):
        return t("security.blockedSsrf", ip=addr)
    return None


def server_check(host: str = "", port: int = 80, name: str = "", url: str = "") -> dict:
    """Server/Port Erreichbarkeit prüfen mit Response-Time."""
    if url or host.startswith(("http://", "https://")):
        parsed_host, parsed_port, normalized_url, url_error = _server_target_from_url(url or host)
        if url_error:
            return {"error": url_error}
        resolved_error = _resolved_public_host_error(parsed_host, parsed_port)
        if resolved_error:
            return {"error": resolved_error}
        host = parsed_host
        port = parsed_port
        name = name or normalized_url

    if not host:
        return {"error": "Host erforderlich."}

    host_error = _host_target_error(host, int(port))
    if host_error:
        return {"error": host_error}

    try:
        start = datetime.now()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, int(port)))
        elapsed = (datetime.now() - start).total_seconds()
        sock.close()

        is_up = result == 0
        return {
            "name": name or f"{host}:{port}",
            "host": host,
            "port": int(port),
            "up": is_up,
            "response_ms": round(elapsed * 1000, 1) if is_up else None,
            "status": "online" if is_up else "offline",
            "checked_at": datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {
            "name": name or f"{host}:{port}",
            "host": host,
            "port": int(port),
            "up": False,
            "error": str(e),
        }


def multi_server_check(servers: str = "", urls: list[str] | None = None) -> list[dict]:
    """Mehrere Server/Ports gleichzeitig prüfen. Format: host:port,host:port"""
    if urls:
        return [server_check(url=url) for url in urls[:20]]

    if not servers:
        # Default common servers
        servers = "127.0.0.1:8000,127.0.0.1:3000,127.0.0.1:5432,127.0.0.1:6379"

    results = []
    for entry in servers.split(","):
        entry = entry.strip()
        if entry.startswith(("http://", "https://")):
            results.append(server_check(url=entry))
        elif ":" in entry:
            host, port_str = entry.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                continue
            results.append(server_check(host=host, port=port))
    return results


# ══════════════════════════════════════════════════════
#  JSON/REGEX TOOLS
# ══════════════════════════════════════════════════════

def json_format(text: str = "") -> str:
    """JSON-Text formatiert anzeigen (Pretty-Print)."""
    if not text:
        return "JSON-Text erforderlich."
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return t("validation.invalidJson", error=str(e))


def regex_test(pattern: str = "", text: str = "") -> dict:
    """Regex-Pattern auf Text testen."""
    if not pattern:
        return {"error": "Pattern erforderlich."}
    if len(pattern) > 500:
        return {"error": "Pattern zu lang (max 500 Zeichen)."}
    if not text:
        return {"error": "Text erforderlich."}
    try:
        regex = re.compile(pattern)
        matches = []
        for m in regex.finditer(text):
            matches.append({
                "match": m.group(),
                "start": m.start(),
                "end": m.end(),
                "groups": list(m.groups()) if m.groups() else [],
            })
        return {
            "pattern": pattern,
            "matches_count": len(matches),
            "matches": matches[:20],
        }
    except re.error as e:
        return {"error": t("validation.invalidPattern", error=str(e))}


def base64_encode(text: str = "") -> str:
    """Text in Base64 encodieren."""
    if not text:
        return "Text erforderlich."
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def base64_decode(text: str = "") -> str:
    """Base64 decodieren."""
    if not text:
        return "Base64-Text erforderlich."
    import base64
    try:
        return base64.b64decode(text).decode("utf-8")
    except Exception as e:
        return t("error.decodeError", error=str(e))


def hash_text(text: str = "", algorithm: str = "sha256") -> dict:
    """Text hashen (md5, sha1, sha256, sha512)."""
    if not text:
        return {"error": "Text erforderlich."}
    import hashlib
    algos = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }
    algo_func = algos.get(algorithm.lower())
    if not algo_func:
        return {"error": f"Algorithmus '{algorithm}' nicht unterstützt. Verfügbar: {', '.join(algos.keys())}"}

    h = algo_func(text.encode("utf-8")).hexdigest()
    return {"text": text[:50], "algorithm": algorithm, "hash": h}


def generate_uuid() -> str:
    """UUID v4 generieren."""
    import uuid
    return str(uuid.uuid4())


def timestamp_convert(timestamp: str = "") -> dict:
    """Unix-Timestamp in lesbares Datum umwandeln (und umgekehrt)."""
    if not timestamp:
        # Return current timestamp
        now = datetime.now()
        return {
            "unix": int(now.timestamp()),
            "iso": now.isoformat(),
            "formatted": now.strftime("%d.%m.%Y %H:%M:%S"),
        }
    try:
        ts = float(timestamp)
        dt = datetime.fromtimestamp(ts)
        return {
            "unix": int(ts),
            "iso": dt.isoformat(),
            "formatted": dt.strftime("%d.%m.%Y %H:%M:%S"),
        }
    except ValueError:
        try:
            # Try parsing date string
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
                try:
                    dt = datetime.strptime(timestamp, fmt)
                    return {
                        "unix": int(dt.timestamp()),
                        "iso": dt.isoformat(),
                        "formatted": dt.strftime("%d.%m.%Y %H:%M:%S"),
                    }
                except ValueError:
                    continue
            return {"error": "Format nicht erkannt."}
        except Exception as e:
            return {"error": str(e)}
