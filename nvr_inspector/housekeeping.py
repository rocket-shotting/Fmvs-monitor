"""보관 기간 관리: 로그·스냅샷·리포트를 보관 기간(최대 15일)이 지나면 삭제한다.
샘플/기준 이미지(refs)와 설정 파일은 삭제하지 않는다."""
import logging
import os
import time
from typing import Iterable

import paths

log = logging.getLogger(__name__)


def purge_old_files(directories: Iterable[str], days: int, now: float = None) -> int:
    """directories 안에서 수정 시각이 days일보다 오래된 파일을 삭제. 반환: 삭제한 파일 수."""
    cutoff = (time.time() if now is None else now) - days * 86400
    removed = 0
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError as e:
                log.warning("보관 기간 정리 실패 %s: %s", path, e)
    return removed


def purge(days: int) -> int:
    """로그·스냅샷·리포트 폴더 정리."""
    return purge_old_files((paths.LOG_DIR, paths.SNAPSHOT_DIR, paths.REPORT_DIR), days)
