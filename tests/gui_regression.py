"""Exercise real checkbox events, regression plotting and invalidation."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rgb_inspector import RGBInspector


app = RGBInspector()
try:
    app.update()
    assert [app.notebook.tab(tab, "text") for tab in app.notebook.tabs()] == ["图片分析", "拟合数据", "拟合"]
    rows = [app._insert_fitting_row(values) for values in [(255, 0, 0, 3), (255, 255, 0, 123), (0, 255, 0, 243), (1, 0, 0, "")]]
    assert len(app.checked_rows) == 4
    app.notebook.select(app.fitting_tab)
    app.update()
    x, y, w, h = app.fit_table.bbox(rows[-1], "#0")
    app.fit_table.event_generate("<Button-1>", x=x + 25, y=y + h // 2)
    assert rows[-1] not in app.checked_rows
    assert app.fit_table.item(rows[-1], "text") == "☐"
    app.notebook.select(app.regression_tab)
    app.update()
    app.run_fit_button.invoke()
    app.update()
    assert app.fit_result["slope"] == 2
    assert app.fit_result["intercept"] == 3
    assert app.fit_result["r_squared"] == 1
    assert len(app.plot_canvas.find_withtag("data_point")) == 3
    assert len(app.plot_canvas.find_withtag("fit_line")) == 1
    app.geometry("760x600")
    app.update()
    assert len(app.plot_canvas.find_withtag("data_point")) == 3
    assert app.plot_canvas.winfo_height() > 180
    with patch("rgb_inspector.messagebox.askyesno", return_value=False):
        assert not app.update_fitting_row(rows[0], (255, 0, 0, 6))
    assert app.fit_result is not None
    with patch("rgb_inspector.messagebox.askyesno", return_value=True):
        assert app.update_fitting_row(rows[0], (255, 0, 0, 6))
    assert app.fit_result is None
    assert not app.plot_canvas.find_withtag("fit_line")
    app.check_all_rows(True)
    with patch("rgb_inspector.messagebox.showerror") as error:
        app.run_fit_button.invoke()
        error.assert_called_once()
    assert app.fit_result is None
    app.check_all_rows(False)
    with patch("rgb_inspector.messagebox.showerror") as error:
        app.run_fitting()
        error.assert_called_once()
    app.toggle_fitting_row(rows[1])
    app.toggle_fitting_row(rows[2])
    app.run_fitting()
    assert len(app.fit_result["points"]) == 2
    app.fit_table.selection_set(rows[2])
    with patch("rgb_inspector.messagebox.askyesno", return_value=True):
        app.delete_fitting_rows()
    assert rows[2] not in app.checked_rows
    assert app.fit_result is None
    app.check_all_rows(False)
    for values in [(255, 0, 0, 100), (127.5, 63.75, 63.75, 50), (63.75, 47.8125, 47.8125, 25)]:
        app._insert_fitting_row(values)
    for component in ("S", "V"):
        app.component_picker.set(component)
        app.component_picker.event_generate("<<ComboboxSelected>>")
        assert app.fit_result is None
        assert app.hue_unwrap_button.instate(["disabled"])
        app.run_fit_button.invoke()
        assert app.fit_result["slope"] == 1
        assert app.fit_result["x_label"] == f"{component} (%)"
        assert any(app.plot_canvas.itemcget(item, "text") == f"{component} (%)"
                   for item in app.plot_canvas.find_all() if app.plot_canvas.type(item) == "text")
    app.component_picker.set("H")
    app.component_picker.event_generate("<<ComboboxSelected>>")
    assert app.hue_unwrap_button.instate(["!disabled"])
    app.check_all_rows(False)
    app._insert_fitting_row((255, 0, 4.25, 9))
    app._insert_fitting_row((255, 4.25, 0, 11))
    app.hue_unwrap_button.invoke()
    app.run_fitting()
    assert abs(app.fit_result["slope"] - 1) < 1e-10
    assert app.fit_result["unwrap_hue"]
    app._insert_fitting_row((127, 127, 127, 10))
    with patch("rgb_inspector.messagebox.showerror") as error:
        app.run_fitting()
        assert "色相 H 未定义" in error.call_args.args[1]
    print("PASS: checkbox, HSV regression, plot/resize, H/S/V selector, hue unwrap, achromatic validation, edit/delete invalidation")
finally:
    app.destroy()
