"""Standalone hBN / approximately 285 nm SiO2/Si optical-contrast calibration."""
from __future__ import annotations
import math
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageOps, ImageStat, ImageTk

FIT_COLUMNS = ("C_R", "C_G", "C_B", "厚度(nm)")
CHANNELS = ("C_R", "C_G", "C_B")


def region_box(start, end):
    return (min(start[0], end[0]), min(start[1], end[1]),
            max(start[0], end[0]) + 1, max(start[1], end[1]) + 1)


def region_means(image, box):
    left, top, right, bottom = box
    if image.mode != "RGB" or not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError("请选择图像内的有效区域。")
    return tuple(ImageStat.Stat(image.crop(box)).mean)


def optical_contrast(background, signal):
    """Signed empirical channel contrast of encoded camera pixels, not absolute reflectance.

    A zero background channel is undefined (None); other channels remain usable.
    """
    if len(background) != 3 or len(signal) != 3:
        raise ValueError("区域必须包含三个通道。")
    if any(not math.isfinite(float(v)) or not 0 <= float(v) <= 255 for v in (*background, *signal)):
        raise ValueError("区域均值必须在 0–255 之间。")
    return tuple(None if b == 0 else (b - s) / b for b, s in zip(background, signal))


def validate_fitting_values(values):
    values = tuple(str(value).strip() for value in values)
    if len(values) != 4:
        raise ValueError("每行必须有四列：C_R、C_G、C_B、厚度(nm)。")
    if all(value == "" for value in values[:3]):
        raise ValueError("至少应有一个有效的通道对比度。")
    for index, value in enumerate(values):
        if value == "":
            continue
        try:
            number = float(value)
        except ValueError:
            raise ValueError(f"{FIT_COLUMNS[index]} 必须是数值。") from None
        if not math.isfinite(number) or (index < 3 and number > 1) or (index == 3 and number < 0):
            raise ValueError("对比度须为有限数值且≤1，允许负值；厚度须为非负有限数值或留空。")
    return values


def parse_fitting_text(text):
    """Require a contrast-specific header to avoid confusing old RGB tables."""
    rows, header_seen = [], False
    for line_number, line in enumerate(text.lstrip("\ufeff").splitlines(), start=1):
        if not line.strip():
            continue
        values = tuple(part.strip() for part in (
            line.split("\t") if "\t" in line else line.split(",") if "," in line else line.split()))
        if not header_seen:
            lower = tuple(value.lower() for value in values)
            if lower not in (("c_r", "c_g", "c_b", "厚度(nm)"), ("c_r", "c_g", "c_b", "厚度"),
                             ("c_r", "c_g", "c_b", "thickness_nm")):
                raise ValueError(f"第 {line_number} 行：需要表头 C_R、C_G、C_B、厚度(nm)，不能导入 RGB 或色差表。")
            header_seen = True
            continue
        try:
            rows.append(validate_fitting_values(values))
        except ValueError as exc:
            raise ValueError(f"第 {line_number} 行：{exc}") from exc
    if not header_seen:
        raise ValueError("文件为空。")
    return rows


def linear_fit(rows, channel="C_G"):
    """Fit thickness in nm against the selected signed contrast (dimensionless)."""
    if channel not in CHANNELS:
        raise ValueError("请选择 C_R、C_G 或 C_B。")
    column = CHANNELS.index(channel)
    points = []
    for row in rows:
        values = validate_fitting_values(row)
        if values[column] == "" or values[3] == "":
            raise ValueError(f"勾选行缺少 {channel} 或厚度，请补充或取消勾选。")
        points.append((float(values[column]), float(values[3])))
    if len(points) < 2:
        raise ValueError("至少需要勾选两行有效数据。")
    try:
        n = len(points)
        mx = math.fsum(x / n for x, _ in points)
        my = math.fsum(y / n for _, y in points)
        sxx = math.fsum((x - mx) ** 2 for x, _ in points)
        if sxx == 0:
            raise ValueError(f"所选数据的 {channel} 全部相同，无法确定斜率。")
        slope = math.fsum((x - mx) * (y - my) for x, y in points) / sxx
        intercept = my - slope * mx
        total = math.fsum((y - my) ** 2 for _, y in points)
        residual = math.fsum((y - (my + slope * (x - mx))) ** 2 for x, y in points)
        r_squared = None if total == 0 else 1 - residual / total
        if not all(math.isfinite(v) for v in (slope, intercept, sxx, total, residual)):
            raise OverflowError
        if r_squared is not None and not math.isfinite(r_squared):
            raise OverflowError
    except (OverflowError, ZeroDivisionError):
        raise ValueError("数据数值范围过大或差异过小，无法可靠计算，请检查输入。") from None
    return dict(points=points, slope=slope, intercept=intercept, r_squared=r_squared,
                mean_x=mx, mean_y=my, x_label=channel, channel=channel, rmse=math.sqrt(residual / n))


