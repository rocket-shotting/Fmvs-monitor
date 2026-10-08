"""ROI별 샘플/기준 이미지 관리 창.

- OK/NG 이미지 매칭: OK·NG·무시 3종류
- 형상 검사 / 기준 화면과 다름: 기준(정상) 이미지
현재 화면에서 추가하거나, 파일(예: 과거 NG 사진)에서 가져와 ROI 크기에 맞춰 저장한다.
잘못 등록한 이미지는 다른 칸(OK/NG/무시)으로 끌어 놓거나 우클릭 메뉴로 옮길 수 있다."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from PIL import Image, ImageTk

import detectors
import paths
import worker
from capture import Grabber
from config import ROI
from i18n import tr
from ui_util import hidden_windows, modal

_THUMB = (150, 100)
_ASPECT_TOLERANCE = 0.15


class SamplesDialog:
    def __init__(self, master: tk.Misc, roi: ROI):
        self.master = master
        self.roi = roi
        self.is_match = roi.detector == "match"
        self.classes = {"ok": tr("OK (정상품 – 기준)"), "ng": tr("NG (불량품)"),
                        "skip": tr("무시 (셀 없음·이동 중·가려짐 – 판정하지 않을 화면)")}
        self._photos: List[ImageTk.PhotoImage] = []
        self.sections: Dict[str, dict] = {}
        self._drag: Optional[dict] = None

        top = self.top = tk.Toplevel(master)
        top.title(tr("샘플 이미지 – {name}  (ROI {w}×{h})", name=roi.name, w=roi.w, h=roi.h))
        top.geometry("860x700")
        top.minsize(600, 300)
        body = ttk.Frame(top, padding=10)
        body.pack(fill="both", expand=True)

        hint = tr("현재 화면 또는 파일(과거 NG 사진 등)에서 이미지를 등록합니다. 파일은 ROI 크기에 맞춰 저장됩니다.\n"
                  "· OK: 정상 제품 (위치·모양 편차가 있으면 여러 장)   · NG: 불량 제품 (접힘·찍힘·휨 등 유형별로)\n"
                  "· 무시: 셀이 없을 때·이동 중·가려진 화면 – 이것과 비슷하면 판정하지 않습니다 (빈 화면 오탐 방지)\n"
                  "· 잘못 등록했으면 이미지를 다른 칸으로 끌어 놓거나, 우클릭 → 이동")
        ttk.Label(body, text=hint, foreground="#555555", justify="left").pack(fill="x", pady=(0, 6))

        for cls, label in self.classes.items():
            self._build_section(body, cls, label)

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(8, 0))
        self.calib_label = ttk.Label(bottom, text="", justify="left", wraplength=640)
        self.calib_label.pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text=tr("닫기"), width=10, command=top.destroy).pack(side="right")
        top.bind("<Escape>", lambda _e: top.destroy())
        self._refresh()

    # ---------- 화면 구성 ----------
    def _build_section(self, parent, cls: str, label: str):
        box = ttk.LabelFrame(parent, text=label, padding=6)
        box.pack(fill="both", expand=True, pady=4)
        bar = ttk.Frame(box)
        bar.pack(fill="x")
        ttk.Button(bar, text=tr("현재 화면 추가"), command=lambda: self._add_from_screen(cls)).pack(side="left")
        ttk.Button(bar, text=tr("파일에서 가져오기"), command=lambda: self._add_from_files(cls)).pack(side="left", padx=4)
        ttk.Button(bar, text=tr("모두 삭제"), command=lambda: self._delete_all(cls)).pack(side="left")
        count = ttk.Label(bar, text="")
        count.pack(side="left", padx=10)

        canvas = tk.Canvas(box, height=_THUMB[1] + 40, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=scroll.set)
        canvas.pack(fill="x", pady=(4, 0))
        scroll.pack(fill="x")
        strip = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=strip, anchor="nw")
        strip.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.sections[cls] = {"count": count, "strip": strip, "box": box, "canvas": canvas}

    def _refresh(self):
        self._photos.clear()
        for cls, sec in self.sections.items():
            for child in sec["strip"].winfo_children():
                child.destroy()
            files = paths.reference_paths(self.roi.id, cls)
            sec["count"].configure(text=tr("{n}장", n=len(files)))
            if not files:
                ttk.Label(sec["strip"], text=tr("등록된 이미지 없음"), foreground="#999999").pack(padx=8, pady=30)
            for path in files:
                self._add_thumb(sec["strip"], path, cls)
        self._update_calibration()

    def _add_thumb(self, strip, path: str, cls: str):
        cell = ttk.Frame(strip, padding=3)
        cell.pack(side="left", anchor="n")
        size_ok = False
        photo = None
        try:
            with Image.open(path) as img:
                thumb = img.convert("RGB")
            size_ok = thumb.size == (self.roi.w, self.roi.h)
            thumb.thumbnail(_THUMB)
            photo = ImageTk.PhotoImage(thumb)
            self._photos.append(photo)
            pic = tk.Label(cell, image=photo, borderwidth=1, relief="solid", cursor="fleur")
        except Exception:
            pic = ttk.Label(cell, text=tr("(열 수 없음)"), cursor="fleur")
        pic.pack()
        pic.bind("<ButtonPress-1>", lambda e: self._drag_start(e, path, cls, photo))
        pic.bind("<B1-Motion>", self._drag_move)
        pic.bind("<ButtonRelease-1>", self._drag_end)
        pic.bind("<Button-3>", lambda e: self._context_menu(e, path, cls))
        name = os.path.basename(path)
        ttk.Label(cell, text=name if size_ok else tr("⚠ ROI와 크기 다름\n{name}", name=name),
                  foreground="#555555" if size_ok else "#b71c1c", font=("맑은 고딕", 8)).pack()  # i18n: skip
        ttk.Button(cell, text=tr("삭제"), width=6, command=lambda: self._delete_one(path)).pack()

    # ---------- 다른 칸으로 옮기기 (끌어 놓기 / 우클릭) ----------
    def _drag_start(self, e, path: str, cls: str, photo):
        self._drag = {"path": path, "cls": cls, "photo": photo, "x0": e.x_root, "y0": e.y_root,
                      "ghost": None, "target": None}

    def _drag_move(self, e):
        d = self._drag
        if d is None:
            return
        if d["ghost"] is None:
            if abs(e.x_root - d["x0"]) < 6 and abs(e.y_root - d["y0"]) < 6:
                return
            ghost = d["ghost"] = tk.Toplevel(self.top)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            try:
                ghost.attributes("-alpha", 0.75)
            except tk.TclError:
                pass
            if d["photo"] is not None:
                tk.Label(ghost, image=d["photo"], borderwidth=2, relief="solid").pack()
            else:
                tk.Label(ghost, text=tr("이미지"), padx=10, pady=10).pack()
        d["ghost"].geometry(f"+{e.x_root + 12}+{e.y_root + 12}")
        target = self._section_at(e.x_root, e.y_root)
        if target != d["target"]:
            d["target"] = target
            self._show_drop_hint(target if target != d["cls"] else None)

    def _drag_end(self, e):
        d, self._drag = self._drag, None
        if d is None:
            return
        self._show_drop_hint(None)
        if d["ghost"] is None:
            return
        d["ghost"].destroy()
        target = self._section_at(e.x_root, e.y_root)
        if target and target != d["cls"]:
            self._move(d["path"], target)

    def _section_at(self, x: int, y: int) -> Optional[str]:
        widget = self.top.winfo_containing(x, y)
        if widget is None:
            return None
        name = str(widget)
        for cls, sec in self.sections.items():
            box = str(sec["box"])
            if name == box or name.startswith(box + "."):
                return cls
        return None

    def _show_drop_hint(self, target: Optional[str]):
        for cls, sec in self.sections.items():
            n = len(paths.reference_paths(self.roi.id, cls))
            if cls == target:
                sec["count"].configure(text=tr("{n}장   ⬇ 여기에 놓으면 '{target}'(으)로 이동", n=n,
                                                  target=self.classes[cls].split(' (')[0]),
                                       foreground="#b71c1c")
            else:
                sec["count"].configure(text=tr("{n}장", n=n), foreground="")

    def _context_menu(self, e, path: str, cls: str):
        menu = tk.Menu(self.top, tearoff=False)
        for target, label in self.classes.items():
            if target != cls:
                menu.add_command(label=tr("→ {target}(으)로 이동", target=label.split(' (')[0]),
                                 command=lambda t=target: self._move(path, t))
        menu.add_separator()
        menu.add_command(label=tr("삭제"), command=lambda: self._delete_one(path))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def _move(self, path: str, target: str):
        """샘플 이미지를 다른 분류(OK/NG/무시)로 옮긴다 (파일 이름만 바뀌고 이미지는 그대로)."""
        try:
            os.replace(path, paths.new_reference_path(self.roi.id, target))
        except OSError as e:
            messagebox.showerror(tr("이동 실패"), str(e), parent=self.top)
        self._refresh()

    def _update_calibration(self):
        samples = worker.load_samples(self.roi.id)
        if not samples["ok"]:
            self.calib_label.configure(text=tr("⚠ OK(정상품) 샘플이 없어 판정하지 않습니다. OK 이미지를 먼저 등록하세요."),
                                       foreground="#b71c1c")
            return
        lines = []
        warn = False
        try:
            self.calib_label.configure(text=tr("샘플로 판정 정확도 자체 검증 중…"), foreground="#555555")
            self.top.update_idletasks()
            if self.is_match:
                p = detectors.normalize_params("match", self.roi.params)
                calib = detectors.match_calibration(samples, (self.roi.h, self.roi.w), p["max_shift"])
                manual = p["ok_threshold"] > 0
                lines.append(tr("자동 계산 OK 허용 거리: {value}", value=f"{calib['threshold']:.2f}")
                             + (tr("  (이 ROI는 수동 값 {value} 사용 중)", value=f"{p['ok_threshold']:.2f}")
                                if manual else tr("  ← 현재 사용 중")))
                lines.append(calib["quality"])
                warn = calib["quality"].startswith("⚠")
            check = detectors.self_check(self.roi.detector, self.roi.params, samples)
            lines.append(check["summary"])
            warn = warn or check["summary"].startswith("⚠")
        except Exception as e:
            lines.append(tr("자체 검증 실패: {error}", error=e))
            warn = True
        if not samples["skip"] and self.roi.still_only:
            lines.append(tr("💡 셀이 없을 때 화면을 '무시'로 1장 이상 등록하면 빈 화면 오탐이 사라집니다."))
        self.calib_label.configure(text="\n".join(lines), foreground="#b71c1c" if warn else "#1b5e20")

    # ---------- 추가/삭제 ----------
    def _add_from_screen(self, cls: str):
        r = self.roi
        try:
            with hidden_windows(self.top, self.master, delay=0.4):
                with Grabber() as g:
                    frame = g.grab(r.x, r.y, r.w, r.h)
            worker.save_png(frame, paths.new_reference_path(r.id, cls))
        except Exception as e:
            self._regrab()
            messagebox.showerror(tr("캡처 실패"), str(e), parent=self.top)
            return
        self._regrab()
        self._refresh()

    def _add_from_files(self, cls: str):
        files = filedialog.askopenfilenames(
            parent=self.top, title=tr("{label} 이미지 선택", label=self.classes[cls]),
            filetypes=[(tr("이미지"), "*.png *.jpg *.jpeg *.bmp"), (tr("모든 파일"), "*.*")])
        if not files:
            return
        target = (self.roi.w, self.roi.h)
        loaded, failed, mismatched = [], [], []
        for f in files:
            try:
                with Image.open(f) as img:
                    rgb = img.convert("RGB")
            except Exception:
                failed.append(os.path.basename(f))
                continue
            ratio_img, ratio_roi = rgb.width / rgb.height, target[0] / target[1]
            if abs(ratio_img - ratio_roi) / ratio_roi > _ASPECT_TOLERANCE:
                mismatched.append(f"{os.path.basename(f)} ({rgb.width}×{rgb.height})")
            loaded.append(rgb)
        if mismatched and not messagebox.askyesno(
                tr("비율 확인"),
                tr("ROI({w}×{h})와 가로세로 비율이 다른 이미지가 있습니다:\n", w=target[0], h=target[1])
                + "\n".join(mismatched[:8]) +
                tr("\n\nROI 크기로 늘려서 저장하면 판정이 부정확할 수 있습니다.\n"
                   "FMVS 화면에서 ROI 영역만 잘라낸 이미지를 권장합니다. 그래도 등록할까요?"), parent=self.top):
            return
        for rgb in loaded:
            if rgb.size != target:
                rgb = rgb.resize(target, Image.LANCZOS)
            rgb.save(paths.new_reference_path(self.roi.id, cls))
        if failed:
            messagebox.showwarning(tr("일부 실패"), tr("열 수 없는 파일:\n") + "\n".join(failed), parent=self.top)
        self._refresh()

    def _delete_one(self, path: str):
        try:
            os.remove(path)
        except OSError as e:
            messagebox.showerror(tr("삭제 실패"), str(e), parent=self.top)
        self._refresh()

    def _delete_all(self, cls: str):
        if not paths.reference_paths(self.roi.id, cls):
            return
        if messagebox.askyesno(tr("확인"), tr("{label} 이미지를 모두 삭제할까요?", label=self.classes[cls]), parent=self.top):
            paths.delete_references(self.roi.id, cls)
            self._refresh()

    def _regrab(self):
        try:
            self.top.lift()
            self.top.grab_set()
            self.top.focus_force()
        except tk.TclError:
            pass

    def run(self):
        modal(self.top, self.master)


def manage_samples(master: tk.Misc, roi: ROI) -> None:
    SamplesDialog(master, roi).run()
