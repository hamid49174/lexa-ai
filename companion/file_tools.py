"""Lexa AI — Datei-Tools
Duplikat-Finder, Batch-Rename, PDF-Bearbeitung, Backup, Download-Organizer,
Archive (ZIP/7z), Bild-Konvertierung, Datei-Infos (Phase 20)
"""

import os
import hashlib
import shutil
import logging
import zipfile
import json
from pathlib import Path
from datetime import datetime

from backend.config import LEXA_DATA_DIR
from backend.i18n import t

logger = logging.getLogger("lexa.files")

_FILE_WRITE_MAX_CHARS = 200_000
_FILE_WRITE_BLOCKED_EXTS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".lnk",
    ".msi",
    ".ps1",
    ".reg",
    ".scr",
    ".sys",
    ".vbs",
}
_FILE_WRITE_BLOCKED_PATH_PARTS = (
    "system32",
    "syswow64",
    "windows\\system",
    "program files\\windows defender",
)


def _is_relative_to_path(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _trusted_temp_roots() -> list[Path]:
    roots: list[Path] = []
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        roots.append(Path(local_appdata) / "Temp")
    roots.append(Path.home() / "AppData" / "Local" / "Temp")

    windows_root = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windows_root:
        roots.append(Path(windows_root) / "Temp")

    trusted: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in seen:
            trusted.append(resolved)
            seen.add(resolved)
    return trusted


def _is_trusted_temp_root(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in _trusted_temp_roots():
        if resolved == root or _is_relative_to_path(resolved, root):
            return True
    return False


def _validate_scan_path(path: str) -> str | None:
    """Returns error string if path should not be scanned."""
    p = Path(path)
    if not p.exists():
        return f"Pfad nicht gefunden: {path}"
    resolved = str(p.resolve()).lower()
    blocked = ["system32", "syswow64", "windows\\system", "program files\\windows defender"]
    if any(b in resolved for b in blocked):
        return "Systemverzeichnis nicht erlaubt."
    return None


def find_duplicates(search_path: str = "C:/Users", max_files: int = 1000) -> list[dict]:
    """Find duplicate files using 2-phase hashing (fast + accurate).

    Phase 1: Group files by size (instant, no I/O)
    Phase 2: For size-matched files, hash first 8KB (fast pre-filter)
    Phase 3: For pre-filter matches, hash FULL file with SHA-256 (no false positives)

    This eliminates false positives from partial MD5 hashing while staying fast
    by only doing full hashes on candidate duplicates.
    """
    err = _validate_scan_path(search_path)
    if err:
        return [{"error": err}]
    max_files = max(1, min(10000, max_files))
    import time

    # Phase 1: Group by file size
    size_groups = {}  # size -> [filepath, ...]
    count = 0
    start_time = time.monotonic()

    skip_dirs = {
        "node_modules", "__pycache__", ".git", ".hg", ".svn",
        "AppData", "Windows", "$Recycle.Bin", "ProgramData",
        ".cache", ".npm", ".nuget", "venv", ".venv",
    }

    for root, dirs, files in os.walk(search_path):
        if time.monotonic() - start_time > 30:  # 30s timeout
            break
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]
        for filename in files:
            if count >= max_files:
                break
            filepath = os.path.join(root, filename)
            try:
                size = os.path.getsize(filepath)
                if size < 100 or size > 2_000_000_000:  # Skip tiny/huge (>2GB)
                    continue
                size_groups.setdefault(size, []).append(filepath)
                count += 1
            except (PermissionError, OSError):
                continue

    # Phase 2+3: Hash only files with matching sizes
    duplicates = []
    for size, paths in size_groups.items():
        if len(paths) < 2:
            continue

        # Phase 2: Quick hash (first 8KB) to narrow candidates
        quick_hashes = {}  # hash -> [filepath, ...]
        for filepath in paths:
            try:
                with open(filepath, "rb") as f:
                    quick_hash = hashlib.sha256(f.read(8192)).hexdigest()
                quick_hashes.setdefault(quick_hash, []).append(filepath)
            except (PermissionError, OSError):
                continue

        # Phase 3: Full hash only for quick-hash matches
        for qhash, candidates in quick_hashes.items():
            if len(candidates) < 2:
                continue

            full_hashes = {}  # hash -> filepath (first seen)
            for filepath in candidates:
                try:
                    h = hashlib.sha256()
                    with open(filepath, "rb") as f:
                        while True:
                            chunk = f.read(65536)  # 64KB chunks
                            if not chunk:
                                break
                            h.update(chunk)
                    full_hash = h.hexdigest()

                    if full_hash in full_hashes:
                        duplicates.append({
                            "original": full_hashes[full_hash],
                            "duplicate": filepath,
                            "size_mb": round(size / 1024 / 1024, 2),
                            "hash": full_hash[:16],
                        })
                    else:
                        full_hashes[full_hash] = filepath
                except (PermissionError, OSError):
                    continue

    return sorted(duplicates, key=lambda x: x["size_mb"], reverse=True)[:30]


def batch_rename(folder: str, pattern: str = "", prefix: str = "", suffix: str = "",
                 replace_from: str = "", replace_to: str = "") -> list[dict]:
    """Batch rename files in a folder."""
    results = []
    folder_path = Path(folder)

    if not folder_path.exists():
        return [{"error": f"Ordner nicht gefunden: {folder}"}]

    for i, filepath in enumerate(sorted(folder_path.iterdir())):
        if filepath.is_dir():
            continue

        old_name = filepath.name
        stem = filepath.stem
        ext = filepath.suffix

        if replace_from:
            stem = stem.replace(replace_from, replace_to)

        if prefix:
            stem = prefix + stem
        if suffix:
            stem = stem + suffix

        if pattern:
            stem = pattern.replace("{n}", str(i + 1).zfill(3)).replace("{name}", filepath.stem)

        new_name = stem + ext
        # Security: prevent path traversal via filename
        new_name = Path(new_name).name  # strip any directory components
        if not new_name or new_name.startswith("."):
            continue
        if new_name != old_name:
            new_path = filepath.parent / new_name
            filepath.rename(new_path)
            results.append({"old": old_name, "new": new_name})

    return results


def organize_downloads(downloads_path: str = "") -> dict:
    """Organize downloads folder by file type."""
    if not downloads_path:
        downloads_path = str(Path.home() / "Downloads")

    categories = {
        "Bilder": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
        "Dokumente": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".odt"],
        "Videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "Musik": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
        "Archive": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
        "Programme": [".exe", ".msi", ".dmg", ".deb", ".rpm"],
        "Code": [".py", ".js", ".html", ".css", ".json", ".xml", ".yml", ".yaml"],
    }

    moved = {}
    dl = Path(downloads_path)

    for filepath in dl.iterdir():
        if filepath.is_dir():
            continue

        ext = filepath.suffix.lower()
        target_category = None

        for category, extensions in categories.items():
            if ext in extensions:
                target_category = category
                break

        if target_category:
            target_dir = dl / target_category
            target_dir.mkdir(exist_ok=True)
            target_path = target_dir / filepath.name

            if not target_path.exists():
                shutil.move(str(filepath), str(target_path))
                moved.setdefault(target_category, []).append(filepath.name)

    total = sum(len(v) for v in moved.values())
    return {"moved_files": total, "categories": moved}


