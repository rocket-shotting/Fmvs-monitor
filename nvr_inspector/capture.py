"""화면 캡처. mss가 있으면 mss(빠름), 없으면 Pillow ImageGrab 사용.
mss 인스턴스는 스레드마다 따로 만들어야 하므로 Grabber를 스레드별로 생성한다."""
import numpy as np

import winutil

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None


class Grabber:
    def __init__(self):
        self._sct = mss.mss() if mss is not None else None

    def grab(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """화면 영역을 RGB uint8 (h, w, 3) 배열로 반환."""
        if self._sct is not None:
            shot = self._sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
            bgra = np.asarray(shot)
            return np.ascontiguousarray(bgra[:, :, 2::-1])
        from PIL import ImageGrab
        img = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
        return np.asarray(img)

    def grab_virtual_screen(self):
        """모든 모니터를 합친 전체 화면 (PIL.Image, left, top)."""
        from PIL import Image
        if self._sct is not None:
            mon = self._sct.monitors[0]
            shot = self._sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            return img, mon["left"], mon["top"]
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True).convert("RGB")
        left, top = winutil.virtual_screen_origin()
        return img, left, top

    def close(self):
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
