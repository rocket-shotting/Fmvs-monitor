"""ROI 하나의 검출 설정 창 (검출 유형/조건, 지속 시간, 대상 프로그램, 담당자/Teams)."""
import copy
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional

from PIL import Image, ImageTk

import detectors
import notifier
import occlusion
import winutil
import worker
from capture import Grabber
from config import ROI
from ui_util import hidden_windows, modal

_LABEL_TO_KIND = {detectors.DETECTORS[k]["label"]: k for k in detectors.DETECTOR_ORDER}


def _fmt_param(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(str(int(v)) for v in value)
    f = float(value)
    return str(int(f)) if f.is_integer() else f"{f:g}"


class RoiDialog:
    def __init__(self, master: tk.Misc, roi: ROI, title: str):
        self.master = master
        self.roi = copy.deepcopy(roi)
        self.result: Optional[ROI] = None
        self.param_vars: Dict[str, tk.StringVar] = {}

        top = self.top = tk.Toplevel(master)
        top.title(title)
        top.resizable(False, False)
        top.protocol("WM_DELETE_WINDOW", self._cancel)

        body = ttk.Frame(top, padding=10)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self._build_basic(left)
        self._build_detect(left)
        self._build_process(right)
        self._build_contact(right)

        btns = ttk.Frame(body)
        btns.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="저장", width=12, command=self._save).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="취소", width=12, command=self._cancel).pack(side="right")
        top.bind("<Escape>", lambda _e: self._cancel())

    # ---------- 화면 구성 ----------
    def _build_basic(self, parent):
        box = ttk.LabelFrame(parent, text="기본", padding=8)
        box.pack(fill="x", pady=(0, 8))
        self.v_name = tk.StringVar(value=self.roi.name)
        self.v_enabled = tk.BooleanVar(value=self.roi.enabled)
        ttk.Label(box, text="이름").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.v_name, width=34).grid(row=0, column=1, columnspan=7, sticky="we", pady=2)
        ttk.Checkbutton(box, text="이 ROI 검출 사용", variable=self.v_enabled).grid(
            row=1, column=1, columnspan=7, sticky="w", pady=2)
        self.v_rect = {}
        for i, (key, label) in enumerate((("x", "X"), ("y", "Y"), ("w", "폭"), ("h", "높이"))):
            self.v_rect[key] = tk.StringVar(value=str(getattr(self.roi, key)))
            ttk.Label(box, text=label).grid(row=2, column=i * 2, sticky="e", padx=(0 if i == 0 else 6, 2))
            ttk.Entry(box, textvariable=self.v_rect[key], width=7).grid(row=2, column=i * 2 + 1, sticky="w")

    def _build_detect(self, parent):
        box = ttk.LabelFrame(parent, text="검출 조건", padding=8)
        box.pack(fill="x")
        ttk.Label(box, text="검출 유형").grid(row=0, column=0, sticky="w")
        self.v_kind = tk.StringVar(value=detectors.DETECTORS[self.roi.detector]["label"])
        combo = ttk.Combobox(box, textvariable=self.v_kind, state="readonly", width=36,
                             values=[detectors.DETECTORS[k]["label"] for k in detectors.DETECTOR_ORDER])
        combo.grid(row=0, column=1, sticky="we", pady=2)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_kind_changed())

        self.help_label = ttk.Label(box, text="", foreground="#555555", wraplength=380, justify="left")
        self.help_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 6))
        self.params_frame = ttk.Frame(box)
        self.params_frame.grid(row=2, column=0, columnspan=2, sticky="we")

        timing = ttk.Frame(box)
        timing.grid(row=3, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.v_duration = tk.StringVar(value=_fmt_param(self.roi.duration_sec))
        self.v_repeat = tk.StringVar(value=_fmt_param(self.roi.repeat_min))
        self.v_recovery = tk.BooleanVar(value=self.roi.notify_recovery)
        ttk.Label(timing, text="이상 지속 시간(초) – 이 시간 이상 계속되면 경보").grid(row=0, column=0, sticky="w")
        ttk.Entry(timing, textvariable=self.v_duration, width=8).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(timing, text="재알림 간격(분) – 0이면 한 번만").grid(row=1, column=0, sticky="w")
        ttk.Entry(timing, textvariable=self.v_repeat, width=8).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Checkbutton(timing, text="정상 복구 시에도 Teams 알림", variable=self.v_recovery).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=2)

        still = ttk.LabelFrame(box, text="움직이는 대상", padding=6)
        still.grid(row=3, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.v_still = tk.BooleanVar(value=self.roi.still_only)
        self.v_still_diff = tk.StringVar(value=_fmt_param(self.roi.still_diff))
        self.v_still_frames = tk.StringVar(value=str(self.roi.still_frames))
        ttk.Checkbutton(still, text="정지 시에만 판정 (움직이는 동안은 판정하지 않고, 멈춘 순간 1회 판정)",
                        variable=self.v_still).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(still, text="정지 기준 변화량 (이 값 이하면 정지, 0.1~255)").grid(row=1, column=0, sticky="w")
        ttk.Entry(still, textvariable=self.v_still_diff, width=8).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(still, text="정지 확인 횟수 (연속 n번 변화 없으면 정지)").grid(row=2, column=0, sticky="w")
        ttk.Entry(still, textvariable=self.v_still_frames, width=8).grid(row=2, column=1, sticky="w", padx=4)
        ttk.Label(still, text="켜면 '이상 지속 시간'은 쓰지 않고, 멈출 때마다 판정해 NG면 바로 알립니다.\n"
                              "[현재 화면으로 측정]에서 지금 변화량을 확인해 기준을 정하세요.\n"
                              "검사 주기 × 정지 확인 횟수보다 오래 멈춰야 판정됩니다.",
                  foreground="#555555", justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        test = ttk.Frame(box)
        test.grid(row=4, column=0, columnspan=2, sticky="we", pady=(8, 0))  # row 3 = 움직이는 대상
        ttk.Button(test, text="현재 화면으로 측정", command=self._measure).pack(side="left")
        self.measure_label = ttk.Label(test, text="조건 조정 후 눌러서 현재 값을 확인하세요.",
                                       foreground="#555555", wraplength=260, justify="left")
        self.measure_label.pack(side="left", padx=8)
        # 측정 화면 미리보기 (형상 검사 불량 위치는 빨간색 표시)
        self.preview_label = ttk.Label(box)
        self.preview_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._preview_photo = None
        self._rebuild_params(use_saved=True)

    def _build_process(self, parent):
        box = ttk.LabelFrame(parent, text="대상 프로그램 확인 (다른 창이 덮으면 검사 건너뜀)", padding=8)
        box.pack(fill="x", pady=(0, 8))
        self.v_process = tk.StringVar(value=self.roi.expected_process)
        ttk.Entry(box, textvariable=self.v_process, width=28).grid(row=0, column=0, sticky="we")
        ttk.Button(box, text="지금 화면에서 감지", command=self._detect_process).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(box, text="예: NVR_VIEWER.exe  ·  비우면 확인하지 않음\n"
                            "창 핸들이 아닌 프로그램(프로세스) 이름으로 비교하므로\n"
                            "FMVS이 내부적으로 창을 다시 만들어도 오탐이 없습니다.",
                  foreground="#555555", justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _build_contact(self, parent):
        box = ttk.LabelFrame(parent, text="담당자 / Teams 알림", padding=8)
        box.pack(fill="x")
        self.v_assignee = tk.StringVar(value=self.roi.assignee)
        self.v_email = tk.StringVar(value=self.roi.assignee_email)
        self.v_webhook = tk.StringVar(value=self.roi.webhook_url)
        rows = (("담당자 이름", self.v_assignee), ("담당자 이메일(Teams)", self.v_email),
                ("개별 Webhook URL", self.v_webhook))
        for i, (label, var) in enumerate(rows):
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(box, textvariable=var, width=36).grid(row=i, column=1, sticky="we", pady=2, padx=(6, 0))
        ttk.Label(box, text="개별 Webhook을 비우면 [설정]의 공통 Webhook으로 보냅니다.\n"
                            "담당자별로 다른 채팅방에 보내려면 여기에 해당 흐름의 URL을 넣으세요.",
                  foreground="#555555", justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _on_kind_changed(self):
        self._rebuild_params(use_saved=False)
        # 흐르는 라인용 유형은 한 화면만 이상이어도 바로 알림 (기본값을 그대로 둔 경우에만 변경)
        if self._kind() in ("match", "shape") and self.v_duration.get().strip() in ("5", "5.0"):
            self.v_duration.set("0")
            self.v_recovery.set(False)
            self.v_still.set(True)

    def _kind(self) -> str:
        return _LABEL_TO_KIND.get(self.v_kind.get(), "black")

    def _rebuild_params(self, use_saved: bool):
        for child in self.params_frame.winfo_children():
            child.destroy()
        kind = self._kind()
        spec = detectors.DETECTORS[kind]
        self.help_label.configure(text=spec["help"])
        if use_saved and kind == self.roi.detector:
            values = detectors.normalize_params(kind, self.roi.params)
        else:
            values = detectors.default_params(kind)
        self.param_vars = {}
        for i, (key, label, typ, _default, lo, _hi) in enumerate(spec["params"]):
            ttk.Label(self.params_frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            if typ == "choice":
                var = tk.StringVar(value=lo.get(values[key], next(iter(lo.values()))))
                ttk.Combobox(self.params_frame, textvariable=var, state="readonly", width=24,
                             values=list(lo.values())).grid(row=i, column=1, columnspan=2, sticky="w", padx=4)
            else:
                var = tk.StringVar(value=_fmt_param(values[key]))
                ttk.Entry(self.params_frame, textvariable=var, width=12).grid(row=i, column=1, sticky="w", padx=4)
            self.param_vars[key] = var
            if typ == "rgb":
                ttk.Button(self.params_frame, text="ROI 평균색 가져오기",
                           command=self._pick_mean_color).grid(row=i, column=2, padx=4)

    # ---------- 값 수집/검증 ----------
    def _collect_rect_only(self) -> ROI:
        roi = copy.deepcopy(self.roi)
        labels = {"x": "X", "y": "Y", "w": "폭", "h": "높이"}
        for key, label in labels.items():
            try:
                setattr(roi, key, int(float(self.v_rect[key].get())))
            except ValueError:
                raise ValueError(f"위치 '{label}' 값이 숫자가 아닙니다.")
        if roi.w < 4 or roi.h < 4:
            raise ValueError("ROI 폭/높이는 4 이상이어야 합니다.")
        return roi

    def _collect(self) -> ROI:
        roi = self._collect_rect_only()
        roi.name = self.v_name.get().strip()
        if not roi.name:
            raise ValueError("이름을 입력하세요.")
        roi.enabled = self.v_enabled.get()
        roi.detector = self._kind()
        params = {}
        for key, label, typ, default, lo, hi in detectors.DETECTORS[roi.detector]["params"]:
            raw = self.param_vars[key].get().strip()
            if typ == "choice":
                value = next((k for k, v in lo.items() if v == raw), default)
                params[key] = value
                continue
            try:
                if typ == "rgb":
                    value = [int(float(p)) for p in raw.replace(" ", "").split(",")]
                    if len(value) != 3 or any(v < lo or v > hi for v in value):
                        raise ValueError
                else:
                    value = float(raw)
                    if value < lo or value > hi:
                        raise ValueError
            except ValueError:
                raise ValueError(f"'{label}' 값이 올바르지 않습니다. (범위 {lo}~{hi})")
            params[key] = value
        roi.params = params
        try:
            roi.duration_sec = max(0.0, float(self.v_duration.get()))
            roi.repeat_min = max(0.0, float(self.v_repeat.get()))
        except ValueError:
            raise ValueError("지속 시간/재알림 간격은 숫자로 입력하세요.")
        roi.notify_recovery = self.v_recovery.get()
        roi.still_only = self.v_still.get()
        try:
            roi.still_diff = float(self.v_still_diff.get())
            roi.still_frames = int(float(self.v_still_frames.get()))
        except ValueError:
            raise ValueError("정지 기준 변화량/정지 확인 횟수는 숫자로 입력하세요.")
        if not 0.1 <= roi.still_diff <= 255 or not 1 <= roi.still_frames <= 20:
            raise ValueError("정지 기준 변화량은 0.1~255, 정지 확인 횟수는 1~20 사이여야 합니다.")
        roi.expected_process = self.v_process.get().strip()
        roi.assignee = self.v_assignee.get().strip()
        roi.assignee_email = self.v_email.get().strip()
        roi.webhook_url = self.v_webhook.get().strip()
        if roi.webhook_url:
            err = notifier.validate_url(roi.webhook_url)
            if err:
                raise ValueError(f"개별 {err}")
        return roi

    # ---------- 화면 측정 ----------
    def _measure(self):
        try:
            roi = self._collect()
        except ValueError as e:
            messagebox.showerror("입력 오류", str(e), parent=self.top)
            return
        frames, windows = [], None
        try:
            with hidden_windows(self.top, self.master):
                with Grabber() as g:
                    frames.append(g.grab(roi.x, roi.y, roi.w, roi.h))
                    if roi.detector == "frozen" or roi.still_only:
                        time.sleep(1.0 if roi.detector == "frozen" else 0.5)
                        frames.append(g.grab(roi.x, roi.y, roi.w, roi.h))
                if roi.expected_process and winutil.IS_WINDOWS:
                    windows = winutil.visible_windows()
        except Exception as e:
            self._regrab()
            messagebox.showerror("캡처 실패", str(e), parent=self.top)
            return
        self._regrab()
        state: dict = {}
        ref = worker.load_for_detector(roi.id, roi.detector)
        res = None
        for frame in frames:
            res = detectors.evaluate(roi.detector, roi.params, frame, state, reference=ref)
        self._show_preview(detectors.overlay_defects(frames[-1], res.mask))
        verdict = {True: "🚨 이상", False: "✅ 정상", None: "⏸ 판정 불가"}[res.abnormal]
        lines = [f"판정: {verdict}", res.detail]
        if roi.still_only and roi.detector != "frozen" and len(frames) == 2:
            motion = detectors.motion_amount(detectors.motion_gray(frames[0]), detectors.motion_gray(frames[1]))
            moving = motion > roi.still_diff
            lines.append(f"0.5초 간 변화량 {motion:.1f} → {'움직임 (판정 안 함)' if moving else '정지 (판정함)'}"
                         f" · 기준 {roi.still_diff:g}")
        if roi.expected_process and winutil.IS_WINDOWS:
            vis = occlusion.roi_visibility((roi.x, roi.y, roi.w, roi.h), windows or [], roi.expected_process)
            if vis.ok:
                lines.append(f"대상 프로그램 확인: {roi.expected_process} ✔ (ROI를 가린 창 없음)")
            else:
                lines.append(f"⚠ 검출 시 건너뜀: {vis.detail}")
        self.measure_label.configure(text="\n".join(lines), foreground="#000000")

    def _show_preview(self, rgb):
        img = Image.fromarray(rgb)
        img.thumbnail((400, 220))
        self._preview_photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=self._preview_photo)

    def _pick_mean_color(self):
        try:
            roi = self._collect_rect_only()
            with hidden_windows(self.top, self.master):
                with Grabber() as g:
                    frame = g.grab(roi.x, roi.y, roi.w, roi.h)
        except Exception as e:
            self._regrab()
            messagebox.showerror("캡처 실패", str(e), parent=self.top)
            return
        self._regrab()
        self.param_vars["rgb"].set(",".join(str(v) for v in detectors.mean_color(frame)))

    def _detect_process(self):
        if not winutil.IS_WINDOWS:
            messagebox.showinfo("안내", "Windows에서만 지원됩니다.", parent=self.top)
            return
        try:
            roi = self._collect_rect_only()
        except ValueError as e:
            messagebox.showerror("입력 오류", str(e), parent=self.top)
            return
        with hidden_windows(self.top, self.master):
            cx, cy = roi.center()
            proc = winutil.process_name_at(cx, cy)
        self._regrab()
        if proc:
            self.v_process.set(proc)
        else:
            messagebox.showwarning("감지 실패", "ROI 위치의 프로그램을 확인할 수 없습니다.", parent=self.top)

    def _regrab(self):
        try:
            self.top.lift()
            self.top.grab_set()
            self.top.focus_force()
        except tk.TclError:
            pass

    # ---------- 닫기 ----------
    def _save(self):
        try:
            self.result = self._collect()
        except ValueError as e:
            messagebox.showerror("입력 오류", str(e), parent=self.top)
            return
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()

    def run(self) -> Optional[ROI]:
        modal(self.top, self.master)
        return self.result


def edit_roi(master: tk.Misc, roi: ROI, title: str = "ROI 설정") -> Optional[ROI]:
    return RoiDialog(master, roi, title).run()