def merge_pdfs(pdf_paths: list[str], output_path: str = "") -> str:
    """Merge multiple PDFs into one."""
    from pypdf import PdfMerger

    merger = PdfMerger()
    for path in pdf_paths:
        merger.append(path)

    if not output_path:
        output_path = str(Path(pdf_paths[0]).parent / "merged.pdf")

    merger.write(output_path)
    merger.close()
    return output_path


def split_pdf(pdf_path: str, pages: str = "") -> list[str]:
    """Split a PDF. pages format: '1-3,5,7-10'"""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf_path)
    output_dir = Path(pdf_path).parent / "split"
    output_dir.mkdir(exist_ok=True)
    results = []

    if pages:
        # Parse page ranges
        page_nums = []
        for part in pages.split(","):
            part = part.strip()
            try:
                if "-" in part:
                    start, end = part.split("-", 1)
                    s, e = int(start), int(end)
                    if s < 1:
                        s = 1
                    page_nums.extend(range(s - 1, e))
                else:
                    page_nums.append(int(part) - 1)
            except ValueError:
                continue  # Skip invalid page specs

        writer = PdfWriter()
        for num in page_nums:
            if 0 <= num < len(reader.pages):
                writer.add_page(reader.pages[num])

        out = str(output_dir / f"pages_{pages.replace(',', '_')}.pdf")
        with open(out, "wb") as f:
            writer.write(f)
        results.append(out)
    else:
        # Split into individual pages
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            out = str(output_dir / f"page_{i + 1}.pdf")
            with open(out, "wb") as f:
                writer.write(f)
            results.append(out)

    return results


