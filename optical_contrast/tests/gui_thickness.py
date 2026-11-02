"""Synthetic checks for prediction, channel provenance and stale-result handling."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from optical_contrast_inspector import OpticalContrastInspector


app = OpticalContrastInspector()
try:
    app.update()
    assert app.thickness_button.instate(["disabled"])
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.png"
        image = Image.new("RGB", (40, 20), (100, 100, 100))
        image.paste((110, 120, 90), (20, 0, 40, 20))
        image.save(path)
        app.open_path(path)
        app.update()

        def sample(button, start, end):
            button.invoke()
            ox, oy = app.offset
            app.canvas.event_generate("<ButtonPress-1>", x=ox + start[0], y=oy + start[1])
            assert app.thickness_result is None
            assert app.thickness_button.instate(["disabled"])
            app.canvas.event_generate("<B1-Motion>", x=ox + end[0], y=oy + end[1])
            app.canvas.event_generate("<ButtonRelease-1>", x=ox + end[0], y=oy + end[1])

        sample(app.background_button, (0, 0), (19, 19))
        sample(app.signal_button, (39, 19), (20, 0))
        assert app.thickness_button.instate(["disabled"])
        first = app._insert_fitting_row((0, 0, 0, 2))
        app._insert_fitting_row((-.5, -.4, .1, 22))
        for channel, expected in (("C_G", 12), ("C_B", 22), ("C_R", 6)):
            app.channel_picker.set(channel)
            app._channel_changed()
            assert app.thickness_result is None
            assert app.thickness_button.instate(["disabled"])
            app.run_fitting()
            assert app.thickness_button.instate(["!disabled"])
            before = app._fitting_rows()
            app.thickness_button.invoke()
            assert abs(app.thickness_result["thickness"] - expected) < 1e-10
            assert f"使用通道：{channel}" in app.thickness_text.get()
            assert "nm" in app.thickness_text.get()
            assert app._fitting_rows() == before
            assert app.notebook.select() == str(app.analysis_tab)

        # Single pixels also work; a new selection clears the previous result.
        sample(app.signal_button, (20, 0), (20, 0))
        assert app.thickness_result is None
        app.thickness_button.invoke()
        assert abs(app.thickness_result["thickness"] - 6) < 1e-10
        app.toggle_fitting_row(first)
        assert app.thickness_result is None
        assert app.thickness_button.instate(["disabled"])
        with patch("optical_contrast_inspector.messagebox.showerror"):
            app.run_fitting()
        assert app.fit_result is None
        app.toggle_fitting_row(first)
        app.run_fitting()
        app.calculate_thickness()
        with patch("optical_contrast_inspector.messagebox.askyesno", return_value=True):
            app.update_fitting_row(first, (0, 0, 0, 3))
        assert app.thickness_result is None
        assert app.thickness_button.instate(["disabled"])
        app.run_fitting()

        # Keep the calibration across images, but never keep a previous prediction.
        saved_fit = app.fit_result
        image.paste((0, 100, 0), (0, 0, 20, 20))
        image.save(path)
        app.open_path(path)
        app.update()
        assert app.fit_result is saved_fit
        assert app.thickness_result is None
        assert app.thickness_button.instate(["disabled"])
        sample(app.background_button, (0, 0), (19, 19))
        sample(app.signal_button, (20, 0), (39, 19))
        assert app.thickness_button.instate(["disabled"])
        assert "C_R 未定义" in app.thickness_text.get()
        app.channel_picker.set("C_G")
        app._channel_changed()
        app.run_fitting()
        app.thickness_button.invoke()
        assert app.thickness_result["channel"] == "C_G"

        # Negative estimates remain visible and are marked as extrapolation.
        image.paste((100, 100, 100), (0, 0, 20, 20))
        image.paste((90, 90, 90), (20, 0, 40, 20))
        image.save(path)
        app.open_path(path)
        app.update()
        sample(app.background_button, (0, 0), (19, 19))
        sample(app.signal_button, (20, 0), (39, 19))
        app.thickness_button.invoke()
        assert app.thickness_result["thickness"] < 0
        assert "外推" in app.thickness_text.get() and "负值" in app.thickness_text.get()
        app.geometry("760x600")
        app.update()
        assert app.canvas.winfo_height() > 80
        assert app.thickness_label.winfo_rooty() + app.thickness_label.winfo_height() < app.analysis_tab.winfo_rooty() + app.analysis_tab.winfo_height()
        assert app.thickness_button.winfo_x() + app.thickness_button.winfo_width() < app.thickness_button.master.winfo_width()
        app.clear_regions()
        assert app.thickness_result is None
        assert app.thickness_button.instate(["disabled"])
    print("PASS: thickness prediction, all channels, invalidation, new images, zero background, extrapolation, minimum layout")
finally:
    app.destroy()
