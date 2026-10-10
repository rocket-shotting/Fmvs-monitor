"""NVR 화면에 표시된 시간 읽기 (스냅샷 파일 이름·팝업에 'NVR 화면 시간' 사용).

- 라이브(LIVE) 화면: 오른쪽 위 흰 글씨  2026-10-10 10:56:49  (날짜+시간)
- 재생(SEARCH) 화면: 왼쪽 아래 노란 글씨  08:46:36           (시간만 – 날짜는 설정의 '재생 날짜', 비우면 오늘)

설정에서 '시간 표시 위치'(사각형)를 등록하면, NG가 날 때 그 부분을 캡처해 글자색(흰/노랑)만 남기고
3배 확대한 뒤 Windows 내장 OCR(Windows.Media.Ocr, 추가 설치 없음)로 읽는다.
읽기에 실패하면 PC 시간을 쓰고 '(PC)'로 표시한다. 읽기는 NG 순간에만 하며 같은 화면은 1초간 재사용한다."""
import hashlib
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import date, datetime
from typing import Optional, Tuple

import numpy as np

import winutil

log = logging.getLogger(__name__)

KINDS = ("live", "search")
_FULL = re.compile(r"(20\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})\D{1,4}(\d{1,2})\D{0,2}(\d{2})\D{0,2}(\d{2})")
_TIME = re.compile(r"(\d{1,2})\s*[:;.]\s*(\d{2})\s*[:;.]\s*(\d{2})")
_CACHE_SEC = 1.0
_TIMEOUT = 8.0

# Windows PowerShell 5.1에서 WinRT OCR 호출 (인자: 이미지 경로) – 결과 문자열을 한 줄로 출력
_PS_SCRIPT = r"""
param([string]$Path)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('en-US')) }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()
Write-Output ($result.Text -replace '\s+', ' ')
"""

_cache: dict = {}


def preprocess(rgb: np.ndarray, kind: str) -> np.ndarray:
    """글자색만 남겨 흰 바탕에 검은 글씨로 + 3배 확대 (OCR 정확도 향상). 반환: 회색조 uint8."""
    img = rgb.astype(np.int16)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    if kind == "search":       # 노란 글씨: R·G 높고 B 낮음
        text = (r > 150) & (g > 130) & (b < 120) & (np.abs(r - g) < 90)
    else:                      # 흰 글씨: 밝고 무채색
        text = (r > 170) & (g > 170) & (b > 170) & (img.max(axis=2) - img.min(axis=2) < 60)
    out = np.where(text, 0, 255).astype(np.uint8)
    out = np.pad(out, 6, constant_values=255)
    return np.repeat(np.repeat(out, 3, axis=0), 3, axis=1)


def parse(text: str, kind: str, playback_date: str = "", today: Optional[date] = None) -> Optional[datetime]:
    """OCR 문자열 → 날짜·시간. 라이브는 날짜+시간, 재생은 시간 + 재생 날짜(없으면 오늘)."""
    t = (text or "").replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    try:
        m = _FULL.search(t)
        if m:
            y, mo, d, hh, mm, ss = (int(v) for v in m.groups())
            return datetime(y, mo, d, hh, mm, ss)
        if kind == "live":
            return None
        m = _TIME.search(t)
        if not m:
            return None
        hh, mm, ss = (int(v) for v in m.groups())
        base = today or date.today()
        if playback_date.strip():
            base = datetime.strptime(playback_date.strip(), "%Y-%m-%d").date()
        return datetime(base.year, base.month, base.day, hh, mm, ss)
    except ValueError:
        return None