def read_fitting_txt(path):
    return parse_fitting_text(Path(path).read_text(encoding="utf-8-sig"))


def write_fitting_txt(path, rows):
    """Write a complete UTF-8 table before atomically replacing the target."""
    text = "\t".join(FIT_COLUMNS) + "\n"
    text += "".join("\t".join(validate_fitting_values(row)) + "\n" for row in rows)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent,
                                         prefix=".contrast-export-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_rgb(path: str | Path) -> Image.Image:
    """Read the first frame, apply EXIF orientation, and detach from the file."""
    with Image.open(path) as source:
        if source.mode in {"I", "F"} or source.mode.startswith("I;16"):
            raise ValueError("暂不支持高位深或浮点灰度图，请先转换为 8 位图像。")
        return ImageOps.exif_transpose(source).convert("RGB")


def image_point(x, y, offset, display_size, image_size, clamp=False):
    """Map canvas coordinates using actual rounded display dimensions."""
    dx, dy = x - offset[0], y - offset[1]
    dw, dh = display_size
    iw, ih = image_size
    if not clamp and not (0 <= dx < dw and 0 <= dy < dh):
        return None
    return (max(0, min(iw - 1, math.floor(dx * iw / dw))),
            max(0, min(ih - 1, math.floor(dy * ih / dh))))


