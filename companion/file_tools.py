"""Lexa AI — Datei-Tools
Duplikat-Finder, Batch-Rename, PDF-Bearbeitung, Backup, Download-Organizer
"""

import os
import hashlib
import shutil
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("lexa.files")


def find_duplicates(search_path: str = "C:/Users", max_files: int = 1000) -> list[dict]:
    """Find duplicate files by hash."""
    hashes = {}
    duplicates = []
    count = 0

    for root, dirs, files in os.walk(search_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".git", "AppData", "Windows", "venv",
        )]
        for filename in files:
            if count >= max_files:
                break
            filepath = os.path.join(root, filename)
            try:
                size = os.path.getsize(filepath)
                if size < 100 or size > 500_000_000:  # Skip tiny/huge files
                    continue
                # Hash first 8KB for speed
                with open(filepath, "rb") as f:
                    file_hash = hashlib.md5(f.read(8192)).hexdigest()
                key = f"{size}_{file_hash}"
                if key in hashes:
                    duplicates.append({
                        "original": hashes[key],
                        "duplicate": filepath,
                        "size_mb": round(size / 1024 / 1024, 2),
                    })
                else:
                    hashes[key] = filepath
                count += 1
            except (PermissionError, OSError):
                continue

    return sorted(duplicates, key=lambda x: x["size_mb"], reverse=True)[:20]


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
            if "-" in part:
                start, end = part.split("-")
                page_nums.extend(range(int(start) - 1, int(end)))
            else:
                page_nums.append(int(part) - 1)

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


def disk_analysis(path: str = "C:/Users") -> list[dict]:
    """Analyze disk usage by file type."""
    type_sizes = {}

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
            "node_modules", "__pycache__", ".git", "AppData",
        )]
        for filename in files:
            try:
                filepath = os.path.join(root, filename)
                size = os.path.getsize(filepath)
                ext = os.path.splitext(filename)[1].lower() or "(kein)"
                type_sizes[ext] = type_sizes.get(ext, 0) + size
            except (PermissionError, OSError):
                continue

    sorted_types = sorted(type_sizes.items(), key=lambda x: x[1], reverse=True)
    return [
        {"type": ext, "size_mb": round(size / 1024 / 1024, 1)}
        for ext, size in sorted_types[:20]
    ]


def clean_temp() -> dict:
    """Clean temporary files."""
    temp_dirs = [
        Path(os.environ.get("TEMP", "")),
        Path(os.environ.get("TMP", "")),
        Path.home() / "AppData" / "Local" / "Temp",
    ]

    deleted = 0
    freed_bytes = 0

    for temp_dir in temp_dirs:
        if not temp_dir.exists():
            continue
        for item in temp_dir.iterdir():
            try:
                if item.is_file():
                    size = item.stat().st_size
                    item.unlink()
                    deleted += 1
                    freed_bytes += size
                elif item.is_dir():
                    size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                    shutil.rmtree(item, ignore_errors=True)
                    deleted += 1
                    freed_bytes += size
            except (PermissionError, OSError):
                continue

    return {
        "deleted_items": deleted,
        "freed_mb": round(freed_bytes / 1024 / 1024, 1),
    }