def ocr_image(gray: np.ndarray) -> str:
    """Windows 내장 OCR로 글자 읽기 (Windows가 아니거나 실패하면 '')."""
    if not winutil.IS_WINDOWS:
        return ""
    from PIL import Image
    tmpdir = tempfile.mkdtemp(prefix="fmvs_ocr_")
    img_path = os.path.join(tmpdir, "time.png")
    ps_path = os.path.join(tmpdir, "ocr.ps1")
    try:
        Image.fromarray(gray).save(img_path)
        with open(ps_path, "w", encoding="utf-8-sig") as f:
            f.write(_PS_SCRIPT)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-File", ps_path, img_path],
                             capture_output=True, timeout=_TIMEOUT, creationflags=flags)
        out = res.stdout.decode("utf-8", "replace").strip()
        if res.returncode != 0 and not out:
            log.warning("NVR 시간 OCR 실패: %s", res.stderr.decode("utf-8", "replace")[-300:])
        return out
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("NVR 시간 OCR 실행 실패: %s", e)
        return ""
    finally:
        for p in (img_path, ps_path):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass


def read(source: dict, rgb: np.ndarray, playback_date: str = "") -> Tuple[Optional[datetime], str]:
    """시간 표시 영역 이미지(rgb)를 읽어 (시간 또는 None, OCR 원문)."""
    kind = source.get("kind", "live")
    gray = preprocess(rgb, kind)
    key = (kind, hashlib.md5(gray.tobytes()).hexdigest())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_SEC:
        text = hit[1]
    else:
        text = ocr_image(gray)
        _cache.clear()
        _cache[key] = (time.monotonic(), text)
    return parse(text, kind, playback_date), text


class OcrQueue:
    """시간 읽기(OCR)를 검출 스레드 밖에서 처리하는 대기열 (PowerShell 실행에 1~5초 걸리므로).
    submit(src, rgb, playback_date, callback): 읽은 뒤 callback(when 또는 None, text)을 이 스레드에서 호출."""

    def __init__(self, max_pending: int = 20):
        import queue
        import threading
        self._q = queue.Queue(maxsize=max_pending)
        self._thread = threading.Thread(target=self._run, name="nvr-ocr", daemon=True)
        self._thread.start()

    def submit(self, source: dict, rgb: np.ndarray, playback_date: str, callback) -> bool:
        try:
            self._q.put_nowait((source, rgb, playback_date, callback))
            return True
        except Exception:            # 대기열이 가득 차면 버림 (PC 시간 유지)
            log.warning("NVR 시간 읽기 대기열이 가득 차 건너뜀")
            return False

    def _run(self):
        while True:
            source, rgb, playback_date, callback = self._q.get()
            try:
                when, text = read(source, rgb, playback_date)
            except Exception as e:
                when, text = None, str(e)
            try:
                callback(when, text)
            except Exception:
                log.exception("NVR 시간 적용 실패")


_queue: Optional[OcrQueue] = None


def ocr_queue() -> OcrQueue:
    global _queue
    if _queue is None:
        _queue = OcrQueue()
    return _queue


def resolve(roi, sources: list) -> Optional[dict]:
    """ROI가 쓸 시간 표시 영역. roi.time_source: 'auto'(가장 가까운 영역) | 'pc' | 영역 이름."""
    choice = getattr(roi, "time_source", "auto") or "auto"
    if choice == "pc" or not sources:
        return None
    if choice != "auto":
        return next((s for s in sources if s.get("name") == choice), None)
    cx, cy = roi.x + roi.w / 2, roi.y + roi.h / 2
    return min(sources, key=lambda s: (s["x"] + s["w"] / 2 - cx) ** 2 + (s["y"] + s["h"] / 2 - cy) ** 2)


def parse_sources(value) -> list:
    """설정 값 검증: [{name, kind, x, y, w, h}, ...]"""
    out, names = [], set()
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            src = {"name": str(item.get("name") or "").strip(), "kind": item.get("kind", "live"),
                   "x": int(item["x"]), "y": int(item["y"]), "w": int(item["w"]), "h": int(item["h"])}
        except (KeyError, TypeError, ValueError):
            continue
        if src["kind"] not in KINDS or src["w"] < 8 or src["h"] < 6 or not src["name"] or src["name"] in names:
            continue
        names.add(src["name"])
        out.append(src)
    return out