def disk_analysis(path: str = "C:/Users", timeout_sec: int = 30) -> list[dict]:
    """Analyze disk usage by file type with timeout protection.

    Scans directory tree with configurable timeout (default 30s) to prevent
    hanging on large drives or network shares.
    """
    err = _validate_scan_path(path)
    if err:
        return [{"error": err}]
    import time

    timeout_sec = max(5, min(120, timeout_sec))
    type_sizes = {}
    file_count = 0
    start_time = time.monotonic()

    skip_dirs = {
        "node_modules", "__pycache__", ".git", ".hg", ".svn",
        "AppData", "Windows", "$Recycle.Bin", "ProgramData",
        ".cache", ".npm", ".nuget", "venv", ".venv",
    }

    timed_out = False
    for root, dirs, files in os.walk(path):
        if time.monotonic() - start_time > timeout_sec:
            timed_out = True
            break
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs]
        for filename in files:
            try:
                filepath = os.path.join(root, filename)
                size = os.path.getsize(filepath)
                ext = os.path.splitext(filename)[1].lower() or "(kein)"
                type_sizes[ext] = type_sizes.get(ext, 0) + size
                file_count += 1
            except (PermissionError, OSError):
                continue

    sorted_types = sorted(type_sizes.items(), key=lambda x: x[1], reverse=True)
    result = [
        {"type": ext, "size_mb": round(size / 1024 / 1024, 1)}
        for ext, size in sorted_types[:20]
    ]
    if timed_out:
        result.insert(0, {"note": f"Scan nach {timeout_sec}s abgebrochen. {file_count} Dateien analysiert (Teilergebnis)."})
    return result


def clean_temp() -> dict:
    """Clean temporary files with proper error reporting.

    Reports: deleted count, freed space, skipped items (locked/in-use),
    and failed items (permission denied) — no silent failures.
    """
    temp_dirs = []
    seen = set()
    for env_var in ("TEMP", "TMP"):
        val = os.environ.get(env_var, "")
        if val:
            p = Path(val).resolve()
            if p not in seen:
                temp_dirs.append(p)
                seen.add(p)
    fallback = (Path.home() / "AppData" / "Local" / "Temp").resolve()
    if fallback not in seen:
        temp_dirs.append(fallback)

    deleted = 0
    freed_bytes = 0
    skipped = 0
    failed = 0
    skipped_unsafe_roots = 0

    for temp_dir in temp_dirs:
        if not _is_trusted_temp_root(temp_dir):
            skipped_unsafe_roots += 1
            logger.warning("Skipping untrusted temp root: %s", temp_dir)
            continue
        if not temp_dir.exists():
            continue
        try:
            items = list(temp_dir.iterdir())
        except PermissionError:
            failed += 1
            continue

        for item in items:
            try:
                if item.is_symlink():
                    skipped += 1
                    continue
                try:
                    item_resolved = item.resolve()
                except OSError:
                    failed += 1
                    continue
                if not _is_relative_to_path(item_resolved, temp_dir):
                    skipped += 1
                    continue
                if item.is_file():
                    size = item.stat().st_size
                    item.unlink()
                    deleted += 1
                    freed_bytes += size
                elif item.is_dir():
                    # Calculate size before deletion
                    dir_size = 0
                    try:
                        dir_size = sum(
                            f.stat().st_size for f in item.rglob("*")
                            if f.is_file() and not f.is_symlink() and _is_relative_to_path(f.resolve(), item_resolved)
                        )
                    except (PermissionError, OSError):
                        pass
                    # Try to remove — track partial failures
                    remaining = []
                    shutil.rmtree(item, onerror=lambda fn, p, exc: remaining.append(p))
                    if not item.exists():
                        deleted += 1
                        freed_bytes += dir_size
                    elif remaining:
                        # Partially cleaned
                        skipped += 1
                    else:
                        deleted += 1
                        freed_bytes += dir_size
            except PermissionError:
                skipped += 1  # File in use / locked
            except OSError:
                failed += 1

    return {
        "deleted_items": deleted,
        "freed_mb": round(freed_bytes / 1024 / 1024, 1),
        "skipped_locked": skipped,
        "failed": failed,
        "skipped_unsafe_roots": skipped_unsafe_roots,
    }