class OpticalContrastInspector(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("hBN 光学对比度 · 约 285 nm SiO₂/Si")
        self.geometry("1120x780")
        self.minsize(760, 600)
        self.image = None
        self.photo = None
        self.fit = True
        self.offset = (0, 0)
        self.display_size = (1, 1)
        self.resize_job = None
        self.drag_anchor = self.drag_box = None
        self.samples = {"background": None, "signal": None}
        self.exported_rows = ()
        self.checked_rows = set()
        self.fit_result = None
        self.pick_mode = tk.StringVar(value="")
        self.file_text = tk.StringVar(value="尚未打开图片")
        self.status_text = tk.StringVar(value="先打开图片，再点击 background 选背景区域。")
        self.sample_text = tk.StringVar(value="background：未选择     signal：未选择")
        self.contrast_text = tk.StringVar(value="C_R：—    C_G：—    C_B：—")
        self._build_ui()
        self.bind("<Control-o>", lambda event: self.open_image())
        self.bind("<Escape>", lambda event: self.clear_regions())
        self.protocol("WM_DELETE_WINDOW", self._close)


    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Main.TNotebook", background="#dce5f2", tabmargins=(12, 10, 12, 0))
        style.configure("Main.TNotebook.Tab", font=("Microsoft YaHei UI", 16, "bold"), padding=(32, 14))
        style.map("Main.TNotebook.Tab", background=[("selected", "#1d4ed8"), ("active", "#cbdafa")],
                  foreground=[("selected", "white")])
        style.configure("Pick.Toolbutton", padding=(12, 8), font=("Microsoft YaHei UI", 11, "bold"))
        style.map("Pick.Toolbutton", background=[("selected", "#1d4ed8")], foreground=[("selected", "white")])
        self.notebook = ttk.Notebook(self, style="Main.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.fitting_tab = ttk.Frame(self.notebook)
        self.regression_tab = ttk.Frame(self.notebook)
        for frame, title in ((self.analysis_tab, "图片分析"), (self.fitting_tab, "拟合数据"), (self.regression_tab, "拟合")):
            self.notebook.add(frame, text=title)
        toolbar = ttk.Frame(self.analysis_tab, padding=12)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="打开图片…", command=self.open_image).pack(side="left", padx=4)
        ttk.Button(toolbar, text="适应窗口", command=lambda: self.set_view(True)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="100% 显示", command=lambda: self.set_view(False)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="清除选区", command=self.clear_regions).pack(side="left", padx=4)
        pickbar = ttk.Frame(self.analysis_tab, padding=(14, 0, 14, 8))
        pickbar.pack(fill="x")
        self.background_button = ttk.Radiobutton(pickbar, text="background", value="background", variable=self.pick_mode,
                                                 command=self._pick_mode_changed, style="Pick.Toolbutton", state="disabled")
        self.background_button.pack(side="left", padx=(0, 8))
        self.signal_button = ttk.Radiobutton(pickbar, text="signal", value="signal", variable=self.pick_mode,
                                             command=self._pick_mode_changed, style="Pick.Toolbutton", state="disabled")
        self.signal_button.pack(side="left", padx=(0, 12))
        self.add_fit_button = ttk.Button(pickbar, text="加入拟合", command=self.add_to_fitting, state="disabled")
        self.add_fit_button.pack(side="left")
        ttk.Label(self.analysis_tab, textvariable=self.file_text, padding=(14, 0, 14, 8), wraplength=700).pack(fill="x")
        panel = ttk.Frame(self.analysis_tab, padding=(12, 0))
        panel.pack(fill="both", expand=True)
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(panel, background="#202630", highlightthickness=0, cursor="crosshair")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(panel, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(panel, orient="horizontal", command=self.canvas.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        ttk.Label(self.analysis_tab, textvariable=self.sample_text, padding=(14, 8), wraplength=700).pack(fill="x")
        ttk.Label(self.analysis_tab, textvariable=self.contrast_text, style="Title.TLabel", padding=(14, 4), wraplength=700).pack(fill="x")
        ttk.Label(self.analysis_tab, text="C = (背景均值 − 信号均值) / 背景均值。使用图片编码值，未做 gamma 线性化；约 285 nm 衬底先用 C_G 标定。", padding=(14, 4), wraplength=700).pack(fill="x")
        ttk.Label(self.analysis_tab, textvariable=self.status_text, padding=(14, 4, 14, 12), wraplength=700).pack(fill="x")
        self._build_fitting_ui()
        self._build_regression_ui()


    def _pick_mode_changed(self):
        self.drag_anchor = None
        self.drag_box = None
        self._update_samples()
        if self.image is not None:
            self.status_text.set(f"请在图片内按住左键拖出 {self.pick_mode.get()} 矩形；单击可选单像素。")


    def _update_samples(self):
        descriptions = []
        for name, box in self.samples.items():
            if box is None:
                descriptions.append(f"{name}：未选择")
            else:
                l, t, r, b = box
                descriptions.append(f"{name}：({l},{t})–({r-1},{b-1})，{(r-l)*(b-t)} 像素")
        self.sample_text.set("    ".join(descriptions))
        ready = self.image is not None and all(box is not None for box in self.samples.values())
        self.add_fit_button.configure(state="disabled")
        if ready:
            values = self.current_contrasts()
            self.contrast_text.set("    ".join(f"{name}：{value:.6f}" if value is not None else f"{name}：未定义"
                                               for name, value in zip(CHANNELS, values)))
            if any(value is not None for value in values) and self.drag_anchor is None:
                self.add_fit_button.configure(state="normal")
            missing = [name for name, value in zip(CHANNELS, values) if value is None]
            self.status_text.set("背景均值为 0，以下通道不能计算：" + "、".join(missing) if missing else
                                 "已计算区域均值对比度。负值表示信号区比背景亮；点击“加入拟合”记录。")
        else:
            self.contrast_text.set("C_R：—    C_G：—    C_B：—")
            self.status_text.set("点击 background 选择裸衬底区域，再点击 signal 选择 hBN 内部区域。")
        self._draw_markers()

    def current_contrasts(self):
        if self.image is None or any(box is None for box in self.samples.values()):
            raise ValueError("请在当前图片中选择 background 和 signal 两个区域。")
        return optical_contrast(region_means(self.image, self.samples["background"]),
                                region_means(self.image, self.samples["signal"]))


    def add_to_fitting(self):
        if self.drag_anchor is not None or self.image is None or any(box is None for box in self.samples.values()):
            return
        values = self.current_contrasts()
        if all(value is None for value in values):
            return
        row = self._insert_fitting_row((*["" if value is None else value for value in values], ""))
        self.fit_table.selection_set(row)
        self.fit_table.focus(row)
        self.fit_table.see(row)
        self.notebook.select(self.fitting_tab)
        self._fit_selection_changed()


    def clear_regions(self):
        self.samples = {"background": None, "signal": None}
        self.drag_anchor = self.drag_box = None
        self.pick_mode.set("")
        self._update_samples()


    def _draw_markers(self):
        self.canvas.delete("sample_marker")
        if self.image is None:
            return
        boxes = [(name, box, "#22d3ee" if name == "background" else "#fbbf24") for name, box in self.samples.items()]
        if self.drag_box is not None:
            boxes.append(("选择中", self.drag_box, "white"))
        for name, box, color in boxes:
            if box is None:
                continue
            left, top, right, bottom = box
            ox, oy = self.offset
            sx, sy = self.display_size[0] / self.image.width, self.display_size[1] / self.image.height
            coords = (ox + left * sx, oy + top * sy, ox + right * sx, oy + bottom * sy)
            self.canvas.create_rectangle(*coords, outline="black", width=4, tags="sample_marker")
            self.canvas.create_rectangle(*coords, outline=color, width=2, tags="sample_marker")
            self.canvas.create_text(coords[0] + 3, coords[1] + 3, text=name, anchor="nw", fill=color,
                                    font=("Microsoft YaHei UI", 10, "bold"), tags="sample_marker")


    def open_path(self, path):
        try:
            loaded = load_rgb(path)
        except Exception as exc:
            messagebox.showerror("无法打开图片", str(exc), parent=self)
            return False
        self.image = loaded
        self.notebook.select(self.analysis_tab)
        self.fit = True
        self.clear_regions()
        self.background_button.configure(state="normal")
        self.signal_button.configure(state="normal")
        self.file_text.set(f"{Path(path).name} | {loaded.width} × {loaded.height} 像素")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._render()
        return True


    def _build_regression_ui(self):
        toolbar = ttk.Frame(self.regression_tab, padding=12)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="光学对比度 · 线性拟合", style="Title.TLabel").pack(side="left", padx=(0, 18))
        self.fit_channel = tk.StringVar(value="C_G")
        self.channel_picker = ttk.Combobox(toolbar, textvariable=self.fit_channel, values=CHANNELS, width=5, state="readonly")
        self.channel_picker.pack(side="left", padx=(0, 12))
        self.channel_picker.bind("<<ComboboxSelected>>", self._channel_changed)
        self.run_fit_button = ttk.Button(toolbar, text="开始 / 更新拟合", command=self.run_fitting)
        self.run_fit_button.pack(side="left")
        self.model_text = tk.StringVar(value="模型：厚度(nm) = 斜率 × C_G + 截距；所有勾选数据等权。")
        ttk.Label(self.regression_tab, textvariable=self.model_text, padding=(14, 0, 14, 8)).pack(fill="x")
        self.fit_parameters = tk.StringVar(value="斜率：—     截距：—     R²：—")
        ttk.Label(self.regression_tab, textvariable=self.fit_parameters, style="Title.TLabel", padding=(14, 8), wraplength=700).pack(fill="x")
        self.regression_status = tk.StringVar(value="优先比较 C_G 和 C_B；需要本机 AFM 标定，不能直接保证整个 0–30 nm 范围线性。")
        ttk.Label(self.regression_tab, textvariable=self.regression_status, padding=(14, 0, 14, 8), wraplength=700).pack(fill="x")
        self.show_residuals = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.regression_tab, text="查看厚度残差（实测 − 拟合），检查是否存在弯曲趋势", variable=self.show_residuals,
                        command=self._draw_fit_plot).pack(anchor="w", padx=14, pady=(0, 6))
        self.plot_canvas = tk.Canvas(self.regression_tab, background="white", highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_fit_plot())

    def _channel_changed(self, event=None):
        self.model_text.set(f"模型：厚度(nm) = 斜率 × {self.fit_channel.get()} + 截距；所有勾选数据等权。")
        self._invalidate_fit()


    def _invalidate_fit(self):
        self.fit_result = None
        if hasattr(self, "fit_parameters"):
            self.fit_parameters.set("斜率：—     截距：—     R²：—")
            self.regression_status.set("数据或勾选已改变，请点击“开始 / 更新拟合”。")
            self._draw_fit_plot()


    def run_fitting(self):
        self._invalidate_fit()
        channel = self.fit_channel.get()
        column = CHANNELS.index(channel)
        rows = []
        for index, row in enumerate(self.fit_table.get_children(), start=1):
            if row not in self.checked_rows:
                continue
            values = self.fit_table.item(row, "values")
            if values[column] == "" or values[3] == "":
                reason = f"表格第 {index} 行缺少 {channel} 或厚度，请补充或取消勾选。"
                self.regression_status.set(reason)
                messagebox.showerror("无法拟合", reason, parent=self)
                return
            rows.append(values)
        try:
            self.fit_result = linear_fit(rows, channel)
        except ValueError as exc:
            self.regression_status.set(str(exc))
            messagebox.showerror("无法拟合", str(exc), parent=self)
            return
        result = self.fit_result
        r2 = "未定义（厚度全部相同）" if result["r_squared"] is None else f"{result['r_squared']:.8g}"
        self.fit_parameters.set(f"斜率：{result['slope']:.8g}     截距：{result['intercept']:.8g}     R²：{r2}")
        self.regression_status.set(f"已拟合 {len(rows)} 个点；训练 RMSE = {result['rmse']:.6g} nm（不是独立验证误差）。横轴：{channel}，无量纲。")
        self._draw_fit_plot()


    def _build_fitting_ui(self):
        toolbar = ttk.Frame(self.fitting_tab, padding=12)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="拟合数据", style="Title.TLabel").pack(side="left", padx=(0, 24))
        self.edit_fit_button = ttk.Button(toolbar, text="填写 / 修改选中行", command=self.edit_fitting_row, state="disabled")
        self.edit_fit_button.pack(side="left", padx=4)
        self.delete_fit_button = ttk.Button(toolbar, text="删除选中行", command=self.delete_fitting_rows, state="disabled")
        self.delete_fit_button.pack(side="left", padx=4)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=12)
        self.import_fit_button = ttk.Button(toolbar, text="导入 TXT…", command=self.import_fitting)
        self.import_fit_button.pack(side="left", padx=4)
        self.export_fit_button = ttk.Button(toolbar, text="导出 TXT…", command=self.export_fitting)
        self.export_fit_button.pack(side="left", padx=4)
        selection_bar = ttk.Frame(self.fitting_tab, padding=(14, 0, 14, 8))
        selection_bar.pack(fill="x")
        ttk.Button(selection_bar, text="全部勾选", command=lambda: self.check_all_rows(True)).pack(side="left", padx=(0, 6))
        ttk.Button(selection_bar, text="全部取消", command=lambda: self.check_all_rows(False)).pack(side="left", padx=(0, 12))
        ttk.Label(selection_bar, text="勾选决定是否参与拟合；双击数值编辑。厚度请统一单位。").pack(side="left")
        table_frame = ttk.Frame(self.fitting_tab, padding=(12, 0))
        table_frame.pack(fill="both", expand=True)
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        ttk.Style(self).configure("Fit.Treeview", font=("Microsoft YaHei UI", 11), rowheight=30)
        self.fit_table = ttk.Treeview(table_frame, columns=FIT_COLUMNS, show="tree headings", selectmode="extended", style="Fit.Treeview")
        self.fit_table.heading("#0", text="参与拟合")
        self.fit_table.column("#0", width=90, minwidth=90, stretch=False)
        for name in self.fit_table["columns"]:
            self.fit_table.heading(name, text=name)
            self.fit_table.column(name, width=140, minwidth=100, anchor="center")
        self.fit_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.fit_table.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.fit_table.configure(yscrollcommand=scrollbar.set)
        self.fit_table.bind("<<TreeviewSelect>>", self._fit_selection_changed)
        self.fit_table.bind("<Button-1>", self._checkbox_click)
        self.fit_table.bind("<space>", self._checkbox_space)
        self.fit_table.bind("<Double-1>", self._fit_double_click)
        self.fit_table.bind("<Delete>", lambda event: self.delete_fitting_rows())
        self.fit_status = tk.StringVar(value="共 0 行")
        ttk.Label(self.fitting_tab, textvariable=self.fit_status, padding=(14, 8)).pack(fill="x")
        self.fit_io_status = tk.StringVar(value="导入会追加到表格末尾；导出保存全部行（包括空白厚度）。")
        ttk.Label(self.fitting_tab, textvariable=self.fit_io_status, wraplength=700, padding=(14, 0, 14, 8)).pack(fill="x")
        ttk.Label(self.fitting_tab, text="TXT 保存全部四列数据，不保存勾选状态；新增及导入行默认勾选。到“拟合”页计算。", padding=(14, 0, 14, 12)).pack(fill="x")


    def _insert_fitting_row(self, values):
        row = self.fit_table.insert("", "end", text="☑", values=values)
        self.checked_rows.add(row)
        self._invalidate_fit()
        return row


    def _checkbox_click(self, event):
        row = self.fit_table.identify_row(event.y)
        if row and self.fit_table.identify_column(event.x) == "#0":
            self.toggle_fitting_row(row)
            self.fit_table.focus(row)
            self.fit_table.focus_set()
            return "break"


    def _checkbox_space(self, event):
        row = self.fit_table.focus()
        if row:
            self.toggle_fitting_row(row)
        return "break"


    def toggle_fitting_row(self, row):
        if row in self.checked_rows:
            self.checked_rows.remove(row)
        else:
            self.checked_rows.add(row)
        self.fit_table.item(row, text="☑" if row in self.checked_rows else "☐")
        self._invalidate_fit()
        self._fit_selection_changed()


    def check_all_rows(self, checked):
        rows = self.fit_table.get_children()
        self.checked_rows = set(rows) if checked else set()
        for row in rows:
            self.fit_table.item(row, text="☑" if checked else "☐")
        self._invalidate_fit()
        self._fit_selection_changed()


    def _draw_fit_plot(self):
        canvas = self.plot_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if self.fit_result is None:
            canvas.create_text(width / 2, height / 2, text="拟合完成后将在此显示数据点和拟合直线", fill="#64748b", font=("Microsoft YaHei UI", 13))
            return
        if width < 200 or height < 180:
            return
        result = self.fit_result
        residual_mode = self.show_residuals.get()
        points = [(x, y - (result["mean_y"] + result["slope"] * (x - result["mean_x"])))
                  for x, y in result["points"]] if residual_mode else result["points"]
        xmin, xmax = min(x for x, _ in points), max(x for x, _ in points)
        predict = lambda x: result["mean_y"] + result["slope"] * (x - result["mean_x"])
        line_y = (0, 0) if residual_mode else (predict(xmin), predict(xmax))
        ymin, ymax = min(*(y for _, y in points), *line_y), max(*(y for _, y in points), *line_y)
        xpad = (xmax - xmin) * .06
        ypad = (ymax - ymin) * .1 if ymax != ymin else max(abs(ymin) * .1, 1)
        xmin, xmax, ymin, ymax = xmin - xpad, xmax + xpad, ymin - ypad, ymax + ypad
        if not all(math.isfinite(v) for v in (xmin, xmax, ymin, ymax)) or xmin == xmax or ymin == ymax:
            canvas.create_text(width / 2, height / 2, text="数据范围超出图表显示精度，请检查输入数值。", fill="#b91c1c")
            return
        left, top, right, bottom = 100, 42, width - 30, height - 65
        px = lambda x: left + (x - xmin) / (xmax - xmin) * (right - left)
        py = lambda y: bottom - (y - ymin) / (ymax - ymin) * (bottom - top)
        for i in range(6):
            x, y = xmin + (xmax - xmin) * i / 5, ymin + (ymax - ymin) * i / 5
            canvas.create_line(px(x), top, px(x), bottom, fill="#e2e8f0")
            canvas.create_line(left, py(y), right, py(y), fill="#e2e8f0")
            canvas.create_text(px(x), bottom + 18, text=f"{x:.4g}", font=("Consolas", 10))
            canvas.create_text(left - 10, py(y), text=f"{y:.4g}", anchor="e", font=("Consolas", 10))
        canvas.create_line(left, top, left, bottom, right, bottom, fill="#334155", width=2)
        canvas.create_text((left + right) / 2, height - 20, text=result["x_label"], font=("Consolas", 12))
        canvas.create_text(24, (top + bottom) / 2, text="残差 (nm)" if residual_mode else "厚度 (nm)", angle=90, font=("Microsoft YaHei UI", 12))
        xlo, xhi = min(x for x, _ in points), max(x for x, _ in points)
        canvas.create_line(px(xlo), py(line_y[0]), px(xhi), py(line_y[1]), fill="#dc2626", width=2, tags="fit_line")
        for x, y in points:
            cx, cy = px(x), py(y)
            canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#2563eb", outline="white", tags="data_point")
        canvas.create_text(left, 20, text="● 厚度残差" if residual_mode else "● 数据点", fill="#2563eb", anchor="w", font=("Microsoft YaHei UI", 11))
        canvas.create_text(left + 120, 20, text="━ 零残差" if residual_mode else "━ 拟合直线", fill="#dc2626", anchor="w", font=("Microsoft YaHei UI", 11))


    def _fitting_rows(self):
        return tuple(self.fit_table.item(row, "values") for row in self.fit_table.get_children())


    def import_fitting(self):
        path = filedialog.askopenfilename(title="导入 TXT 表格（追加到现有数据）", parent=self,
                                          filetypes=[("TXT 表格", "*.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            rows = read_fitting_txt(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导入失败", f"未添加任何数据。请检查文件是否为 UTF-8 编码的四列表格。\n\n{exc}", parent=self)
            return
        added = [self._insert_fitting_row(row) for row in rows]
        if added:
            self.fit_table.selection_set(added)
            self.fit_table.focus(added[0])
            self.fit_table.see(added[0])
        self._fit_selection_changed()
        self.fit_io_status.set(f"已从 {Path(path).name} 追加 {len(rows)} 行，原有数据已保留。")


    def export_fitting(self):
        path = filedialog.asksaveasfilename(title="导出全部拟合数据", parent=self,
                                            defaultextension=".txt", initialfile="光学对比度数据.txt",
                                            filetypes=[("TXT 表格", "*.txt")], confirmoverwrite=True)
        if not path:
            return
        rows = self._fitting_rows()
        try:
            write_fitting_txt(path, rows)
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", f"未能保存表格，请重试或选择其他位置。\n\n{exc}", parent=self)
            return
        self.exported_rows = rows
        self.fit_io_status.set(f"已导出全部 {len(rows)} 行至：{path}")


    def _fit_selection_changed(self, event=None):
        count = len(self.fit_table.selection())
        self.edit_fit_button.configure(state="normal" if count == 1 else "disabled")
        self.delete_fit_button.configure(state="normal" if count else "disabled")
        self.fit_status.set(f"共 {len(self.fit_table.get_children())} 行 · 已勾选 {len(self.checked_rows)} 行参与拟合 · 已选中 {count} 行用于编辑 / 删除")


    def _fit_double_click(self, event):
        if self.fit_table.identify_column(event.x) == "#0":
            return "break"
        row = self.fit_table.identify_row(event.y)
        if row and self.fit_table.identify_region(event.x, event.y) == "cell":
            self.fit_table.selection_set(row)
            self.edit_fitting_row()


    def edit_fitting_row(self):
        selected = self.fit_table.selection()
        if len(selected) != 1:
            return
        row = selected[0]
        dialog = tk.Toplevel(self)
        dialog.title("填写 / 修改拟合数据")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        entries = []
        for index, (label, value) in enumerate(zip(self.fit_table["columns"], self.fit_table.item(row, "values"))):
            ttk.Label(body, text=label).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=6)
            entry = ttk.Entry(body, width=30)
            entry.insert(0, value)
            entry.grid(row=index, column=1, pady=6)
            entries.append(entry)
        ttk.Label(body, text="对比度可为负值（最大为1）；厚度≥0 nm，可留空。\n首次填写空白厚度可直接保存；覆盖已有值需确认。").grid(row=4, column=0, columnspan=2, pady=10)

        def save():
            if self.update_fitting_row(row, [entry.get() for entry in entries], parent=dialog):
                dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="保存", command=save).pack(side="left", padx=4)
        dialog.bind("<Return>", lambda event: save())
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.grab_set()
        entries[3].focus_set()


    def update_fitting_row(self, row, values, parent=None):
        parent = parent or self
        old = self.fit_table.item(row, "values")
        try:
            new = validate_fitting_values(values)
        except ValueError as exc:
            messagebox.showerror("数值无效", str(exc), parent=parent)
            return False
        # Formatting-only changes are not replacements of the measured value.
        changed = [i for i in range(4) if old[i] != new[i] and
                   (old[i] == "" or new[i] == "" or float(old[i]) != float(new[i]))]
        overwritten = [i for i in changed if old[i] != ""]
        if overwritten:
            details = "\n".join(f"{self.fit_table['columns'][i]}：{old[i]} → {new[i] or '（空白）'}" for i in changed)
            if not messagebox.askyesno("确认修改已有数据", f"以下修改会覆盖原值，无法撤销：\n\n{details}\n\n确定保存吗？", parent=parent, icon="warning", default="no"):
                return False
        self.fit_table.item(row, values=new)
        if tuple(old) != tuple(new):
            self._invalidate_fit()
        return True


    def delete_fitting_rows(self):
        selected = self.fit_table.selection()
        if not selected:
            return
        if messagebox.askyesno("确认删除", f"即将删除选中的 {len(selected)} 行数据，无法撤销。\n\n确定删除吗？", parent=self, icon="warning", default="no"):
            self.fit_table.delete(*selected)
            self.checked_rows.difference_update(selected)
            self._invalidate_fit()
            self._fit_selection_changed()


    def _close(self):
        if self._fitting_rows() != self.exported_rows and not messagebox.askyesno(
                "确认退出", "拟合表格有尚未导出的修改，关闭程序后这些修改会丢失。\n请先取消退出并使用“导出 TXT”保存。\n\n仍要退出吗？",
                parent=self, icon="warning", default="no"):
            return
        self.destroy()


    def open_image(self):
        path = filedialog.askopenfilename(title="选择图片", filetypes=[
            ("图片", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif"), ("所有文件", "*.*")])
        if path:
            self.open_path(path)


    def set_view(self, fit):
        self.fit = fit
        self.drag_anchor = self.drag_box = None
        self._update_samples()
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._render()


    def _resize(self, event):
        if self.resize_job:
            self.after_cancel(self.resize_job)
        self.resize_job = self.after(80, self._render)


    def _render(self):
        self.resize_job = None
        self.canvas.delete("all")
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.image is None:
            self.canvas.create_text(cw / 2, ch / 2, text="点击「打开图片」开始分析\n\nbackground 选背景区域 · signal 选信号区域", fill="#ced7e3", font=("Microsoft YaHei UI", 16), justify="center")
            return
        iw, ih = self.image.size
        scale = min(cw / iw, ch / ih, 1.0) if self.fit else 1.0
        dw, dh = max(1, round(iw * scale)), max(1, round(ih * scale))
        self.display_size = (dw, dh)
        self.offset = (max(0, (cw - dw) // 2), max(0, (ch - dh) // 2))
        display = self.image if (dw, dh) == self.image.size else self.image.resize((dw, dh), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(display, master=self)
        self.canvas.create_image(*self.offset, anchor="nw", image=self.photo)
        self.canvas.configure(scrollregion=(0, 0, max(cw, dw), max(ch, dh)))
        self._draw_markers()
        self.status_text.set(f"显示比例：{dw / iw:.1%}  |  Ctrl+O 打开图片 · Esc 清除选区 · 100% 模式可用滚动条浏览")


    def _point(self, event, clamp=False):
        if self.image is None:
            return None
        return image_point(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y),
                           self.offset, self.display_size, self.image.size, clamp)


    def _press(self, event):
        if self.pick_mode.get() not in self.samples:
            return
        self.drag_anchor = self._point(event)
        if self.drag_anchor is not None:
            self.drag_box = region_box(self.drag_anchor, self.drag_anchor)
            self.add_fit_button.configure(state="disabled")
            self._draw_markers()

    def _motion(self, event):
        if self.drag_anchor is not None:
            self.drag_box = region_box(self.drag_anchor, self._point(event, clamp=True))
            self._draw_markers()

    def _release(self, event):
        if self.drag_anchor is None:
            return
        self._motion(event)
        mode = self.pick_mode.get()
        if mode in self.samples:
            self.samples[mode] = self.drag_box
        self.drag_anchor = self.drag_box = None
        self.pick_mode.set("")
        self._update_samples()




if __name__ == "__main__":
    OpticalContrastInspector().mainloop()
