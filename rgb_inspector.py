"""Local RGB pixel and rectangular region inspector."""

from __future__ import annotations

import colorsys
import math
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageStat, ImageTk


FIT_COLUMNS = ("R", "G", "B", "厚度")
HSV_LABELS = {"H": "H (°)", "S": "S (%)", "V": "V (%)"}


def rgb_to_hsv_values(r, g, b):
    """Convert encoded RGB (0–255) into H degrees and S/V percentages."""
    h, s, v = colorsys.rgb_to_hsv(float(r) / 255, float(g) / 255, float(b) / 255)
    return h * 360, s * 100, v * 100


def hsv_fit_point(row, component="H", unwrap_hue=False):
    if component not in HSV_LABELS:
        raise ValueError("请选择 H、S 或 V 分量。")
    r, g, b, thickness = validate_fitting_values(row)
    if thickness == "":
        raise ValueError("厚度为空，请填写或取消勾选。")
    h, s, v = rgb_to_hsv_values(r, g, b)
    if component == "H" and s == 0:
        raise ValueError("RGB 为灰色或黑白，色相 H 未定义；请取消勾选或改用 S / V。")
    if unwrap_hue and h >= 180:
        h -= 360
    return {"H": h, "S": s, "V": v}[component], float(thickness)


def linear_fit(rows, component="H", unwrap_hue=False):
    """Ordinary least squares: thickness = slope * HSV component + intercept."""
    if component not in HSV_LABELS:
        raise ValueError("请选择 H、S 或 V 分量。")
    points = []
    for row in rows:
        points.append(hsv_fit_point(row, component, unwrap_hue))
    if len(points) < 2:
        raise ValueError("至少需要勾选两行有效数据。")
    try:
        n = len(points)
        mx = math.fsum(x / n for x, _ in points)
        my = math.fsum(y / n for _, y in points)
        sxx = math.fsum((x - mx) ** 2 for x, _ in points)
        if sxx == 0:
            raise ValueError(f"所选数据的 {component} 分量全部相同，无法确定斜率。")
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
                mean_x=mx, mean_y=my, component=component,
                x_label=HSV_LABELS[component], unwrap_hue=bool(unwrap_hue and component == "H"))


def validate_fitting_values(values):
    values = tuple(str(value).strip() for value in values)
    if len(values) != 4:
        raise ValueError("每行必须有四列：R、G、B、厚度。")
    for index, value in enumerate(values):
        if index == 3 and value == "":
            continue
        try:
            number = float(value)
        except ValueError:
            raise ValueError(f"{FIT_COLUMNS[index]} 必须是数值。") from None
        if not math.isfinite(number) or number < 0 or (index < 3 and number > 255):
            raise ValueError("RGB 必须为 0–255 的有限数值；厚度必须为非负有限数值或留空。")
    return values


def parse_fitting_text(text):
    """Validate the entire document before allowing any table mutation."""
    rows = []
    first = True
    for line_number, line in enumerate(text.lstrip("\ufeff").splitlines(), start=1):
        if not line.strip():
            continue
        # Preserve empty thickness fields in tab/comma-separated files.
        values = tuple(part.strip() for part in (
            line.split("\t") if "\t" in line else line.split(",") if "," in line else line.split()))
        if first and tuple(value.lower() for value in values) in (
                ("r", "g", "b", "厚度"), ("r", "g", "b", "thickness")):
            first = False
            continue
        first = False
        try:
            rows.append(validate_fitting_values(values))
        except ValueError as exc:
            raise ValueError(f"第 {line_number} 行：{exc}") from exc
    if first:
        raise ValueError("文件为空，请提供表头或四列数据。")
    return rows


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
                                         prefix=".rgb-export-", suffix=".tmp", delete=False) as output:
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