# ══════════════════════════════════════════════════
#  ARCHIVE (Phase 20) — ZIP / 7z erstellen & entpacken
# ══════════════════════════════════════════════════

def archive_create(source: str = "", output: str = "", format: str = "zip") -> str:
    """Create a ZIP archive from a file or folder."""
    if not source:
        return "Quellpfad fehlt."
    src = Path(source)
    if not src.exists():
        return f"Quelle nicht gefunden: {source}"

    if not output:
        output = str(src.parent / f"{src.stem}.zip")

    try:
        if format == "zip":
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
                if src.is_file():
                    zf.write(src, src.name)
                else:
                    for root, dirs, files in os.walk(src):
                        for file in files:
                            filepath = Path(root) / file
                            arcname = filepath.relative_to(src.parent)
                            zf.write(filepath, arcname)

            size_mb = round(Path(output).stat().st_size / 1024 / 1024, 2)
            return f"Archiv erstellt: {output} ({size_mb} MB)"
        else:
            return f"Format '{format}' nicht unterstützt. Verwende 'zip'."
    except Exception as e:
        return t("error.createFailed", error=str(e))


def _safe_archive_members(names, destination: Path) -> tuple[list[str], int]:
    """Return archive member names that stay inside the extraction destination."""
    safe: list[str] = []
    skipped = 0
    dest_path = destination.resolve()
    for name in names:
        member_name = str(name or "")
        try:
            member_path = (dest_path / member_name).resolve()
            member_path.relative_to(dest_path)
        except (OSError, ValueError):
            logger.warning("Archive path traversal blocked: %s", member_name)
            skipped += 1
            continue
        safe.append(member_name)
    return safe, skipped


def archive_extract(archive_path: str = "", destination: str = "") -> str:
    """Extract a ZIP archive."""
    if not archive_path:
        return "Archiv-Pfad fehlt."
    arc = Path(archive_path)
    if not arc.exists():
        return f"Archiv nicht gefunden: {archive_path}"

    if not destination:
        destination = str(arc.parent / arc.stem)

    try:
        ext = arc.suffix.lower()
        if ext == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                dest_path = Path(destination).resolve()
                safe_names, skipped = _safe_archive_members((m.filename for m in zf.infolist()), dest_path)
                safe_name_set = set(safe_names)
                safe_count = 0
                for member in zf.infolist():
                    if member.filename not in safe_name_set:
                        continue
                    zf.extract(member, destination)
                    safe_count += 1
            if skipped:
                return f"Entpackt: {safe_count} Dateien nach {destination} ({skipped} unsichere Einträge geblockt)"
            return f"Entpackt: {safe_count} Dateien nach {destination}"
        elif ext in (".7z",):
            # Try py7zr if available
            try:
                import py7zr
                with py7zr.SevenZipFile(archive_path, mode="r") as z:
                    safe_names, skipped = _safe_archive_members(z.getnames(), Path(destination))
                    if skipped:
                        return f"7z-Archiv nicht entpackt: {skipped} unsichere Einträge geblockt."
                    z.extractall(path=destination, targets=safe_names)
                return f"7z-Archiv entpackt nach {destination}"
            except ImportError:
                return "py7zr nicht installiert. Installiere mit: pip install py7zr"
        elif ext == ".rar":
            try:
                import rarfile
                with rarfile.RarFile(archive_path) as rf:
                    dest_path = Path(destination).resolve()
                    safe_names, skipped = _safe_archive_members((m.filename for m in rf.infolist()), dest_path)
                    safe_name_set = set(safe_names)
                    safe_count = 0
                    for member in rf.infolist():
                        if member.filename not in safe_name_set:
                            continue
                        rf.extract(member, destination)
                        safe_count += 1
                if skipped:
                    return f"RAR-Archiv entpackt nach {destination} ({skipped} unsichere Einträge geblockt)"
                return f"RAR-Archiv entpackt nach {destination}"
            except ImportError:
                return "rarfile nicht installiert. Installiere mit: pip install rarfile"
        elif ext in (".tar", ".gz", ".bz2", ".xz", ".tgz"):
            import tarfile
            with tarfile.open(archive_path) as tf:
                tf.extractall(destination, filter="data")
            return f"TAR-Archiv entpackt nach {destination}"
        else:
            return f"Unbekanntes Archiv-Format: {ext}"
    except Exception as e:
        return t("error.extractFailed", error=str(e))


