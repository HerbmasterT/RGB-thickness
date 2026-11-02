"""End-to-end synthetic rectangle sampling, signed contrast and regression."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import ttk
from PIL import Image
from optical_contrast_inspector import OpticalContrastInspector, read_fitting_txt


app = OpticalContrastInspector()
try:
    app.update()
    assert app.add_fit_button.instate(["disabled"])
    assert tuple(app.fit_table["columns"]) == ("C_R", "C_G", "C_B", "厚度(nm)")
    assert app.fit_channel.get() == "C_G"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "hbn_synthetic.png"
        image = Image.new("RGB", (40, 20), (100, 100, 100))
        image.paste((110, 120, 90), (20, 0, 40, 20))
        image.save(path)
        assert app.open_path(path)
        app.update()

        def drag(button, start, end):
            button.invoke()
            ox, oy = app.offset
            app.canvas.event_generate("<ButtonPress-1>", x=ox + start[0], y=oy + start[1])
            assert app.add_fit_button.instate(["disabled"])
            app.canvas.event_generate("<B1-Motion>", x=ox + end[0], y=oy + end[1])
            app.canvas.event_generate("<ButtonRelease-1>", x=ox + end[0], y=oy + end[1])

        drag(app.background_button, (19, 19), (0, 0))
        assert app.samples["background"] == (0, 0, 20, 20)
        assert app.add_fit_button.instate(["disabled"])
        drag(app.signal_button, (20, 0), (39, 19))
        assert app.current_contrasts() == (-.1, -.2, .1)
        assert "400 像素" in app.sample_text.get()
        app.add_fit_button.invoke()
        first = app.fit_table.get_children()[0]
        assert app.fit_table.item(first, "values") == ("-0.1", "-0.2", "0.1", "")
        app.edit_fitting_row()
        app.update()
        dialog = next(child for child in app.winfo_children() if isinstance(child, tk.Toplevel))
        body = dialog.winfo_children()[0]
        entries = [child for child in body.winfo_children() if isinstance(child, ttk.Entry)]
        assert len(entries) == 4
        entries[3].insert(0, "10")
        buttons = next(child for child in body.winfo_children() if isinstance(child, ttk.Frame))
        save = next(child for child in buttons.winfo_children() if child.cget("text") == "保存")
        with patch("optical_contrast_inspector.messagebox.askyesno") as confirm:
            save.invoke()
            confirm.assert_not_called()

        image.paste((120, 140, 80), (20, 0, 40, 20))
        image.save(path)
        assert app.open_path(path)
        app.update()
        assert all(box is None for box in app.samples.values())
        assert len(app.fit_table.get_children()) == 1
        drag(app.background_button, (0, 0), (19, 19))
        drag(app.signal_button, (39, 19), (20, 0))
        app.add_fit_button.invoke()
        second = app.fit_table.get_children()[1]
        app.update_fitting_row(second, (-.2, -.4, .2, 20))
        app.notebook.select(app.regression_tab)
        app.update()
        app.run_fit_button.invoke()
        assert abs(app.fit_result["slope"] + 50) < 1e-10
        assert abs(app.fit_result["intercept"]) < 1e-10
        assert len(app.plot_canvas.find_withtag("data_point")) == 2
        app.show_residuals.set(True)
        app._draw_fit_plot()
        assert any(app.plot_canvas.itemcget(item, "text") == "━ 零残差" for item in app.plot_canvas.find_all()
                   if app.plot_canvas.type(item) == "text")
        app.channel_picker.set("C_B")
        app.channel_picker.event_generate("<<ComboboxSelected>>")
        assert app.fit_result is None
        app.run_fitting()
        assert abs(app.fit_result["slope"] - 100) < 1e-10
        app.geometry("760x600")
        app.update()
        assert app.plot_canvas.winfo_height() > 180
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=False):
            assert not app.update_fitting_row(first, (-.15, -.2, .1, 10))
        assert app.fit_result is not None
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=True):
            assert app.update_fitting_row(first, (-.15, -.2, .1, 10))
        assert app.fit_result is None
        app.toggle_fitting_row(first)
        with patch("optical_contrast_inspector.messagebox.showerror") as error:
            app.run_fitting()
            error.assert_called_once()
        app.toggle_fitting_row(first)

        txt = Path(folder) / "contrast.txt"
        with patch("optical_contrast_inspector.filedialog.asksaveasfilename", return_value=str(txt)):
            app.export_fitting()
        assert tuple(read_fitting_txt(txt)) == app._fitting_rows()
        with patch("optical_contrast_inspector.filedialog.askopenfilename", return_value=str(txt)):
            app.import_fitting()
        assert len(app.fit_table.get_children()) == 4
        txt.write_text("C_R C_G C_B 厚度\n0 0 0 0\n0 nan 0 1", encoding="utf-8")
        with patch("optical_contrast_inspector.filedialog.askopenfilename", return_value=str(txt)), patch("optical_contrast_inspector.messagebox.showerror"):
            app.import_fitting()
        assert len(app.fit_table.get_children()) == 4
        app.fit_table.selection_set(first, second)
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=False):
            app.delete_fitting_rows()
        assert len(app.fit_table.get_children()) == 4
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=True):
            app.delete_fitting_rows()
        assert len(app.fit_table.get_children()) == 2

        # A zero background channel must not prevent usable green contrast.
        image.paste((0, 100, 0), (0, 0, 20, 20))
        image.save(path)
        app.open_path(path)
        app.update()
        drag(app.background_button, (0, 0), (19, 19))
        drag(app.signal_button, (20, 0), (39, 19))
        assert app.current_contrasts() == (None, -.4, None)
        app.add_fit_button.invoke()
        last = app.fit_table.get_children()[-1]
        assert app.fit_table.item(last, "values") == ("", "-0.4", "", "")
        app.check_all_rows(False)
        app.toggle_fitting_row(last)
        app.update_fitting_row(last, ("", -.4, "", 20))
        with patch("optical_contrast_inspector.messagebox.showerror") as error:
            app.run_fitting()  # C_B is still selected and undefined.
            assert "C_B" in error.call_args.args[1]
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=False):
            app._close()
        assert app.winfo_exists()
        app.clear_regions()
        assert app.add_fit_button.instate(["disabled"])
    print("PASS: rectangle means/reverse drag, signed channels, default green, residuals, channel switch, TXT, protections, zero background, image reset")
finally:
    app.destroy()
