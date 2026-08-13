from __future__ import annotations

import difflib
import hashlib
import http.client
import ipaddress
import io
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import tarfile
import tempfile
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, unquote_plus, urljoin, urlparse, urlsplit, urlunsplit

from .vault import append_jsonl, atomic_write_text, read_json, read_jsonl, write_json


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SOURCE_BYTES = 100 * 1024 * 1024
NORMALIZER_VERSION = 1
_REMOTE_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "target",
    "vendor",
}
_BINARY_SUFFIXES = {
    ".7z",
    ".a",
    ".avi",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lib",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".obj",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".wasm",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xz",
    ".zip",
}
_INJECTION_PATTERNS = {
    "ignore-previous-instructions": re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    "system-tag": re.compile(r"<\s*/?\s*(?:system|developer)(?:\s|>)", re.I),
    "role-override": re.compile(r"\bact\s+as\b|\byou\s+are\s+now\b", re.I),
    "prompt-exfiltration": re.compile(r"\b(?:reveal|print|show)\b.{0,40}\b(?:system|developer)\s+prompt\b", re.I | re.S),
    "jailbreak": re.compile(r"\b(?:jailbreak|developer\s+mode|do\s+anything\s+now)\b", re.I),
}
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I | re.S)),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("bearer-token", re.compile(r"(?i)(\bAuthorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]{8,}")),
    ("credential-assignment", re.compile(r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|passwd|secret)\b[\"']?\s*[:=]\s*[\"']?)([^\s\"'#,;}{]{4,})")),
)
_REMOTE_SCHEMES = {"http", "https", "ssh", "git"}
_SENSITIVE_QUERY_KEYS = {
    "api_key",
    "apikey",
    "access_key",
    "access_token",
    "auth",
    "authorization",
    "client_secret",
    "credential",
    "key",
    "password",
    "passwd",
    "refresh_token",
    "secret",
    "sig",
    "signature",
    "token",
    "x_amz_credential",
    "x_amz_signature",
}
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)), *(f"lpt{number}" for number in range(1, 10))}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_name(value: str, fallback: str = "source") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-_")
    return (value or fallback)[:64]


def _sensitive_query_key(value: str) -> bool:
    key = re.sub(r"[^a-z0-9]+", "_", unquote_plus(value).casefold()).strip("_")
    return key in _SENSITIVE_QUERY_KEYS or key.endswith(("_password", "_secret", "_signature", "_token"))


def _redact_query(query: str) -> str:
    parts: list[str] = []
    for part in query.split("&"):
        key, separator, value = part.partition("=")
        parts.append(f"{key}{separator}[REDACTED]" if separator and value and _sensitive_query_key(key) else part)
    return "&".join(parts)


def _canonical_remote_url(value: str, *, redact: bool = True) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in _REMOTE_SCHEMES:
        return value
    host = parsed.hostname or ""
    host = f"[{host.casefold()}]" if ":" in host else host.casefold()
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError as exc:
        raise ValueError("invalid remote URL port") from exc
    userinfo = "[REDACTED]@" if parsed.username is not None else ""
    query = _redact_query(parsed.query) if redact else parsed.query
    fragment = _redact_query(parsed.fragment) if redact else parsed.fragment
    return urlunsplit((parsed.scheme.casefold(), userinfo + host + port, parsed.path, query, fragment))


def _safe_spec(value: str) -> str:
    if value.startswith("git+"):
        return "git+" + _canonical_remote_url(value[4:])
    return _canonical_remote_url(value)


def _redact_message(message: str, *values: str) -> str:
    output = message
    for value in values:
        if value:
            output = output.replace(value, _safe_spec(value))
    output = re.sub(r"(?i)\b(?:https?|ssh|git)://[^\s<>\"']+", lambda match: _safe_spec(match.group(0)), output)
    output = re.sub(r"(?i)(://)([^/@\s]+)@", r"\1[REDACTED]@", output)
    output = re.sub(
        r"(?i)([?&](?:api[_-]?key|access[_-]?key|access[_-]?token|auth(?:orization)?|client[_-]?secret|credential|key|passw(?:or)?d|secret|sig(?:nature)?|token|x-amz-(?:credential|signature))=)[^&#\s]+",
        r"\1[REDACTED]",
        output,
    )
    return output


def _reject_userinfo(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("remote URLs must not contain userinfo credentials")
    for component in (parsed.query, parsed.fragment):
        for part in component.split("&"):
            key, separator, secret = part.partition("=")
            if separator and secret and _sensitive_query_key(key):
                raise ValueError("remote URLs must not contain credential-like query values")


def _is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        return _is_public_address(mapped)
    if isinstance(address, ipaddress.IPv6Address) and (address.sixtofour is not None or address.teredo is not None):
        return False
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_reserved
        and not getattr(address, "is_site_local", False)
    )


def _validate_public_http_url(value: str) -> tuple[str, int, list[str]]:
    parsed = urlsplit(value)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("HTTP source must use an absolute http(s) URL")
    _reject_userinfo(value)
    hostname = parsed.hostname.rstrip(".")
    try:
        port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    except ValueError as exc:
        raise ValueError("invalid HTTP source port") from exc
    if hostname.casefold() == "localhost" or hostname.casefold().endswith(".localhost"):
        raise ValueError("HTTP source host must be globally routable")
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0].split("%", 1)[0])
                for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            }
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot resolve HTTP source host: {hostname}") from exc
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise ValueError("HTTP source host must resolve only to globally routable addresses")
    return hostname, port, sorted(str(address) for address in addresses)


