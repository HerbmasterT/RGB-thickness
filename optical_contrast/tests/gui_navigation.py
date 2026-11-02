"""Exercise real Tk bindings with synthetic pixels; no measurement data is used."""
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from optical_contrast_inspector import OpticalContrastInspector, region_box


app = OpticalContrastInspector()
try:
    app.update()
    app.canvas.event_generate("<MouseWheel>", x=10, y=10, delta=120)
    assert app.image is None
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "navigation.png"
        image = Image.new("RGB", (1200, 800), (100, 100, 100))
        image.paste((110, 120, 90), (600, 0, 1200, 800))
        image.save(path)
        app.open_path(path)
        app.update()
        app._render()
        app.samples = {"background": (0, 0, 100, 100), "signal": (900, 0, 1000, 100)}
        app._update_samples()
        app._insert_fitting_row((0, 0, 0, 0))
        app._insert_fitting_row((-.2, -.4, .2, 20))
        app.run_fitting()
        app.calculate_thickness()
        samples, contrasts = app.samples.copy(), app.current_contrasts()
        prediction = app.thickness_result.copy()
        calibration = app.fit_result
        app.signal_button.invoke()
        app.calculate_thickness()

        x, y = app.canvas.winfo_width() // 2, app.canvas.winfo_height() // 2
        event = SimpleNamespace(x=x, y=y)
        before = app._point(event)
        initial_zoom = app.zoom
        for _ in range(8):
            app.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=120)
        assert app.zoom > initial_zoom and not app.fit
        after = app._point(event)
        assert max(abs(a-b) for a, b in zip(before, after)) <= 3
        assert app.samples == samples and app.current_contrasts() == contrasts
        assert app.thickness_result == prediction and app.fit_result is calibration
        assert app.photo.width() <= app.canvas.winfo_width() + 1
        assert app.photo.height() <= app.canvas.winfo_height() + 1

        # Dragging moves the image with the mouse without selecting a region.
        old_x, old_y = app.canvas.canvasx(0), app.canvas.canvasy(0)
        app.canvas.event_generate("<ButtonPress-3>", x=x, y=y)
        assert app.panning
        app.canvas.event_generate("<B3-Motion>", x=x-75, y=y-40)
        assert abs(app.canvas.canvasx(0) - old_x - 75) <= 1
        assert abs(app.canvas.canvasy(0) - old_y - 40) <= 1
        app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        assert app.drag_anchor is None
        app.canvas.event_generate("<ButtonRelease-3>", x=x-75, y=y-40)
        assert not app.panning and app.canvas.cget("cursor") == "crosshair"
        assert app.samples == samples and app.pick_mode.get() == "signal"
        assert app.thickness_result == prediction

        # Visible rendered pixels and left-button sampling agree after pan/zoom.
        point = app._point(event)
        left, top = app.canvas.coords(app.canvas.find_withtag("image")[0])
        pixel = app.tk.call(str(app.photo), "get", int(app.canvas.canvasx(x)-left), int(app.canvas.canvasy(y)-top))
        assert tuple(pixel) == image.getpixel(point)
        end = SimpleNamespace(x=x+30, y=y+20)
        expected = region_box(point, app._point(end))
        app.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        zoom = app.zoom
        app.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=-120)
        app.canvas.event_generate("<ButtonPress-3>", x=x, y=y)
        assert app.zoom == zoom and not app.panning
        app.canvas.event_generate("<B1-Motion>", x=end.x, y=end.y)
        app.canvas.event_generate("<ButtonRelease-1>", x=end.x, y=end.y)
        assert app.samples["signal"] == expected
        assert app.thickness_result is None

        # Scrollbars repaint the viewport, and pan is confined to image boundaries.
        app._scroll_x("moveto", 1)
        app._scroll_y("moveto", 1)
        assert app.canvas.xview()[1] == 1 and app.canvas.yview()[1] == 1
        assert app.canvas.find_withtag("image")
        app.canvas.event_generate("<ButtonPress-3>", x=x, y=y)
        app.canvas.event_generate("<B3-Motion>", x=-10000, y=-10000)
        app.canvas.event_generate("<ButtonRelease-3>", x=-10000, y=-10000)
        assert app.canvas.xview()[1] == 1 and app.canvas.yview()[1] == 1

        app.set_view(False)
        assert app.zoom == 1 and app.display_size == image.size
        assert app.canvas.canvasx(0) == 0 and app.canvas.canvasy(0) == 0
        app.set_view(True)
        assert app.fit and app.display_size[0] <= app.canvas.winfo_width()
        assert app.display_size[1] <= app.canvas.winfo_height()
        app.canvas.event_generate("<ButtonPress-3>", x=x, y=y)
        assert not app.panning
        # Linux wheel bindings and both zoom limits.
        app.canvas.event_generate("<Button-4>", x=x, y=y)
        z = app.zoom
        app.canvas.event_generate("<Button-5>", x=x, y=y)
        assert app.zoom < z
        for _ in range(6):
            app.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=1200)
        assert app.zoom == 32
        assert app.photo.width() <= app.canvas.winfo_width() + 1
        for _ in range(6):
            app.canvas.event_generate("<MouseWheel>", x=x, y=y, delta=-1200)
        assert app.zoom == .05
        z = app.zoom
        app.canvas.event_generate("<MouseWheel>", x=0, y=0, delta=120)
        assert app.zoom == z  # Outside the small, centered image.
        app.open_path(path)
        app.update()
        assert app.fit and not app.panning
        assert all(box is None for box in app.samples.values())
    print("PASS: anchored wheel zoom, right drag, bounds, viewport pixels, ROI mapping, zoom limits, reset, prediction preservation")
finally:
    app.destroy()
