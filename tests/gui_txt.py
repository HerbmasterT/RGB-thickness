"""Verify TXT actions, cancellation, and saved state in a real Tk window."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tkinter import ttk
from rgb_inspector import RGBInspector, read_fitting_txt


app = RGBInspector()
try:
    app.update()
    style = ttk.Style(app)
    assert style.lookup("Main.TNotebook.Tab", "background", ("selected",)) == "#1d4ed8"
    app.notebook.select(app.fitting_tab)
    app.geometry("760x600")
    app.update()
    assert app.export_fit_button.winfo_rootx() + app.export_fit_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
    row = app.fit_table.insert("", "end", values=("1", "2", "3", ""))
    initial = app._fitting_rows()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "数据.txt"
        with patch("rgb_inspector.filedialog.askopenfilename", return_value=""):
            app.import_fit_button.invoke()
        with patch("rgb_inspector.filedialog.asksaveasfilename", return_value=""):
            app.export_fit_button.invoke()
        assert app._fitting_rows() == initial
        assert app.exported_rows == ()
        path.write_text("R G B 厚度\n10 20 30 4\n256 1 2 3", encoding="utf-8")
        with patch("rgb_inspector.filedialog.askopenfilename", return_value=str(path)), patch("rgb_inspector.messagebox.showerror") as error:
            app.import_fit_button.invoke()
            error.assert_called_once()
        assert app._fitting_rows() == initial  # No partial import.
        path.write_text("R G B 厚度\n10 20 30 4", encoding="utf-8")
        with patch("rgb_inspector.filedialog.askopenfilename", return_value=str(path)):
            app.import_fit_button.invoke()
        assert app._fitting_rows() == (*initial, ("10", "20", "30", "4"))
        with patch("rgb_inspector.filedialog.asksaveasfilename", return_value=str(path)), patch("rgb_inspector.write_fitting_txt", side_effect=OSError("test")), patch("rgb_inspector.messagebox.showerror"):
            app.export_fit_button.invoke()
        assert app.exported_rows == ()
        with patch("rgb_inspector.filedialog.asksaveasfilename", return_value=str(path)) as save:
            app.export_fit_button.invoke()
            assert save.call_args.kwargs["confirmoverwrite"]
        assert tuple(read_fitting_txt(path)) == app._fitting_rows()
        assert app.exported_rows == app._fitting_rows()
        with patch("rgb_inspector.messagebox.askyesno", return_value=True):
            app.update_fitting_row(row, ("1", "2", "3", "5"))
        assert app._fitting_rows() != app.exported_rows
        with patch("rgb_inspector.messagebox.askyesno", return_value=False) as warning:
            app._close()
            warning.assert_called_once()
        with patch("rgb_inspector.filedialog.asksaveasfilename", return_value=str(path)):
            app.export_fit_button.invoke()
        assert app._fitting_rows() == app.exported_rows
    print("PASS: highlighted tabs, minimum window layout, TXT import/export, cancellation, atomic import, export errors and saved-state tracking")
finally:
    app.destroy()