def _connected_socket(address: str, port: int, timeout: float) -> socket.socket:
    family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
    connection = socket.socket(family, socket.SOCK_STREAM)
    connection.settimeout(timeout)
    try:
        connection.connect((address, port))
        peer = ipaddress.ip_address(connection.getpeername()[0].split("%", 1)[0])
        if str(peer) != str(ipaddress.ip_address(address)) or not _is_public_address(peer):
            raise ValueError("HTTP connection peer does not match the validated public address")
        return connection
    except BaseException:
        connection.close()
        raise


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address

    def connect(self) -> None:
        self.sock = _connected_socket(self._address, self.port, float(self.timeout))


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._address = address

    def connect(self) -> None:
        connection = _connected_socket(self._address, self.port, float(self.timeout))
        self.sock = self._context.wrap_socket(connection, server_hostname=self.host)


def _fetch_public_url(value: str, *, redirects: int = 5) -> tuple[str, bytes, Any]:
    current = value
    for redirect_number in range(redirects + 1):
        hostname, port, addresses = _validate_public_http_url(current)
        parsed = urlsplit(current)
        target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        last_error: BaseException | None = None
        response: http.client.HTTPResponse | None = None
        connection: http.client.HTTPConnection | None = None
        for address in addresses:
            try:
                connection_type = _PinnedHTTPSConnection if parsed.scheme.casefold() == "https" else _PinnedHTTPConnection
                connection = connection_type(hostname, port, address, 30.0)
                connection.request(
                    "GET",
                    target,
                    headers={"User-Agent": "expertctl/0.1", "Accept": "text/*,application/json,application/xml;q=0.8,*/*;q=0.1"},
                )
                response = connection.getresponse()
                break
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                last_error = exc
                if connection is not None:
                    connection.close()
        if response is None or connection is None:
            raise RuntimeError(f"could not connect to validated HTTP source: {last_error}")
        try:
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location or redirect_number >= redirects:
                    raise ValueError("HTTP source redirect is missing a location or exceeds the redirect limit")
                current = urljoin(current, location)
                response.read(MAX_FILE_BYTES + 1)
                continue
            if response.status < 200 or response.status >= 300:
                raise ValueError(f"HTTP source returned status {response.status}")
            data = response.read(MAX_FILE_BYTES + 1)
            return current, data, response.headers
        finally:
            connection.close()
    raise ValueError("HTTP source exceeded the redirect limit")