def region_box(start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int, int, int]:
    """Include both endpoint pixels; return Pillow's exclusive right/bottom box."""
    return (min(start[0], end[0]), min(start[1], end[1]),
            max(start[0], end[0]) + 1, max(start[1], end[1]) + 1)


def region_statistics(image: Image.Image, box: tuple[int, int, int, int]):
    """Return channel means and population standard deviations, using source pixels."""
    left, top, right, bottom = box
    if image.mode != "RGB":
        raise ValueError("统计图像必须为 RGB 模式。")
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError("选区必须在图像内且至少包含一个像素。")
    stats = ImageStat.Stat(image.crop(box))
    return tuple(stats.mean), tuple(stats.stddev)


def image_point(x, y, offset, display_size, image_size, clamp=False):
    """Map canvas coordinates using actual rounded display dimensions."""
    dx, dy = x - offset[0], y - offset[1]
    dw, dh = display_size
    iw, ih = image_size
    if not clamp and not (0 <= dx < dw and 0 <= dy < dh):
        return None
    return (max(0, min(iw - 1, math.floor(dx * iw / dw))),
            max(0, min(ih - 1, math.floor(dy * ih / dh))))


class RGBInspector(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RGB 像素分析工具")
        self.geometry("1120x780")
        self.minsize(760, 600)
        self.image = None
        self.photo = None
        self.fit = True
        self.offset = (0, 0)
        self.display_size = (1, 1)
        self.selection = None
        self.anchor = None
        self.press_position = None
        self.dragging = False
        self.resize_job = None
        self.current_rgb = None
        self.exported_rows = ()
        self.checked_rows = set()
        self.fit_result = None
        self.file_text = tk.StringVar(value="尚未打开图片")
        self.selection_text = tk.StringVar(value="点击图片读取单像素；按住鼠标左键拖拽选择矩形。")
        self.status_text = tk.StringVar(value="准备就绪")
        self._build_ui()
        self.bind("<Control-o>", lambda event: self.open_image())
        self.bind("<Escape>", lambda event: self.clear_selection())
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        style = ttk.Style(self)
        # Clam honors tab colors on Windows, unlike native themed tab elements.
        style.theme_use("clam")
        style.configure("Main.TNotebook", background="#dce5f2", tabmargins=(12, 10, 12, 0))
        style.configure("Main.TNotebook.Tab", font=("Microsoft YaHei UI", 16, "bold"),
                        padding=(36, 14), background="#e2e8f0", foreground="#334155")
        style.map("Main.TNotebook.Tab", background=[("selected", "#1d4ed8"), ("active", "#cbdafa")],
                  foreground=[("selected", "white"), ("active", "#1e3a8a")])
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Value.TLabel", font=("Consolas", 13))
        self.notebook = ttk.Notebook(self, style="Main.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.analysis_tab = ttk.Frame(self.notebook)
        self.fitting_tab = ttk.Frame(self.notebook)
        self.regression_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.analysis_tab, text="图片分析")
        self.notebook.add(self.fitting_tab, text="拟合数据")
        self.notebook.add(self.regression_tab, text="拟合")
        toolbar = ttk.Frame(self.analysis_tab, padding=12)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="RGB 像素分析", style="Title.TLabel").pack(side="left", padx=(0, 24))
        ttk.Button(toolbar, text="打开图片…", command=self.open_image).pack(side="left", padx=4)
        ttk.Button(toolbar, text="适应窗口", command=lambda: self.set_view(True)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="100% 显示", command=lambda: self.set_view(False)).pack(side="left", padx=4)
        ttk.Button(toolbar, text="清除选区", command=self.clear_selection).pack(side="left", padx=4)
        self.add_fit_button = ttk.Button(toolbar, text="加入拟合", command=self.add_to_fitting, state="disabled")
        self.add_fit_button.pack(side="left", padx=4)
        ttk.Label(self.analysis_tab, textvariable=self.file_text, padding=(14, 0, 14, 8), wraplength=1000).pack(fill="x")

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

        result = ttk.LabelFrame(self.analysis_tab, text="选区结果 · 原始分辨率 RGB（0–255）", padding=12)
        result.pack(fill="x", padx=12, pady=(8, 4))
        ttk.Label(result, textvariable=self.selection_text).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self.values = {}
        for col, heading in enumerate(("统计量", "R · 红", "G · 绿", "B · 蓝")):
            ttk.Label(result, text=heading).grid(row=1, column=col, sticky="w", padx=(0, 38))
            result.columnconfigure(col, weight=1)
        for row, (key, label) in enumerate((("pixel", "像素值"), ("mean", "均值"), ("std", "标准差（总体）")), start=2):
            ttk.Label(result, text=label).grid(row=row, column=0, sticky="w", pady=3)
            for channel in range(3):
                var = tk.StringVar(value="—")
                self.values[key, channel] = var
                ttk.Label(result, textvariable=var, style="Value.TLabel").grid(row=row, column=channel + 1, sticky="w")
        ttk.Label(self.analysis_tab, text="坐标从左上角 (0, 0) 开始；矩形包含起点与终点像素。缩放仅影响显示。", padding=(14, 4)).pack(fill="x")
        ttk.Label(self.analysis_tab, textvariable=self.status_text, padding=(14, 4, 14, 8)).pack(fill="x")
        self._build_fitting_ui()
        self._build_regression_ui()

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

    def _build_regression_ui(self):
        toolbar = ttk.Frame(self.regression_tab, padding=12)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="HSV 与厚度 · 线性拟合", style="Title.TLabel").pack(side="left", padx=(0, 24))
        self.fit_component = tk.StringVar(value="H")
        self.component_picker = ttk.Combobox(toolbar, textvariable=self.fit_component, values=("H", "S", "V"), state="readonly", width=4)
        self.component_picker.pack(side="left", padx=(0, 12))
        self.component_picker.bind("<<ComboboxSelected>>", self._fit_mode_changed)
        self.run_fit_button = ttk.Button(toolbar, text="开始 / 更新拟合", command=self.run_fitting)
        self.run_fit_button.pack(side="left")
        self.model_text = tk.StringVar(value="模型：厚度 = 斜率 × H + 截距。H：色相（°），S：饱和度（%），V：明度（%）。")
        ttk.Label(self.regression_tab, textvariable=self.model_text, padding=(14, 0, 14, 8)).pack(fill="x")
        options = ttk.Frame(self.regression_tab, padding=(14, 0, 14, 8))
        options.pack(fill="x")
        self.hue_unwrap = tk.BooleanVar(value=False)
        self.hue_unwrap_button = ttk.Checkbutton(options, text="H 跨 0° 展开（180°–360° 映射为负角度）", variable=self.hue_unwrap, command=self._fit_mode_changed)
        self.hue_unwrap_button.pack(side="left")
        ttk.Label(self.regression_tab, text="默认 H∈[0°,360°)，S/V∈[0%,100%]。H 为环形角度，近灰色时不稳定；按数据范围选择展开。", padding=(14, 0, 14, 8), wraplength=700).pack(fill="x")
        self.fit_parameters = tk.StringVar(value="斜率：—     截距：—     R²：—")
        ttk.Label(self.regression_tab, textvariable=self.fit_parameters, style="Title.TLabel", padding=(14, 8), wraplength=700).pack(fill="x")
        self.regression_status = tk.StringVar(value="请勾选数据并点击“开始 / 更新拟合”。")
        ttk.Label(self.regression_tab, textvariable=self.regression_status, padding=(14, 0, 14, 8), wraplength=700).pack(fill="x")
        self.plot_canvas = tk.Canvas(self.regression_tab, background="white", highlightthickness=0)
        self.plot_canvas.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.plot_canvas.bind("<Configure>", lambda event: self._draw_fit_plot())

    def _fit_mode_changed(self, event=None):
        component = self.fit_component.get()
        self.hue_unwrap_button.configure(state="normal" if component == "H" else "disabled")
        self.model_text.set(f"模型：厚度 = 斜率 × {component} + 截距。H：色相（°），S：饱和度（%），V：明度（%）。")
        self._invalidate_fit()

    def _invalidate_fit(self):
        self.fit_result = None
        if hasattr(self, "fit_parameters"):
            self.fit_parameters.set("斜率：—     截距：—     R²：—")
            self.regression_status.set("数据、勾选或拟合设置已改变，请点击“开始 / 更新拟合”。")
            self._draw_fit_plot()

    def run_fitting(self):
        self._invalidate_fit()
        component = self.fit_component.get()
        unwrap = self.hue_unwrap.get()
        rows = []
        for index, row in enumerate(self.fit_table.get_children(), start=1):
            if row not in self.checked_rows:
                continue
            values = self.fit_table.item(row, "values")
            try:
                hsv_fit_point(values, component, unwrap)
            except ValueError as exc:
                reason = f"表格第 {index} 行：{exc}"
                messagebox.showerror("无法拟合", reason, parent=self)
                self.regression_status.set(reason)
                return
            rows.append(values)
        try:
            self.fit_result = linear_fit(rows, component, unwrap)
        except ValueError as exc:
            self.regression_status.set(str(exc))
            messagebox.showerror("无法拟合", str(exc), parent=self)
            return
        result = self.fit_result
        r2 = "未定义（厚度全部相同）" if result["r_squared"] is None else f"{result['r_squared']:.8g}"
        self.fit_parameters.set(f"斜率：{result['slope']:.8g}     截距：{result['intercept']:.8g}     R²：{r2}")
        suffix = "；H 已展开至 [-180°,180°)" if result["unwrap_hue"] else ""
        self.regression_status.set(f"已拟合 {len(rows)} 个等权数据点。横轴：{result['x_label']}；纵轴：厚度（输入单位）{suffix}。")
        self._draw_fit_plot()

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
        points = result["points"]
        xmin, xmax = min(x for x, _ in points), max(x for x, _ in points)
        predict = lambda x: result["mean_y"] + result["slope"] * (x - result["mean_x"])
        line_y = (predict(xmin), predict(xmax))
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
        canvas.create_text(24, (top + bottom) / 2, text="厚度", angle=90, font=("Microsoft YaHei UI", 12))
        xlo, xhi = min(x for x, _ in points), max(x for x, _ in points)
        canvas.create_line(px(xlo), py(line_y[0]), px(xhi), py(line_y[1]), fill="#dc2626", width=2, tags="fit_line")
        for x, y in points:
            cx, cy = px(x), py(y)
            canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#2563eb", outline="white", tags="data_point")
        canvas.create_text(left, 20, text="● 数据点", fill="#2563eb", anchor="w", font=("Microsoft YaHei UI", 11))
        canvas.create_text(left + 120, 20, text="━ 拟合直线", fill="#dc2626", anchor="w", font=("Microsoft YaHei UI", 11))

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
                                            defaultextension=".txt", initialfile="拟合数据.txt",
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

    def add_to_fitting(self):
        if self.current_rgb is None or self.anchor is not None:
            return
        row = self._insert_fitting_row((*self.current_rgb, ""))
        self.fit_table.selection_set(row)
        self.fit_table.focus(row)
        self.fit_table.see(row)
        self.notebook.select(self.fitting_tab)
        self._fit_selection_changed()

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
        ttk.Label(body, text="RGB：0–255；厚度：非负数，可暂时留空。\n首次填写空白厚度可直接保存；覆盖已有值需确认。").grid(row=4, column=0, columnspan=2, pady=10)

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

    def open_path(self, path):
        try:
            loaded = load_rgb(path)
        except Exception as exc:
            messagebox.showerror("无法打开图片", str(exc), parent=self)
            return False
        self.image = loaded
        self.notebook.select(self.analysis_tab)
        self.fit = True
        self.clear_selection()
        self.file_text.set(f"{Path(path).name}  |  {loaded.width} × {loaded.height} 像素")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._render()
        return True

    def set_view(self, fit):
        self.fit = fit
        self.anchor = None
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
            self.canvas.create_text(cw / 2, ch / 2, text="点击「打开图片」开始分析\n\n单击取色 · 拖拽统计矩形区域", fill="#ced7e3", font=("Microsoft YaHei UI", 16), justify="center")
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
        self._draw_selection()
        self.status_text.set(f"显示比例：{dw / iw:.1%}  |  Ctrl+O 打开图片 · Esc 清除选区 · 100% 模式可用滚动条浏览")

    def _point(self, event, clamp=False):
        if self.image is None:
            return None
        return image_point(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y),
                           self.offset, self.display_size, self.image.size, clamp)

    def _press(self, event):
        self.anchor = self._point(event)
        self.press_position = (event.x, event.y)
        self.dragging = False
        if self.anchor is not None:
            self.selection = region_box(self.anchor, self.anchor)
            self._show_result(pixel=True)
            self._draw_selection()

    def _motion(self, event):
        if self.anchor is None:
            return
        if max(abs(event.x - self.press_position[0]), abs(event.y - self.press_position[1])) >= 3:
            self.dragging = True
        if self.dragging:
            self.current_rgb = None
            self.add_fit_button.configure(state="disabled")
            end = self._point(event, clamp=True)
            self.selection = region_box(self.anchor, end)
            left, top, right, bottom = self.selection
            self.selection_text.set(f"正在选择：({left}, {top}) → ({right - 1}, {bottom - 1})  |  松开鼠标计算统计量")
            for var in self.values.values():
                var.set("—")
            self._draw_selection()

    def _release(self, event):
        if self.anchor is None:
            return
        self._motion(event)
        self._show_result(pixel=not self.dragging)
        self._draw_selection()
        self.anchor = None

    def _draw_selection(self):
        self.canvas.delete("selection")
        if self.selection is None or self.image is None:
            return
        left, top, right, bottom = self.selection
        ox, oy = self.offset
        sx, sy = self.display_size[0] / self.image.width, self.display_size[1] / self.image.height
        coords = (ox + left * sx, oy + top * sy, ox + right * sx, oy + bottom * sy)
        self.canvas.create_rectangle(*coords, outline="black", width=3, tags="selection")
        self.canvas.create_rectangle(*coords, outline="#ffffff", width=1, dash=(5, 3), tags="selection")

    def _show_result(self, pixel):
        left, top, right, bottom = self.selection
        count = (right - left) * (bottom - top)
        means, stds = region_statistics(self.image, self.selection)
        rgb = self.image.getpixel((left, top)) if pixel else None
        self.current_rgb = rgb if pixel else means
        self.add_fit_button.configure(state="normal")
        for channel in range(3):
            self.values["pixel", channel].set(str(rgb[channel]) if rgb is not None else "—")
            self.values["mean", channel].set(f"{means[channel]:.4f}")
            self.values["std", channel].set(f"{stds[channel]:.4f}")
        self.selection_text.set(
            f"单像素：({left}, {top})" if pixel else
            f"矩形：({left}, {top}) → ({right - 1}, {bottom - 1})  |  {right - left} × {bottom - top}  |  {count:,} 个像素")

    def clear_selection(self):
        self.selection = None
        self.anchor = None
        self.current_rgb = None
        self.add_fit_button.configure(state="disabled")
        self.canvas.delete("selection")
        for var in self.values.values():
            var.set("—")
        self.selection_text.set("点击图片读取单像素；按住鼠标左键拖拽选择矩形。")


if __name__ == "__main__":
    RGBInspector().mainloop()