def archive_list(archive_path: str = "") -> list[dict]:
    """List contents of an archive."""
    if not archive_path:
        return [{"error": "Archiv-Pfad fehlt."}]
    arc = Path(archive_path)
    if not arc.exists():
        return [{"error": t("error.notFound", path=str(archive_path))}]

    try:
        ext = arc.suffix.lower()
        if ext == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                return [
                    {
                        "name": info.filename,
                        "size_kb": round(info.file_size / 1024, 1),
                        "compressed_kb": round(info.compress_size / 1024, 1),
                        "is_dir": info.is_dir(),
                    }
                    for info in zf.infolist()[:50]
                ]
        return [{"error": f"Listing nur für ZIP unterstützt (war: {ext})"}]
    except Exception as e:
        return [{"error": str(e)}]


# ══════════════════════════════════════════════════
#  BACKUP SYSTEM (Phase 20)
# ══════════════════════════════════════════════════

BACKUP_CONFIG_PATH = LEXA_DATA_DIR / "backup_config.json"


def backup_create(source: str = "", destination: str = "", name: str = "") -> str:
    """Create a backup (ZIP) of a folder."""
    if not source:
        return "Quellordner fehlt."
    src = Path(source)
    if not src.exists():
        return f"Quelle nicht gefunden: {source}"

    if not destination:
        destination = str(Path.home() / "Backups")

    dest = Path(destination)
    dest.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = name or src.name
    backup_file = dest / f"backup_{backup_name}_{timestamp}.zip"

    try:
        file_count = 0
        total_size = 0
        with zipfile.ZipFile(str(backup_file), "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(src):
                # Skip common unnecessary dirs
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                    "node_modules", "__pycache__", ".git", "venv", ".venv",
                )]
                for file in files:
                    filepath = Path(root) / file
                    try:
                        arcname = filepath.relative_to(src)
                        zf.write(filepath, arcname)
                        file_count += 1
                        total_size += filepath.stat().st_size
                    except (PermissionError, OSError):
                        continue

        backup_size = round(backup_file.stat().st_size / 1024 / 1024, 2)
        original_size = round(total_size / 1024 / 1024, 2)

        # Save backup log
        _save_backup_log(str(backup_file), source, file_count, backup_size)

        return (
            f"Backup erstellt: {backup_file.name}\n"
            f"Dateien: {file_count} | Original: {original_size} MB | Komprimiert: {backup_size} MB"
        )
    except Exception as e:
        return t("error.backupFailed", error=str(e))


def _save_backup_log(backup_path: str, source: str, file_count: int, size_mb: float):
    """Save backup metadata to config."""
    try:
        config = {}
        if BACKUP_CONFIG_PATH.exists():
            config = json.loads(BACKUP_CONFIG_PATH.read_text())

        history = config.get("history", [])
        history.insert(0, {
            "path": backup_path,
            "source": source,
            "files": file_count,
            "size_mb": size_mb,
            "created": datetime.now().isoformat(),
        })
        config["history"] = history[:20]  # Keep last 20

        BACKUP_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    except Exception:
        pass


def backup_list() -> list[dict]:
    """List previous backups."""
    try:
        if not BACKUP_CONFIG_PATH.exists():
            return []
        config = json.loads(BACKUP_CONFIG_PATH.read_text())
        history = config.get("history", [])
        # Check which still exist
        for entry in history:
            entry["exists"] = Path(entry["path"]).exists()
        return history
    except Exception:
        return []


def backup_restore(backup_path: str = "", destination: str = "") -> str:
    """Restore a backup (extract ZIP to destination)."""
    if not backup_path:
        return "Backup-Pfad fehlt."
    return archive_extract(archive_path=backup_path, destination=destination)


# ══════════════════════════════════════════════════
#  BILD-KONVERTIERUNG (Phase 20) — Pillow
# ══════════════════════════════════════════════════