def _decode_text(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("latin-1")
    if text:
        controls = sum(ord(char) < 32 and char not in "\n\r\t\f\b" for char in text)
        if controls / len(text) > 0.01:
            return None
    return text


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: dict[int, list[str]] = {}
        self.hidden = 0

    def _append(self, value: str, line: int | None = None) -> None:
        start = line or self.getpos()[0]
        for offset, part in enumerate(value.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
            if part:
                self.parts.setdefault(start + offset, []).append(part)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        elif not self.hidden and re.fullmatch(r"h[1-6]", tag):
            self._append("#" * int(tag[1]) + " ")
        elif not self.hidden and tag == "li":
            self._append("- ")
        elif not self.hidden and tag in {"br", "p", "div", "section", "article", "pre", "tr"}:
            self._append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in {"p", "div", "section", "article", "pre", "li", "tr"}:
            self._append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self._append(data)

    def markdown(self, line_count: int) -> str:
        lines = [re.sub(r"\s+", " ", "".join(self.parts.get(number, []))).strip() for number in range(1, line_count + 1)]
        return "\n".join(lines) + "\n"


def _normalise(relative: PurePosixPath, data: bytes, content_type: str = "") -> tuple[PurePosixPath, str] | None:
    if relative.suffix.casefold() == ".pdf" or content_type.casefold() == "application/pdf":
        return None
    text = _decode_text(data)
    if text is None:
        return None
    if relative.suffix.lower() in {".html", ".htm"} or "text/html" in content_type.lower():
        parser = _HTMLText()
        parser.feed(text)
        parser.close()
        return relative.with_suffix(relative.suffix + ".md"), parser.markdown(len(text.replace("\r\n", "\n").replace("\r", "\n").splitlines()))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return relative, text.rstrip() + "\n"


def _prompt_flags(files: list[tuple[PurePosixPath, bytes]]) -> list[str]:
    found: set[str] = set()
    for _, data in files:
        text = _decode_text(data)
        if text is None:
            continue
        for label, pattern in _INJECTION_PATTERNS.items():
            if pattern.search(text):
                found.add(label)
    return sorted(found)


def _redact_secrets(text: str) -> tuple[str, list[str]]:
    found: set[str] = set()
    output = text

    def replacement(match: re.Match[str], label: str) -> str:
        prefix = match.group(1) if match.re.groups else ""
        matched = match.group(0)
        secret = matched[len(prefix) :]
        newlines = "".join(re.findall(r"\r\n|\r|\n", secret))
        return prefix + f"[REDACTED:{label}]" + newlines

    for label, pattern in _SECRET_PATTERNS:
        if not pattern.search(output):
            continue
        found.add(label)
        output = pattern.sub(lambda match, label=label: replacement(match, label), output)
    return output, sorted(found)


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Redact recognized credentials before source text leaves the trust boundary."""
    return _redact_secrets(text)


def _tree_digest(files: list[tuple[PurePosixPath, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(files, key=lambda item: item[0].as_posix()):
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _is_derived_map_directory(path: Path) -> bool:
    """Keep generated corpus maps out of captured source evidence."""
    return path.name.casefold().endswith("-out") and (path / "graph.json").is_file()


def _validate_portable_paths(files: list[tuple[PurePosixPath, Any]]) -> None:
    seen: dict[str, PurePosixPath] = {}
    for relative, _ in files:
        raw = relative.as_posix()
        normalized = unicodedata.normalize("NFKC", raw)
        path = PurePosixPath(normalized)
        if len(normalized.encode("utf-8")) > 1024:
            raise ValueError(f"source path is too long for portable storage: {raw!r}")
        if relative.is_absolute() or path.is_absolute() or not relative.parts or ".." in relative.parts or ".." in path.parts or "\\" in raw:
            raise ValueError(f"unsafe source path: {raw!r}")
        for part in path.parts:
            if (
                part in {"", ".", ".."}
                or len(part.encode("utf-8")) > 240
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or part.endswith((" ", "."))
                or part.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
            ):
                raise ValueError(f"non-portable source path: {raw!r}")
        key = normalized.casefold()
        if key in seen:
            raise ValueError(f"portable source path collision: {seen[key]} and {relative}")
        seen[key] = relative


def _collect_tree(root: Path) -> tuple[list[tuple[PurePosixPath, bytes]], list[str]]:
    base = root.resolve()
    files: list[tuple[PurePosixPath, bytes]] = []
    skipped: list[str] = []
    total = 0
    for current, directories, names in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            relative = path.relative_to(base).as_posix()
            resolved = path.resolve()
            if not _inside(resolved, base):
                raise ValueError(f"directory link escapes source root: {relative}")
            if path.is_symlink() or resolved != path.absolute():
                skipped.append(relative)
            elif name.casefold() in _SKIP_DIRS or _is_derived_map_directory(path):
                skipped.append(relative)
            else:
                kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            path = current_path / name
            relative_path = path.relative_to(base)
            relative = relative_path.as_posix()
            resolved = path.resolve()
            if not _inside(resolved, base):
                raise ValueError(f"file link escapes source root: {relative}")
            if path.is_symlink() or resolved != path.absolute():
                skipped.append(relative)
                continue
            suffix = path.suffix.casefold()
            if suffix in _BINARY_SUFFIXES - {".pdf"}:
                skipped.append(relative)
                continue
            try:
                size = path.stat().st_size
            except OSError:
                skipped.append(relative)
                continue
            if size > MAX_FILE_BYTES:
                skipped.append(relative)
                continue
            data = path.read_bytes()
            if suffix != ".pdf" and _decode_text(data) is None:
                skipped.append(relative)
                continue
            total += len(data)
            if total > MAX_SOURCE_BYTES:
                raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} bytes of text")
            files.append((PurePosixPath(relative), data))
    return sorted(files, key=lambda item: item[0].as_posix()), sorted(skipped)


def _collect_file(path: Path) -> tuple[list[tuple[PurePosixPath, bytes]], list[str]]:
    resolved = path.resolve()
    if resolved.suffix.casefold() in _BINARY_SUFFIXES - {".pdf"}:
        raise ValueError(f"binary files are not supported by the stdlib MVP: {path}")
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes: {path}")
    data = resolved.read_bytes()
    if resolved.suffix.casefold() != ".pdf" and _decode_text(data) is None:
        raise ValueError(f"binary file is not supported: {path}")
    return [(PurePosixPath(_safe_name(resolved.name, "document.txt")), data)], []


def _workspace_reference_source(vault: Path, entry: dict[str, Any]) -> Path | None:
    """Resolve the workspace source root for a deliberately thin vault."""
    root = Path(vault).expanduser().resolve()
    config = read_json(root / "vault.json", {})
    if not isinstance(config, dict) or config.get("source_storage") != "workspace-reference":
        return None
    spec = str(entry.get("spec") or "").strip()
    if not spec:
        raise ValueError(f"workspace-reference source has no relative spec: {entry.get('id')}")
    relative = Path(spec.replace("\\", os.sep).replace("/", os.sep))
    if relative.is_absolute():
        raise ValueError(f"workspace-reference source must be relative: {entry.get('id')}")
    workspace = root.parent.parent.resolve()
    candidate = (workspace / relative).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"workspace-reference source escapes workspace: {entry.get('id')}")
    return candidate


def workspace_reference_root(vault: Path, entry: dict[str, Any]) -> Path | None:
    """Return the adjacent source root for runtime inventory readers."""
    return _workspace_reference_source(vault, entry)


def workspace_reference_files(vault: Path, entry: dict[str, Any]) -> list[tuple[PurePosixPath, bytes]] | None:
    """Return live workspace evidence for a deliberately thin published vault.

    A ``workspace-reference`` vault ships its compact Wiki/index beside the
    source packs it was compiled from.  It is portable inside that workspace:
    references are resolved only from the registry's relative ``spec`` and
    never from an arbitrary absolute path.
    """
    candidate = _workspace_reference_source(vault, entry)
    if candidate is None:
        return None
    spec = str(entry.get("spec") or "").strip()
    kind = str(entry.get("kind") or "")
    if kind == "file":
        if not candidate.is_file():
            raise FileNotFoundError(f"workspace-reference file missing: {spec}")
        files, _ = _collect_file(candidate)
        return files
    if kind == "directory":
        if not candidate.is_dir():
            raise FileNotFoundError(f"workspace-reference directory missing: {spec}")
        files, _ = _collect_tree(candidate)
        return files
    raise ValueError(f"workspace-reference source kind is unsupported: {kind!r}")


def workspace_reference_path(vault: Path, entry: dict[str, Any], relative: PurePosixPath) -> Path | None:
    """Resolve a raw snapshot-relative file to its adjacent workspace source."""
    source = _workspace_reference_source(vault, entry)
    if source is None:
        return None
    if source.is_file():
        raw_names = [
            str(item.get("raw") or "")
            for item in entry.get("normalization_map", [])
            if isinstance(item, dict) and item.get("raw")
        ]
        expected = PurePosixPath(raw_names[0]) if raw_names else PurePosixPath(_safe_name(source.name, "document.txt"))
        return source if relative == expected else None
    candidate = (source / Path(*relative.parts)).resolve()
    if candidate != source and source not in candidate.parents:
        raise ValueError(f"workspace-reference path escapes source: {relative}")
    return candidate if candidate.is_file() else None


def _git(path: Path | None, *arguments: str) -> str:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("git executable is required for Git sources")
    command = [executable]
    if path is not None:
        command.extend(["-C", str(path)])
    command.extend(arguments)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if result.returncode:
        raise RuntimeError(_redact_message(result.stderr.strip() or "git command failed", *arguments))
    return result.stdout.strip()


def _git_url(spec: str) -> bool:
    explicit = spec.startswith("git+")
    value = spec[4:] if explicit else spec
    if explicit:
        return bool(value.strip())
    if re.fullmatch(r"[^/@\s]+@[^:/\s]+:.+", value):
        return True
    parsed = urlparse(value)
    if parsed.scheme in {"git", "ssh"}:
        return True
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.lower()
    if path.endswith(".git"):
        return True
    if parsed.netloc.lower() in {"github.com", "gitlab.com", "bitbucket.org"}:
        excluded = {"blob", "tree", "issues", "pull", "pulls", "wiki", "-/"}
        parts = [part for part in path.split("/") if part]
        return len(parts) >= 2 and not any(part in excluded for part in parts)
    return False


def _git_snapshot(path: Path) -> tuple[list[tuple[PurePosixPath, bytes]], list[str]]:
    executable = shutil.which("git")
    if not executable:
        raise RuntimeError("git executable is required for Git sources")
    result = subprocess.run(
        [executable, "-C", str(path), "archive", "--format=tar", "HEAD"],
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "git archive failed")
    files: list[tuple[PurePosixPath, bytes]] = []
    skipped: list[str] = []
    total = 0
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in sorted(archive.getmembers(), key=lambda item: item.name):
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe path in Git archive: {member.name}")
            if not member.isfile() or any(part.casefold() in _SKIP_DIRS for part in relative.parts[:-1]):
                skipped.append(relative.as_posix())
                continue
            suffix = relative.suffix.casefold()
            if suffix in _BINARY_SUFFIXES - {".pdf"} or member.size > MAX_FILE_BYTES:
                skipped.append(relative.as_posix())
                continue
            handle = archive.extractfile(member)
            data = handle.read() if handle else b""
            if suffix != ".pdf" and _decode_text(data) is None:
                skipped.append(relative.as_posix())
                continue
            total += len(data)
            if total > MAX_SOURCE_BYTES:
                raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
            files.append((relative, data))
    return files, sorted(skipped)


def _source_id(kind: str, label: str, uri: str) -> str:
    if urlsplit(uri).scheme.casefold() in _REMOTE_SCHEMES:
        normalized = _canonical_remote_url(uri, redact=False)
    elif match := re.fullmatch(r"(?P<user>[^/@\s]+)@(?P<host>[^:/\s]+):(?P<path>.+)", uri):
        normalized = f"{match.group('user')}@{match.group('host').casefold()}:{match.group('path')}"
    else:
        normalized = uri.casefold() if os.name == "nt" else uri
    origin = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{kind}.{_safe_name(label).lower()[:32]}.{origin}"


def _workspace_source_identity(vault: Path, resolved: Path, original: str) -> tuple[str, str]:
    """Use a stable identity for local sources that ship beside the vault."""
    workspace = Path(vault).expanduser().resolve().parent.parent
    try:
        relative = resolved.relative_to(workspace)
    except ValueError:
        return original, str(resolved)
    portable_spec = relative.as_posix()
    return portable_spec, f"workspace:{portable_spec}"


def _write_snapshot(root: Path, files: list[tuple[PurePosixPath, bytes | str]]) -> None:
    _validate_portable_paths(files)
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists():
        existing, _ = _collect_tree(root)
        expected = [(path, content.encode("utf-8") if isinstance(content, str) else content) for path, content in files]
        if _tree_digest(existing) != _tree_digest(expected):
            raise ValueError(f"immutable snapshot integrity failure: {root}")
        return
    staging = Path(tempfile.mkdtemp(prefix=".ingest-", dir=root.parent))
    try:
        for relative, content in files:
            target = staging.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8", newline="\n")
        os.replace(staging, root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _declared_authority(metadata: dict[str, Any]) -> str:
    discovery = metadata.get("discovery")
    authority = discovery.get("authority") if isinstance(discovery, dict) else None
    return str(authority) if authority in {"primary", "secondary", "community"} else "untrusted-source"


def _store(
    vault: Path,
    *,
    kind: str,
    spec: str,
    uri: str,
    label: str,
    files: list[tuple[PurePosixPath, bytes]],
    skipped: list[str],
    metadata: dict[str, Any] | None = None,
    content_type: str = "",
    source_id_override: str | None = None,
    force_snapshot: bool = False,
) -> dict[str, Any]:
    if not files:
        raise ValueError("source contains no supported text files")
    registry_spec = _safe_spec(spec)
    registry_uri = _safe_spec(uri)
    sha256 = _tree_digest(files)
    normalization_profile = {"normalizer_version": NORMALIZER_VERSION, "content_type": content_type.casefold().strip()}
    normalization_key = hashlib.sha256(
        repr(sorted(normalization_profile.items())).encode("utf-8")
    ).hexdigest()[:10]
    registry_path = vault / "sources/registry.jsonl"
    registry = read_jsonl(registry_path)
    previous = next(
        (
            item
            for item in reversed(registry)
            if item.get("kind") == kind and item.get("uri") == registry_uri
        ),
        None,
    )
    source_id = source_id_override or (
        str(previous.get("id") or "") if previous else _source_id(kind, label, uri)
    )
    metadata = dict(metadata or {})
    if previous and "discovery" not in metadata and isinstance(previous.get("discovery"), dict):
        metadata["discovery"] = previous["discovery"]
    if not force_snapshot and previous and previous.get("sha256") == sha256 and previous.get("normalization_profile") == normalization_profile:
        raw = vault / str(previous.get("raw_path", ""))
        existing, _ = _collect_tree(raw)
        if _tree_digest(existing) != sha256:
            raise ValueError(f"immutable raw snapshot integrity failure: {raw}")
        normalized = vault / str(previous.get("normalized_path", ""))
        normalized_files, _ = _collect_tree(normalized)
        if previous.get("normalized_sha256") != _tree_digest(normalized_files):
            raise ValueError(f"immutable normalized snapshot integrity failure: {normalized}")
        result = dict(previous)
        changed_metadata = False
        if metadata:
            clean_metadata = {key: value for key, value in metadata.items() if value not in (None, "")}
            changed_metadata = any(result.get(key) != value for key, value in clean_metadata.items())
            result.update(clean_metadata)
        authority = _declared_authority(result)
        changed_metadata = changed_metadata or result.get("authority") != authority
        result["authority"] = authority
        result["version"] = result.get("commit") or result.get("etag") or result.get("snapshot")
        if changed_metadata:
            result["added_at"] = _utc_now()
            append_jsonl(registry_path, result)
        return result

    snapshot = sha256[:12]
    raw_root = vault / "sources/raw" / source_id / snapshot
    normalized_root = vault / "sources/normalized" / source_id / f"{snapshot}-{normalization_key}"
    normalised: dict[str, tuple[PurePosixPath, str]] = {}
    normalization_map: list[dict[str, Any]] = []
    secret_flags: set[str] = set()
    for relative, data in files:
        item = _normalise(relative, data, content_type)
        if item is not None:
            redacted, flags_for_file = _redact_secrets(item[1])
            secret_flags.update(flags_for_file)
            normalized_name = item[0].as_posix()
            if normalized_name in normalised:
                raise ValueError(f"normalization path collision: {normalized_name}")
            normalised[normalized_name] = (item[0], redacted)
            normalization_map.append({"raw": relative.as_posix(), "normalized": item[0].as_posix(), "line_mapping": "identity"})
    normalized_files = [(path, text.encode("utf-8")) for path, text in normalised.values()]
    normalized_sha256 = _tree_digest(normalized_files)
    _validate_portable_paths(files)
    _validate_portable_paths(list(normalised.values()))
    _write_snapshot(raw_root, files)
    _write_snapshot(normalized_root, list(normalised.values()))

    flags = _prompt_flags(files)
    entry: dict[str, Any] = {
        "id": source_id,
        "kind": kind,
        "spec": registry_spec,
        "uri": registry_uri,
        "trusted": False,
        "trust": False,
        "authority": "untrusted-source",
        "added_at": _utc_now(),
        "raw_path": raw_root.relative_to(vault).as_posix(),
        "normalized_path": normalized_root.relative_to(vault).as_posix(),
        "normalized_sha256": normalized_sha256,
        "normalizer_version": NORMALIZER_VERSION,
        "normalization_profile": normalization_profile,
        "sha256": sha256,
        "snapshot": snapshot,
        "file_count": len(files),
        "byte_count": sum(len(data) for _, data in files),
        "skipped": skipped,
        "prompt_injection": bool(flags),
        "prompt_injection_flags": flags,
        "secrets_redacted": bool(secret_flags),
        "secret_flags": sorted(secret_flags),
        "normalization": "text" if normalised else "raw-only",
        "normalization_map": sorted(normalization_map, key=lambda item: (item["normalized"], item["raw"])),
        "refresh": "remote" if kind in {"git", "url"} else "manual",
    }
    if metadata:
        entry.update({key: value for key, value in metadata.items() if value not in (None, "")})
    entry["authority"] = _declared_authority(entry)
    entry["version"] = entry.get("commit") or entry.get("etag") or snapshot
    append_jsonl(registry_path, entry)
    return entry


def _add_one(vault: Path, spec: str, declared_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError("source spec must be a non-empty string")
    original = spec.strip()
    declared = dict(declared_metadata or {})
    if set(declared) - {"discovery"} or ("discovery" in declared and not isinstance(declared["discovery"], dict)):
        raise ValueError("declared source metadata may contain only a discovery object")
    local = Path(original).expanduser()
    if not local.is_absolute():
        local = Path(vault).expanduser().resolve().parent.parent / local
    if local.exists():
        resolved = local.resolve()
        registry_spec, registry_uri = _workspace_source_identity(vault, resolved, original)
        if resolved.is_dir():
            is_git = (resolved / ".git").exists()
            files, skipped = _git_snapshot(resolved) if is_git else _collect_tree(resolved)
            metadata: dict[str, Any] = dict(declared)
            if is_git:
                metadata.update({
                    "commit": _git(resolved, "rev-parse", "HEAD"),
                    "branch": _git(resolved, "rev-parse", "--abbrev-ref", "HEAD"),
                    "dirty_worktree_ignored": bool(_git(resolved, "status", "--porcelain", "--untracked-files=normal")),
                })
            return _store(
                vault,
                kind="git" if is_git else "directory",
                spec=registry_spec,
                uri=registry_uri,
                label=resolved.name,
                files=files,
                skipped=skipped,
                metadata=metadata,
            )
        if resolved.is_file():
            files, skipped = _collect_file(resolved)
            return _store(
                vault,
                kind="file",
                spec=registry_spec,
                uri=registry_uri,
                label=resolved.stem,
                files=files,
                skipped=skipped,
                metadata=declared,
            )
        raise ValueError(f"unsupported local source: {spec}")

    if _git_url(original):
        uri = original[4:] if original.startswith("git+") else original
        parsed = urlparse(uri)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("remote Git sources must use a public HTTPS URL")
        if str(parsed.hostname or "").casefold().rstrip(".") not in _REMOTE_GIT_HOSTS:
            raise ValueError("remote Git sources are limited to github.com, gitlab.com, or bitbucket.org")
        _validate_public_http_url(uri)
        with tempfile.TemporaryDirectory(prefix="expertctl-git-") as temporary:
            checkout = Path(temporary) / "checkout"
            hooks = Path(temporary) / "disabled-hooks"
            hooks.mkdir()
            git_options = ["-c", f"core.hooksPath={hooks}"]
            git_options.extend(["-c", "http.followRedirects=false"])
            _git(None, *git_options, "clone", "--depth", "1", "--no-tags", "--no-checkout", "--", uri, str(checkout))
            files, skipped = _git_snapshot(checkout)
            label = Path(urlparse(uri).path.rstrip("/")).stem or "repository"
            return _store(
                vault,
                kind="git",
                spec=original,
                uri=uri,
                label=label,
                files=files,
                skipped=skipped,
                metadata={
                    **declared,
                    "commit": _git(checkout, "rev-parse", "HEAD"),
                    "branch": _git(checkout, "rev-parse", "--abbrev-ref", "HEAD"),
                },
            )

    parsed = urlparse(original)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FileNotFoundError("source does not exist and is not a supported URL")
    final_url, data, response_headers = _fetch_public_url(original)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"URL response exceeds {MAX_FILE_BYTES} bytes")
    content_type = response_headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    name = _safe_name(unquote(Path(urlparse(final_url).path).name), "index")
    if content_type == "application/pdf":
        name = str(PurePosixPath(name).with_suffix(".pdf"))
    elif "." not in name:
        name += {"text/html": ".html", "application/json": ".json", "application/xml": ".xml", "application/pdf": ".pdf"}.get(content_type, ".txt")
    if content_type != "application/pdf" and _decode_text(data) is None:
        raise ValueError("URL did not return supported text")
    headers = {
        **declared,
        "content_type": content_type,
        "etag": response_headers.get("ETag"),
        "last_modified": response_headers.get("Last-Modified"),
        "resolved_uri": _safe_spec(final_url),
    }
    return _store(
        vault,
        kind="url",
        spec=original,
        uri=original,
        label=Path(unquote(urlparse(original).path)).stem or "web",
        files=[(PurePosixPath(name), data)],
        skipped=[],
        metadata=headers,
        content_type=content_type,
    )


def add_sources(
    vault: Path,
    specs: list[str],
    declared_metadata: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    root = Path(vault).expanduser().resolve()
    if not (root / "vault.json").is_file():
        raise FileNotFoundError(f"not an expertise vault: {root}")
    if declared_metadata is not None and len(declared_metadata) != len(specs):
        raise ValueError("declared source metadata must align with source specs")
    records: list[dict[str, Any]] = []
    metadata = declared_metadata or [{} for _ in specs]
    for spec, item_metadata in zip(specs, metadata, strict=True):
        try:
            records.append(_add_one(root, spec, item_metadata))
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise type(exc)(_redact_message(str(exc), spec)) from exc
        except Exception as exc:
            raise RuntimeError(_redact_message(str(exc), spec)) from exc
    return records


def materialize_workspace_references(vault: Path) -> dict[str, Any]:
    """Restore raw/normalized snapshots before a user expands a thin vault."""
    root = Path(vault).expanduser().resolve()
    config = read_json(root / "vault.json", {})
    if not isinstance(config, dict) or config.get("source_storage") != "workspace-reference":
        return {"materialized": False, "reason": "vault already stores source snapshots"}
    latest: dict[str, dict[str, Any]] = {}
    for entry in read_jsonl(root / "sources" / "registry.jsonl"):
        if isinstance(entry, dict) and entry.get("id"):
            latest[str(entry["id"])] = entry
    restored: list[str] = []
    for source_id, entry in sorted(latest.items()):
        source = _workspace_reference_source(root, entry)
        files = workspace_reference_files(root, entry)
        if source is None or files is None:
            raise ValueError(f"cannot materialize non-workspace source: {source_id}")
        if source.is_dir():
            _, skipped = _collect_tree(source)
        else:
            _, skipped = _collect_file(source)
        discovery = entry.get("discovery")
        metadata = {"discovery": discovery} if isinstance(discovery, dict) else None
        _store(
            root,
            kind=str(entry.get("kind") or "directory"),
            spec=str(entry.get("spec") or ""),
            uri=str(entry.get("uri") or ""),
            label=source_id,
            files=files,
            skipped=skipped,
            metadata=metadata,
            content_type=str(entry.get("content_type") or ""),
            source_id_override=source_id,
            force_snapshot=True,
        )
        restored.append(source_id)
    next_config = dict(config)
    next_config.pop("source_storage", None)
    write_json(root / "vault.json", next_config)
    return {"materialized": True, "sources": restored}


def _portable_workspace_value(value: str, workspace: Path) -> str:
    normalized = value.replace("\\", "/")
    prefix = workspace.as_posix().rstrip("/")
    if os.name == "nt":
        matches = normalized.casefold() == prefix.casefold()
        nested = normalized.casefold().startswith(prefix.casefold() + "/")
    else:
        matches = normalized == prefix
        nested = normalized.startswith(prefix + "/")
    return normalized[len(prefix) :].lstrip("/") if matches or nested else value


def _rewrite_workspace_values(value: Any, workspace: Path) -> Any:
    if isinstance(value, str):
        return _portable_workspace_value(value, workspace)
    if isinstance(value, list):
        return [_rewrite_workspace_values(item, workspace) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_workspace_values(item, workspace) for key, item in value.items()}
    return value


def migrate_workspace_paths(vault: Path) -> dict[str, Any]:
    """Replace host-specific paths in a thin vault with portable references."""
    root = Path(vault).expanduser().resolve()
    config = read_json(root / "vault.json", {})
    if not isinstance(config, dict) or config.get("source_storage") != "workspace-reference":
        raise ValueError("migrate-workspace-paths requires a workspace-reference vault")
    workspace = root.parent.parent.resolve()
    registry_path = root / "sources" / "registry.jsonl"
    registry = read_jsonl(registry_path)
    rewritten_registry: list[Any] = []
    source_records = 0
    for item in registry:
        if not isinstance(item, dict) or item.get("kind") not in {"file", "directory"}:
            rewritten_registry.append(item)
            continue
        spec = str(item.get("spec") or "").replace("\\", "/").strip()
        relative = PurePosixPath(spec)
        if not spec or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"workspace-reference source must have a relative spec: {item.get('id')}")
        updated = dict(item)
        updated["spec"] = relative.as_posix()
        updated["uri"] = f"workspace:{relative.as_posix()}"
        source_records += int(updated != item)
        rewritten_registry.append(updated)
    if rewritten_registry != registry:
        atomic_write_text(
            registry_path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in rewritten_registry),
        )

    state_files = [*sorted((root / "state").glob("*.json")), *sorted((root / "state").glob("*.jsonl"))]
    state_files_rewritten = 0
    for path in state_files:
        if path.suffix == ".jsonl":
            value = read_jsonl(path)
            encoded = "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in value)
        else:
            value = read_json(path, None)
            encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        updated = _rewrite_workspace_values(value, workspace)
        updated_encoded = (
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in updated)
            if path.suffix == ".jsonl"
            else json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if updated_encoded != encoded:
            atomic_write_text(path, updated_encoded)
            state_files_rewritten += 1
    return {"migrated": True, "source_records": source_records, "state_files": state_files_rewritten}


def _snapshot_content_map(vault: Path, entry: dict[str, Any]) -> dict[str, bytes]:
    files, _ = _collect_tree(vault / str(entry.get("raw_path", "")))
    return {path.as_posix(): data for path, data in files}


def _changed_line_ranges(before: bytes, after: bytes) -> tuple[list[dict[str, int]], list[dict[str, int]]]:
    old_lines = before.decode("utf-8", "replace").splitlines()
    new_lines = after.decode("utf-8", "replace").splitlines()
    old_ranges: list[dict[str, int]] = []
    new_ranges: list[dict[str, int]] = []
    for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if old_start == old_end:
            line = max(1, min(len(old_lines) or 1, old_start + 1))
            old_ranges.append({"start_line": line, "end_line": line})
        else:
            old_ranges.append({"start_line": old_start + 1, "end_line": old_end})
        if new_start == new_end:
            line = max(1, min(len(new_lines) or 1, new_start + 1))
            new_ranges.append({"start_line": line, "end_line": line})
        else:
            new_ranges.append({"start_line": new_start + 1, "end_line": new_end})
    return old_ranges, new_ranges


def _changed_files(vault: Path, old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    before, after = _snapshot_content_map(vault, old), _snapshot_content_map(vault, new)
    result: list[dict[str, Any]] = []
    for path in sorted(before.keys() | after.keys()):
        status = (
            "added"
            if path not in before
            else "deleted"
            if path not in after
            else "modified"
            if hashlib.sha256(before[path]).digest() != hashlib.sha256(after[path]).digest()
            else ""
        )
        if status:
            item: dict[str, Any] = {"path": path, "status": status}
            if status == "modified":
                item["old_line_ranges"], item["new_line_ranges"] = _changed_line_ranges(before[path], after[path])
            elif status == "deleted" and before[path]:
                item["old_line_ranges"] = [{"start_line": 1, "end_line": max(1, len(before[path].decode("utf-8", "replace").splitlines()))}]
            result.append(item)
    return result


def refresh_sources(vault: Path) -> list[dict[str, Any]]:
    """Refresh the latest Git and URL entries; local files remain manual."""
    root = Path(vault).expanduser().resolve()
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in read_jsonl(root / "sources/registry.jsonl"):
        if entry.get("kind") in {"git", "url"}:
            latest[(entry["kind"], entry.get("uri", entry.get("spec", "")))] = entry
    reports: list[dict[str, Any]] = []
    for _, old in sorted(latest.items(), key=lambda item: item[0]):
        try:
            local_uri = Path(str(old.get("uri", ""))).expanduser()
            refresh_spec = str(local_uri) if local_uri.exists() else old.get("spec") or old["uri"]
            discovery = old.get("discovery")
            declared = {"discovery": discovery} if isinstance(discovery, dict) else None
            new = _add_one(root, refresh_spec, declared)
            content_changed = new.get("sha256") != old.get("sha256")
            version_changed = any(new.get(field) != old.get(field) for field in ("commit", "etag", "last_modified", "version"))
            derived_changed = any(
                new.get(field) != old.get(field)
                for field in ("normalized_sha256", "normalizer_version", "normalization_profile", "normalized_path")
            )
            changed = content_changed or version_changed or derived_changed
            changed_files = _changed_files(root, old, new) if content_changed else []
            diff_method = "snapshot-diff"
            if changed and old.get("kind") == "git" and local_uri.is_dir() and old.get("commit") and new.get("commit"):
                try:
                    output = _git(local_uri.resolve(), "diff", "--name-status", str(old["commit"]), str(new["commit"]), "--")
                    parsed: list[dict[str, Any]] = []
                    for line in output.splitlines():
                        fields = line.split("\t")
                        if len(fields) >= 2:
                            code = fields[0][0]
                            if code == "R" and len(fields) >= 3:
                                parsed.extend(({"path": fields[-2], "status": "deleted"}, {"path": fields[-1], "status": "added"}))
                            elif code == "C" and len(fields) >= 3:
                                parsed.append({"path": fields[-1], "status": "added"})
                            else:
                                parsed.append({"path": fields[-1], "status": {"A": "added", "D": "deleted"}.get(code, "modified")})
                    snapshot_details = {str(item.get("path")): item for item in changed_files}
                    changed_files = [
                        {**snapshot_details.get(str(item.get("path")), {}), **item}
                        for item in parsed
                    ] or changed_files
                    diff_method = "git-diff"
                except RuntimeError:
                    pass
            reports.append(
                {
                    "id": new.get("id"),
                    "kind": old.get("kind"),
                    "uri": old.get("uri"),
                    "status": "changed" if changed else "unchanged",
                    "content_changed": content_changed,
                    "version_changed": version_changed,
                    "derived_changed": derived_changed,
                    "old_sha256": old.get("sha256"),
                    "new_sha256": new.get("sha256"),
                    "old_snapshot": old.get("snapshot"),
                    "new_snapshot": new.get("snapshot"),
                    "old_commit": old.get("commit"),
                    "new_commit": new.get("commit"),
                    "changed_files": changed_files,
                    "diff_method": diff_method,
                }
            )
        except Exception as exc:
            reports.append(
                {
                    "id": old.get("id"),
                    "kind": old.get("kind"),
                    "uri": old.get("uri"),
                    "status": "error",
                    "error": _redact_message(str(exc), str(old.get("spec", "")), str(old.get("uri", ""))),
                }
            )
    return reports
