"""Exercise the actual Tk canvas event bindings with a generated reference image."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from rgb_inspector import RGBInspector


app = RGBInspector()
try:
    app.update()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "reference.png"
        image = Image.new("RGB", (10, 10), (10, 20, 30))
        image.putpixel((0, 0), (110, 120, 130))
        image.save(path)
        assert app.open_path(path)
        app.update()
        ox, oy = app.offset
        for event in ("<ButtonPress-1>", "<ButtonRelease-1>"):
            app.canvas.event_generate(event, x=ox, y=oy)
        assert app.values["pixel", 0].get() == "110"
        assert app.values["std", 0].get() == "0.0000"
        app.canvas.event_generate("<ButtonPress-1>", x=ox + 9, y=oy + 9)
        app.canvas.event_generate("<B1-Motion>", x=ox, y=oy)
        app.canvas.event_generate("<ButtonRelease-1>", x=ox, y=oy)
        assert app.selection == (0, 0, 10, 10)
        assert app.values["mean", 0].get() == "11.0000"
        assert app.values["std", 0].get() == "9.9499"
        app.set_view(False)
        app.update()
        assert app.display_size == (10, 10)
        app.clear_selection()
        assert app.values["mean", 0].get() == "—"
        print("PASS: Tk image loading, click, reverse drag, statistics, 100% view, clear")
finally:
    app.destroy()