def image_convert(source: str = "", output_format: str = "png", quality: int = 85) -> str:
    """Convert image to different format."""
    if not source:
        return "Bildpfad fehlt."
    src = Path(source)
    if not src.exists():
        return f"Bild nicht gefunden: {source}"

    try:
        from PIL import Image
        img = Image.open(source)

        fmt = output_format.lower().strip(".")
        fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP", "bmp": "BMP", "gif": "GIF", "tiff": "TIFF", "ico": "ICO"}
        pil_format = fmt_map.get(fmt, fmt.upper())

        output_path = src.with_suffix(f".{fmt}")
        if output_path == src:
            output_path = src.with_stem(src.stem + "_converted").with_suffix(f".{fmt}")

        # Convert RGBA to RGB for JPEG
        if pil_format == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        save_kwargs = {}
        if pil_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = max(1, min(100, quality))
        if pil_format == "PNG":
            save_kwargs["optimize"] = True

        img.save(str(output_path), pil_format, **save_kwargs)
        size_kb = round(output_path.stat().st_size / 1024, 1)
        return f"Konvertiert: {output_path.name} ({size_kb} KB, {img.size[0]}x{img.size[1]})"
    except ImportError:
        return "Pillow nicht installiert. pip install Pillow"
    except Exception as e:
        return t("error.convertFailed", error=str(e))


def image_resize(source: str = "", width: int = 0, height: int = 0, quality: int = 85) -> str:
    """Resize an image. Keeps aspect ratio if only width or height given."""
    if not source:
        return "Bildpfad fehlt."
    src = Path(source)
    if not src.exists():
        return f"Bild nicht gefunden: {source}"

    try:
        from PIL import Image
        img = Image.open(source)
        orig_w, orig_h = img.size

        if width and not height:
            ratio = width / orig_w
            height = int(orig_h * ratio)
        elif height and not width:
            ratio = height / orig_h
            width = int(orig_w * ratio)
        elif not width and not height:
            return "Breite und/oder Höhe angeben."

        img_resized = img.resize((width, height), Image.LANCZOS)

        output_path = src.with_stem(src.stem + f"_{width}x{height}")
        save_kwargs = {}
        fmt = src.suffix.lower()
        if fmt in (".jpg", ".jpeg", ".webp"):
            save_kwargs["quality"] = quality
            if img_resized.mode == "RGBA":
                img_resized = img_resized.convert("RGB")

        img_resized.save(str(output_path), **save_kwargs)
        size_kb = round(output_path.stat().st_size / 1024, 1)
        return f"Skaliert: {output_path.name} ({width}x{height}, {size_kb} KB)"
    except ImportError:
        return "Pillow nicht installiert."
    except Exception as e:
        return t("error.resizeFailed", error=str(e))


def image_batch_resize(folder: str = "", width: int = 800, quality: int = 80) -> str:
    """Batch resize all images in a folder."""
    if not folder:
        return "Ordner-Pfad fehlt."
    folder_path = Path(folder)
    if not folder_path.exists():
        return f"Ordner nicht gefunden: {folder}"

    image_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
    output_dir = folder_path / "resized"
    output_dir.mkdir(exist_ok=True)

    converted = 0
    try:
        from PIL import Image
        for filepath in folder_path.iterdir():
            if filepath.is_file() and filepath.suffix.lower() in image_exts:
                try:
                    img = Image.open(filepath)
                    orig_w, orig_h = img.size
                    if orig_w <= width:
                        continue  # Skip smaller images
                    ratio = width / orig_w
                    new_h = int(orig_h * ratio)
                    img_resized = img.resize((width, new_h), Image.LANCZOS)

                    out_path = output_dir / filepath.name
                    save_kwargs = {}
                    if filepath.suffix.lower() in (".jpg", ".jpeg", ".webp"):
                        save_kwargs["quality"] = quality
                        if img_resized.mode == "RGBA":
                            img_resized = img_resized.convert("RGB")
                    img_resized.save(str(out_path), **save_kwargs)
                    converted += 1
                except Exception:
                    continue
    except ImportError:
        return "Pillow nicht installiert."

    return f"Batch-Resize: {converted} Bilder auf max. {width}px skaliert → {output_dir}"


def image_info(source: str = "") -> dict:
    """Get image metadata."""
    if not source:
        return {"error": "Bildpfad fehlt."}
    src = Path(source)
    if not src.exists():
        return {"error": t("error.notFound", path=str(source))}

    try:
        from PIL import Image
        img = Image.open(source)
        size_kb = round(src.stat().st_size / 1024, 1)
        return {
            "filename": src.name,
            "format": img.format,
            "mode": img.mode,
            "width": img.size[0],
            "height": img.size[1],
            "size_kb": size_kb,
        }
    except ImportError:
        return {"error": "Pillow nicht installiert."}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════
#  DATEI-INFOS (Phase 20)
# ══════════════════════════════════════════════════

