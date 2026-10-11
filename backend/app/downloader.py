"""Robust Binance historical archive downloader.

Features:
- Bounded concurrency with asyncio.Semaphore
- Timeouts & bounded retries with exponential backoff
- Atomic file writes (.tmp -> target)
- Verification against published SHA-256 .CHECKSUM files
- Archive reuse (skips verified existing archives)
- Cancellation token support
- Original raw archive preservation in data/raw/{symbol}/
- Detailed progress callback and source manifest generation
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import httpx

from backend.app.config import (
    RAW_DATA_DIR,
    MANIFESTS_DIR,
    BINANCE_ARCHIVE_BASE,
    DEFAULT_START_DATE,
    DEFAULT_END_DATE,
)

logger = logging.getLogger(__name__)


def generate_month_list(
    start_year: int = 2022,
    start_month: int = 10,
    end_year: int = 2026,
    end_month: int = 9,
) -> List[str]:
    """Generate list of 'YYYY-MM' strings for the archive range."""
    months = []
    current_year = start_year
    current_month = start_month

    while (current_year < end_year) or (
        current_year == end_year and current_month <= end_month
    ):
        months.append(f"{current_year:04d}-{current_month:02d}")
        if current_month == 12:
            current_year += 1
            current_month = 1
        else:
            current_month += 1

    return months


def calculate_sha256(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file in streaming chunks."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest().lower()


class ArchiveDownloader:
    def __init__(
        self,
        symbol: str,
        interval: str = "1h",
        months: Optional[List[str]] = None,
        max_concurrency: int = 4,
        max_retries: int = 3,
        timeout_seconds: float = 30.0,
    ):
        self.symbol = symbol.upper()
        self.interval = interval
        last = DEFAULT_END_DATE - __import__("datetime").timedelta(seconds=1)
        self.months = months or generate_month_list(
            DEFAULT_START_DATE.year, DEFAULT_START_DATE.month, last.year, last.month
        )
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        self.symbol_raw_dir = RAW_DATA_DIR / self.symbol
        self.symbol_raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_file = MANIFESTS_DIR / f"{self.symbol}_manifest.json"

        self._cancel_requested = False

    def request_cancellation(self):
        """Signal cancellation of ongoing download."""
        self._cancel_requested = True

    async def fetch_checksum(self, client: httpx.AsyncClient, ym: str) -> Optional[str]:
        """Fetch published SHA-256 checksum from Binance Vision."""
        url = f"{BINANCE_ARCHIVE_BASE}/{self.symbol}/{self.interval}/{self.symbol}-{self.interval}-{ym}.zip.CHECKSUM"
        for attempt in range(self.max_retries):
            if self._cancel_requested:
                return None
            try:
                resp = await client.get(url, timeout=self.timeout_seconds)
                if resp.status_code == 200:
                    text = resp.text.strip()
                    # format: "<hash>  <filename>" or "<hash>"
                    parts = text.split()
                    if parts:
                        return parts[0].strip().lower()
                elif resp.status_code == 404:
                    logger.warning(f"Checksum not found for {self.symbol} {ym}")
                    return None
            except Exception as e:
                logger.warning(
                    f"Error fetching checksum for {self.symbol} {ym} (attempt {attempt+1}/{self.max_retries}): {e}"
                )
                await asyncio.sleep(0.5 * (2**attempt))
        return None

    async def download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        dest_path: Path,
        expected_sha: Optional[str],
    ) -> Dict[str, Any]:
        """Download file atomically and verify SHA-256."""
        if not expected_sha or len(expected_sha) != 64:
            return {
                "status": "failed",
                "error": "Published SHA-256 checksum unavailable",
            }
        temp_path = dest_path.with_suffix(".tmp")

        # Check if target file already exists and is valid
        if dest_path.exists():
            actual_sha = calculate_sha256(dest_path)
            if expected_sha and actual_sha == expected_sha:
                return {
                    "status": "verified",
                    "reused": True,
                    "actual_sha": actual_sha,
                    "size": dest_path.stat().st_size,
                }
            elif not expected_sha and dest_path.stat().st_size > 0:
                return {
                    "status": "unverified",
                    "reused": True,
                    "actual_sha": actual_sha,
                    "size": dest_path.stat().st_size,
                }

        for attempt in range(self.max_retries):
            if self._cancel_requested:
                if temp_path.exists():
                    temp_path.unlink()
                return {"status": "cancelled", "error": "Operation cancelled"}

            try:
                async with client.stream(
                    "GET", url, timeout=self.timeout_seconds
                ) as response:
                    if response.status_code != 200:
                        raise Exception(f"HTTP {response.status_code}")

                    with open(temp_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if self._cancel_requested:
                                temp_path.unlink(missing_ok=True)
                                return {
                                    "status": "cancelled",
                                    "error": "Operation cancelled",
                                }
                            f.write(chunk)

                # Check SHA-256
                actual_sha = calculate_sha256(temp_path)
                if expected_sha and actual_sha != expected_sha:
                    temp_path.unlink(missing_ok=True)
                    raise Exception(
                        f"Checksum mismatch: expected {expected_sha}, got {actual_sha}"
                    )

                # Atomic rename
                temp_path.replace(dest_path)
                return {
                    "status": "verified" if expected_sha else "completed",
                    "reused": False,
                    "actual_sha": actual_sha,
                    "size": dest_path.stat().st_size,
                }
            except Exception as e:
                temp_path.unlink(missing_ok=True)
                logger.warning(
                    f"Download error {url} (attempt {attempt+1}/{self.max_retries}): {e}"
                )
                if attempt == self.max_retries - 1:
                    return {"status": "failed", "error": str(e)}
                await asyncio.sleep(1.0 * (2**attempt))

        return {"status": "failed", "error": "Max retries exceeded"}

    async def download_all(
        self, progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Download all monthly archives for symbol with progress reporting and manifest creation."""
        self._cancel_requested = False
        manifest_entries: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(self.max_concurrency)
        total_months = len(self.months)
        completed_count = 0
        failed_count = 0

        limits = httpx.Limits(
            max_keepalive_connections=self.max_concurrency,
            max_connections=self.max_concurrency * 2,
        )
        async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:

            async def process_month(ym: str) -> Dict[str, Any]:
                nonlocal completed_count, failed_count
                if self._cancel_requested:
                    return {"ym": ym, "status": "cancelled"}

                async with semaphore:
                    if self._cancel_requested:
                        return {"ym": ym, "status": "cancelled"}

                    zip_filename = f"{self.symbol}-{self.interval}-{ym}.zip"
                    dest_zip = self.symbol_raw_dir / zip_filename
                    zip_url = f"{BINANCE_ARCHIVE_BASE}/{self.symbol}/{self.interval}/{zip_filename}"
                    chk_url = f"{zip_url}.CHECKSUM"

                    # 1. Fetch checksum
                    expected_sha = await self.fetch_checksum(client, ym)

                    # Preserve checksum file alongside raw archive
                    if expected_sha:
                        chk_file = self.symbol_raw_dir / f"{zip_filename}.CHECKSUM"
                        chk_file.write_text(f"{expected_sha}  {zip_filename}\n")

                    # 2. Download zip
                    res = await self.download_file(
                        client, zip_url, dest_zip, expected_sha
                    )

                    entry = {
                        "filename": zip_filename,
                        "url": zip_url,
                        "checksum_url": chk_url,
                        "expected_sha256": expected_sha or "",
                        "actual_sha256": res.get("actual_sha", ""),
                        "checksum_verified": res.get("status") == "verified",
                        "size_bytes": res.get("size", 0),
                        "downloaded_at": datetime.now(timezone.utc).isoformat(),
                        "status": res.get("status", "failed"),
                    }
                    if res.get("error"):
                        entry["error"] = res["error"]
                        failed_count += 1
                    else:
                        completed_count += 1

                    manifest_entries.append(entry)

                    if progress_callback:
                        progress_callback(
                            {
                                "symbol": self.symbol,
                                "completed_files": completed_count,
                                "total_files": total_months,
                                "current_file": zip_filename,
                                "percent": round(
                                    (completed_count / total_months) * 100, 1
                                ),
                                "status": "downloading",
                            }
                        )
                    return entry

            tasks = [process_month(ym) for ym in self.months]
            await asyncio.gather(*tasks)

        # Write manifest file
        verified_count = sum(1 for e in manifest_entries if e.get("checksum_verified"))
        manifest_data = {
            "symbol": self.symbol,
            "archive_url_base": f"{BINANCE_ARCHIVE_BASE}/{self.symbol}/{self.interval}",
            "total_files": total_months,
            "verified_files": verified_count,
            "failed_files": failed_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": sorted(manifest_entries, key=lambda x: x["filename"]),
        }

        from backend.app.storage import atomic_json

        atomic_json(self.manifest_file, manifest_data)

        return {
            "symbol": self.symbol,
            "total": total_months,
            "completed": completed_count,
            "verified": verified_count,
            "failed": failed_count,
            "cancelled": self._cancel_requested,
            "manifest_path": str(self.manifest_file),
        }
