"""ROI별 샘플/기준 이미지 관리 창.

- OK/NG 이미지 매칭: OK·NG·무시 3종류
- 형상 검사 / 기준 화면과 다름: 기준(정상) 이미지
현재 화면에서 추가하거나, 파일(예: 과거 NG 사진)에서 가져와 ROI 크기에 맞춰 저장한다."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List

from PIL import Image, ImageTk

import detectors
import paths
import worker
from capture import Grabber
from config import ROI
from ui_util import hidden_windows, modal

_THUMB = (150, 100)
_ASPECT_TOLERANCE = 0.15


class SamplesDialog:
    def __init__(self, master: tk.Misc, roi: ROI):
        self.master = master
        self.roi = roi
        self.is_match = roi.detector == "match"
        self.classes = (dict(detectors.SAMPLE_CLASSES) if self.is_match
                        else {"ok": "기준 이미지 (정상품)"})
        self._photos: List[ImageTk.PhotoImage] = []
        self.sections: Dict[str, dict] = {}

        top = self.top = tk.Toplevel(master)
        top.title(f"샘플 이미지 – {roi.name}  (ROI {roi.w}×{roi.h})")
        top.geometry("820x640" if self.is_match else "820x330")
        top.minsize(600, 300)
        body = ttk.Frame(top, padding=10)
        body.pack(fill="both", expand=True)

        hint = ("현재 화면 또는 파일(과거 NG 사진 등)에서 이미지를 등록합니다. 파일은 ROI 크기에 맞춰 저장됩니다.\n"
                "· OK: 정상 제품 (모양·위치 편차가 있으면 여러 장)   · NG: 불량 제품   "
                "· 무시: 제품 없음/이동 중/가려짐 등 판정하지 않을 화면"
                if self.is_match else
                "정상 제품 화면을 등록합니다. 정상품의 모양 편차가 있으면 여러 장 등록하면 가장 비슷한 것과 비교합니다.")
        ttk.Label(body, text=hint, foreground="#555555", justify="left").pack(fill="x", pady=(0, 6))

        for cls, label in self.classes.items():
            self._build_section(body, cls, label)

        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(8, 0))
        self.calib_label = ttk.Label(bottom, text="", justify="left", wraplength=640)
        self.calib_label.pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="닫기", width=10, command=top.destroy).pack(side="right")
        top.bind("<Escape>", lambda _e: top.destroy())
        self._refresh()

    # ---------- 화면 구성 ----------
    def _build_section(self, parent, cls: str, label: str):
        box = ttk.LabelFrame(parent, text=label, padding=6)
        box.pack(fill="both", expand=True, pady=4)
        bar = ttk.Frame(box)
        bar.pack(fill="x")
        ttk.Button(bar, text="현재 화면 추가", command=lambda: self._add_from_screen(cls)).pack(side="left")
        ttk.Button(bar, text="파일에서 가져오기", command=lambda: self._add_from_files(cls)).pack(side="left", padx=4)
        ttk.Button(bar, text="모두 삭제", command=lambda: self._delete_all(cls)).pack(side="left")
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
        self.sections[cls] = {"count": count, "strip": strip}

    def _refresh(self):
        self._photos.clear()
        for cls, sec in self.sections.items():
            for child in sec["strip"].winfo_children():
                child.destroy()
            files = paths.reference_paths(self.roi.id, cls)
            sec["count"].configure(text=f"{len(files)}장")
            if not files:
                ttk.Label(sec["strip"], text="등록된 이미지 없음", foreground="#999999").pack(padx=8, pady=30)
            for path in files:
                self._add_thumb(sec["strip"], path)
        self._update_calibration()

    def _add_thumb(self, strip, path: str):
        cell = ttk.Frame(strip, padding=3)
        cell.pack(side="left", anchor="n")
        size_ok = False
        try:
            with Image.open(path) as img:
                thumb = img.convert("RGB")
            size_ok = thumb.size == (self.roi.w, self.roi.h)
            thumb.thumbnail(_THUMB)
            photo = ImageTk.PhotoImage(thumb)
            self._photos.append(photo)
            tk.Label(cell, image=photo, borderwidth=1, relief="solid").pack()
        except Exception:
            ttk.Label(cell, text="(열 수 없음)").pack()
        name = os.path.basename(path)
        ttk.Label(cell, text=name if size_ok else f"⚠ ROI와 크기 다름\n{name}",
                  foreground="#555555" if size_ok else "#b71c1c", font=("맑은 고딕", 8)).pack()
        ttk.Button(cell, text="삭제", width=6, command=lambda: self._delete_one(path)).pack()

    def _update_calibration(self):
        if not self.is_match:
            n = len(paths.reference_paths(self.roi.id, "ok"))
            self.calib_label.configure(text=f"기준 이미지 {n}장" if n else "⚠ 기준 이미지가 없어 판정하지 않습니다.",
                                       foreground="#1b5e20" if n else "#b71c1c")
            return
        samples = worker.load_samples(self.roi.id)
        if not samples["ok"]:
            self.calib_label.configure(text="⚠ OK 샘플이 없어 판정하지 않습니다. OK 이미지를 먼저 등록하세요.",
                                       foreground="#b71c1c")
            return
        try:
            p = detectors.normalize_params("match", self.roi.params)
            calib = detectors.match_calibration(samples, (self.roi.h, self.roi.w), p["max_shift"])
        except Exception as e:
            self.calib_label.configure(text=f"자동 기준 계산 실패: {e}", foreground="#b71c1c")
            return
        manual = p["ok_threshold"] > 0
        text = (f"자동 계산 OK 허용 거리: {calib['threshold']:.2f}"
                + (f"  (이 ROI는 수동 값 {p['ok_threshold']:.2f} 사용 중)" if manual else "  ← 현재 사용 중")
                + f"\n{calib['quality']}")
        color = "#b71c1c" if calib["quality"].startswith("⚠") else "#1b5e20"
        self.calib_label.configure(text=text, foreground=color)

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
            messagebox.showerror("캡처 실패", str(e), parent=self.top)
            return
        self._regrab()
        self._refresh()

    def _add_from_files(self, cls: str):
        files = filedialog.askopenfilenames(
            parent=self.top, title=f"{self.classes[cls]} 이미지 선택",
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.bmp"), ("모든 파일", "*.*")])
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
                "비율 확인",
                f"ROI({target[0]}×{target[1]})와 가로세로 비율이 다른 이미지가 있습니다:\n"
                + "\n".join(mismatched[:8]) +
                "\n\nROI 크기로 늘려서 저장하면 판정이 부정확할 수 있습니다.\n"
                "NVR 화면에서 ROI 영역만 잘라낸 이미지를 권장합니다. 그래도 등록할까요?", parent=self.top):
            return
        for rgb in loaded:
            if rgb.size != target:
                rgb = rgb.resize(target, Image.LANCZOS)
            rgb.save(paths.new_reference_path(self.roi.id, cls))
        if failed:
            messagebox.showwarning("일부 실패", "열 수 없는 파일:\n" + "\n".join(failed), parent=self.top)
        self._refresh()

    def _delete_one(self, path: str):
        try:
            os.remove(path)
        except OSError as e:
            messagebox.showerror("삭제 실패", str(e), parent=self.top)
        self._refresh()

    def _delete_all(self, cls: str):
        if not paths.reference_paths(self.roi.id, cls):
            return
        if messagebox.askyesno("확인", f"{self.classes[cls]} 이미지를 모두 삭제할까요?", parent=self.top):
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
