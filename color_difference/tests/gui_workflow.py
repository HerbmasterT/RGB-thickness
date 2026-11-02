"""Synthetic end-to-end test of the standalone color-difference workflow."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import ttk
from PIL import Image
from color_difference_inspector import ColorDifferenceInspector, read_fitting_txt


app = ColorDifferenceInspector()
try:
    app.update()
    assert app.background_button.instate(["disabled"])
    assert app.add_fit_button.instate(["disabled"])
    assert tuple(app.fit_table["columns"]) == ("色差 ΔE76", "厚度")
    assert not hasattr(app, "component_picker")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "image.png"
        image = Image.new("RGB", (32, 32), (0, 0, 0))
        image.putpixel((31, 31), (255, 255, 255))
        image.save(path)
        assert app.open_path(path)
        app.update()

        def pick(button, x, y):
            button.invoke()
            ox, oy = app.offset
            app.canvas.event_generate("<Button-1>", x=ox + x, y=oy + y)

        pick(app.background_button, 0, 0)
        assert app.samples["background"] == (0, 0)
        assert app.add_fit_button.instate(["disabled"])
        pick(app.signal_button, 31, 31)
        assert app.samples["signal"] == (31, 31)
        assert abs(app.current_difference() - 100) < 1e-10
        assert app.canvas.find_withtag("sample_marker")
        app.add_fit_button.invoke()
        first = app.fit_table.get_children()[0]
        assert len(app.fit_table.item(first, "values")) == 2
        assert app.fit_table.item(first, "values")[1] == ""
        assert first in app.checked_rows
        app.edit_fitting_row()
        app.update()
        dialog = next(child for child in app.winfo_children() if isinstance(child, tk.Toplevel))
        body = dialog.winfo_children()[0]
        entries = [child for child in body.winfo_children() if isinstance(child, ttk.Entry)]
        assert len(entries) == 2
        entries[1].insert(0, "203")
        buttons = next(child for child in body.winfo_children() if isinstance(child, ttk.Frame))
        save = next(child for child in buttons.winfo_children() if child.cget("text") == "保存")
        with patch("color_difference_inspector.messagebox.askyesno") as confirm:
            save.invoke()
            confirm.assert_not_called()

        image.putpixel((31, 31), (128, 128, 128))
        image.save(path)
        assert app.open_path(path)
        app.update()
        assert all(point is None for point in app.samples.values())
        assert app.add_fit_button.instate(["disabled"])
        assert len(app.fit_table.get_children()) == 1
        # Outside-image clicks must not create a sample.
        app.background_button.invoke()
        app.canvas.event_generate("<Button-1>", x=0, y=0)
        assert app.samples["background"] is None
        pick(app.background_button, 0, 0)
        pick(app.signal_button, 31, 31)
        difference = app.current_difference()
        app.add_fit_button.invoke()
        second = app.fit_table.get_children()[1]
        assert app.update_fitting_row(second, (difference, 2 * difference + 3))
        app.notebook.select(app.regression_tab)
        app.update()
        app.run_fit_button.invoke()
        assert abs(app.fit_result["slope"] - 2) < 1e-10
        assert abs(app.fit_result["intercept"] - 3) < 1e-10
        assert app.fit_result["r_squared"] == 1
        assert len(app.plot_canvas.find_withtag("data_point")) == 2
        assert len(app.plot_canvas.find_withtag("fit_line")) == 1
        app.geometry("760x600")
        app.update()
        assert app.plot_canvas.winfo_height() > 180
        with patch("color_difference_inspector.messagebox.askyesno", return_value=False):
            assert not app.update_fitting_row(first, (99, 200))
        assert app.fit_result is not None
        with patch("color_difference_inspector.messagebox.askyesno", return_value=True):
            assert app.update_fitting_row(first, (99, 200))
        assert app.fit_result is None
        app.toggle_fitting_row(first)
        with patch("color_difference_inspector.messagebox.showerror") as error:
            app.run_fitting()
            error.assert_called_once()
        app.toggle_fitting_row(first)
        table_path = Path(folder) / "table.txt"
        with patch("color_difference_inspector.filedialog.asksaveasfilename", return_value=str(table_path)):
            app.export_fitting()
        saved = app._fitting_rows()
        assert tuple(read_fitting_txt(table_path)) == saved
        assert app.exported_rows == saved
        with patch("color_difference_inspector.filedialog.askopenfilename", return_value=str(table_path)):
            app.import_fitting()
        assert len(app.fit_table.get_children()) == 4
        table_path.write_text("1 2\nR G B 厚度", encoding="utf-8")
        with patch("color_difference_inspector.filedialog.askopenfilename", return_value=str(table_path)), patch("color_difference_inspector.messagebox.showerror"):
            app.import_fitting()
        assert len(app.fit_table.get_children()) == 4
        app.fit_table.selection_set(first, second)
        with patch("color_difference_inspector.messagebox.askyesno", return_value=False):
            app.delete_fitting_rows()
        assert len(app.fit_table.get_children()) == 4
        with patch("color_difference_inspector.messagebox.askyesno", return_value=True):
            app.delete_fitting_rows()
        assert len(app.fit_table.get_children()) == 2
        assert first not in app.checked_rows
        # Removing originals leaves their imported copies: values equal the export.
        # Make a new change before checking the unsaved-data exit warning.
        app._insert_fitting_row((25, ""))
        with patch("color_difference_inspector.messagebox.askyesno", return_value=False):
            app._close()
        assert app.winfo_exists()
        app.clear_points()
        assert app.add_fit_button.instate(["disabled"])
    print("PASS: background/signal, full-precision delta E, image reset, two-column edit, selection, regression plot, TXT, protections")
finally:
    app.destroy()