def file_move(source: str = "", destination: str = "") -> dict:
    """Move a file or folder from source to destination."""
    if not source or not destination:
        return {"error": "Quell- und Zielpfad müssen angegeben werden."}

    src = Path(source)
    dst = Path(destination)

    if not src.exists():
        return {"error": t("file.notFound", path=source)}

    # Validate paths
    for p in (src, dst):
        err = _validate_scan_path(str(p.resolve()) if p.exists() else str(p.parent.resolve() if p.parent.exists() else p))
        if err and "nicht gefunden" not in err:
            return {"error": t("file.systemPath")}

    # Validate source is not traversal
    try:
        src.resolve()
    except (OSError, ValueError):
        return {"error": "Ungültiger Quellpfad."}

    # Destination parent must exist
    if not dst.is_dir() and not dst.parent.exists():
        return {"error": f"Zielverzeichnis existiert nicht: {dst.parent}"}

    try:
        result_path = shutil.move(str(src), str(dst))
        logger.info(f"file_move: {source} → {result_path}")
        return {"success": True, "data": t("file.moved", source=src.name, destination=str(result_path))}
    except Exception as e:
        logger.error(f"file_move failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}


def file_copy(source: str = "", destination: str = "") -> dict:
    """Copy a file or folder (recursively for directories)."""
    if not source or not destination:
        return {"error": "Quell- und Zielpfad müssen angegeben werden."}

    src = Path(source)
    dst = Path(destination)

    if not src.exists():
        return {"error": t("file.notFound", path=source)}

    # Validate paths
    for p in (src, dst):
        err = _validate_scan_path(str(p.resolve()) if p.exists() else str(p.parent.resolve() if p.parent.exists() else p))
        if err and "nicht gefunden" not in err:
            return {"error": t("file.systemPath")}

    # Destination parent must exist
    if not dst.is_dir() and not dst.parent.exists():
        return {"error": f"Zielverzeichnis existiert nicht: {dst.parent}"}

    try:
        if src.is_dir():
            result_path = shutil.copytree(str(src), str(dst))
        else:
            result_path = shutil.copy2(str(src), str(dst))
        logger.info(f"file_copy: {source} → {result_path}")
        return {"success": True, "data": t("file.copied", source=src.name, destination=str(result_path))}
    except Exception as e:
        logger.error(f"file_copy failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}


def file_delete(path: str = "") -> dict:
    """Delete a file or empty folder. NEVER uses shutil.rmtree."""
    if not path:
        return {"error": "Pfad fehlt."}

    p = Path(path)
    if not p.exists():
        return {"error": t("file.notFound", path=path)}

    # Validate path — block system directories
    err = _validate_scan_path(str(p.resolve()))
    if err and "nicht gefunden" not in err:
        return {"error": t("file.systemPath")}

    try:
        name = p.name
        if p.is_file():
            os.remove(str(p))
            logger.info(f"file_delete: Deleted file {path}")
            return {"success": True, "data": t("file.deleted", name=name)}
        elif p.is_dir():
            os.rmdir(str(p))  # Only empty dirs — safe
            logger.info(f"file_delete: Deleted empty folder {path}")
            return {"success": True, "data": t("file.deleted", name=name)}
        else:
            return {"error": "Unbekannter Dateityp."}
    except OSError as e:
        if "not empty" in str(e).lower() or "verzeichnis ist nicht leer" in str(e).lower() or e.errno == 39:
            return {"error": "Ordner ist nicht leer. Nur leere Ordner können gelöscht werden."}
        logger.error(f"file_delete failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}
    except Exception as e:
        logger.error(f"file_delete failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}


def file_open(path: str = "") -> dict:
    """Open a file with its default application."""
    if not path:
        return {"error": "Pfad fehlt."}

    p = Path(path)
    if not p.exists():
        return {"error": t("file.notFound", path=path)}

    # Block dangerous extensions
    blocked_exts = {".exe", ".bat", ".cmd", ".ps1", ".vbs"}
    if p.suffix.lower() in blocked_exts:
        return {"error": t("file.blocked", extension=p.suffix)}

    try:
        os.startfile(str(p))
        logger.info(f"file_open: Opened {path}")
        return {"success": True, "data": t("file.opened", name=p.name)}
    except Exception as e:
        logger.error(f"file_open failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}


def file_recent_downloads(count: int = 5) -> list[dict]:
    """List the N most recent files in the user's Downloads folder."""
    count = max(1, min(50, count))

    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        # Fallback via USERPROFILE
        userprofile = os.environ.get("USERPROFILE", "")
        if userprofile:
            downloads = Path(userprofile) / "Downloads"
        if not downloads.exists():
            return [{"error": "Downloads-Ordner nicht gefunden."}]

    try:
        files = [f for f in downloads.iterdir() if f.is_file()]
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        result = []
        for f in files[:count]:
            stat = f.stat()
            result.append({
                "name": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "extension": f.suffix.lower(),
            })
        return result
    except Exception as e:
        logger.error(f"file_recent_downloads failed: {e}", exc_info=True)
        return [{"error": str(e)}]


def folder_create(path: str = "") -> dict:
    """Create a new folder (with parents)."""
    if not path:
        return {"error": "Pfad fehlt."}

    if len(path) > 260:
        return {"error": "Pfad ist zu lang (max 260 Zeichen)."}

    p = Path(path)

    # Validate path — block system directories
    resolved = str(p.resolve()).lower()
    blocked = ["system32", "syswow64", "windows\\system", "program files\\windows defender"]
    if any(b in resolved for b in blocked):
        return {"error": t("file.systemPath")}

    try:
        p.mkdir(parents=True, exist_ok=True)
        logger.info(f"folder_create: Created {path}")
        return {"success": True, "data": t("file.created", path=str(p))}
    except Exception as e:
        logger.error(f"folder_create failed: {e}", exc_info=True)
        return {"error": t("error.generic", error=str(e))}


def file_write(path: str = "", content: str = "", create_dirs: bool = True) -> dict:
    """Create a new UTF-8 text/code file. Existing files are never overwritten."""
    if not path:
        raise ValueError("Pfad fehlt.")
    if not isinstance(content, str):
        raise ValueError("Inhalt muss Text sein.")
    if len(content) > _FILE_WRITE_MAX_CHARS:
        raise ValueError(f"Inhalt ist zu lang (max {_FILE_WRITE_MAX_CHARS} Zeichen).")
    if len(path) > 500:
        raise ValueError("Pfad ist zu lang (max 500 Zeichen).")

    p = Path(path).expanduser()
    if p.suffix.lower() in _FILE_WRITE_BLOCKED_EXTS:
        raise ValueError(t("file.blocked", extension=p.suffix))

    resolved = p.resolve()
    resolved_lower = str(resolved).lower()
    if ".." in path or any(part in resolved_lower for part in _FILE_WRITE_BLOCKED_PATH_PARTS):
        raise ValueError(t("file.systemPath"))
    if resolved.exists():
        if resolved.is_dir():
            raise ValueError("Ziel ist ein Ordner, keine Datei.")
        raise ValueError("Datei existiert bereits. Ich ueberschreibe sie nicht automatisch.")

    parent = resolved.parent
    if not parent.exists():
        if not create_dirs:
            raise ValueError("Zielordner existiert nicht.")
        parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise ValueError("Zielordner ist kein Ordner.")

    resolved.write_text(content, encoding="utf-8")
    logger.info("file_write: Created %s", resolved)
    return {
        "path": str(resolved),
        "chars": len(content),
        "bytes": len(content.encode("utf-8")),
        "created": True,
    }


def file_info(path: str = "") -> dict:
    """Get detailed file information."""
    if not path:
        return {"error": "Pfad fehlt."}
    p = Path(path)
    if not p.exists():
        return {"error": t("error.notFound", path=str(path))}

    try:
        stat = p.stat()
        return {
            "name": p.name,
            "extension": p.suffix,
            "size_kb": round(stat.st_size / 1024, 1),
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "is_file": p.is_file(),
            "is_dir": p.is_dir(),
            "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "parent": str(p.parent),
        }
    except Exception as e:
        return {"error": str(e)}


def folder_size(path: str = "") -> dict:
    """Calculate total folder size."""
    if not path:
        return {"error": "Pfad fehlt."}
    p = Path(path)
    if not p.exists():
        return {"error": t("error.notFound", path=str(path))}

    total = 0
    file_count = 0
    dir_count = 0

    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        dir_count += len(dirs)
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                file_count += 1
            except (PermissionError, OSError):
                continue

    return {
        "path": path,
        "total_mb": round(total / 1024 / 1024, 2),
        "total_gb": round(total / 1024 / 1024 / 1024, 3),
        "files": file_count,
        "folders": dir_count,
    }
