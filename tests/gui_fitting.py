"""Check fitting table actions and confirmation branches in a real Tk window."""
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import ttk
from PIL import Image
from rgb_inspector import RGBInspector


app = RGBInspector()
try:
    app.update()
    assert app.add_fit_button.instate(["disabled"])
    app.add_to_fitting()
    assert not app.fit_table.get_children()
    app.image = Image.new("RGB", (3, 1))
    app.image.putdata([(1, 2, 3), (2, 4, 6), (2, 5, 8)])
    app.selection = (0, 0, 1, 1)
    app._show_result(pixel=True)
    app.add_fit_button.invoke()
    app.update()
    first = app.fit_table.get_children()[0]
    assert app.fit_table.item(first, "values") == ("1", "2", "3", "")
    assert app.notebook.select() == str(app.fitting_tab)

    app.selection = (0, 0, 3, 1)
    app._show_result(pixel=False)
    app.add_to_fitting()
    second = app.fit_table.get_children()[1]
    values = app.fit_table.item(second, "values")
    assert float(values[0]) == 5 / 3  # Full precision, not the four-decimal display.
    assert values[3] == ""
    app.clear_selection()
    assert app.add_fit_button.instate(["disabled"])
    assert len(app.fit_table.get_children()) == 2

    # Use the actual edit dialog and Save button to enter the first thickness.
    app.fit_table.selection_set(first)
    app.edit_fitting_row()
    app.update()
    dialog = next(child for child in app.winfo_children() if isinstance(child, tk.Toplevel))
    body = dialog.winfo_children()[0]
    entries = [child for child in body.winfo_children() if isinstance(child, ttk.Entry)]
    entries[3].insert(0, "12.5")
    buttons = next(child for child in body.winfo_children() if isinstance(child, ttk.Frame))
    save = next(child for child in buttons.winfo_children() if child.cget("text") == "保存")
    with patch("rgb_inspector.messagebox.askyesno") as confirm:
        save.invoke()
        confirm.assert_not_called()
    assert app.fit_table.item(first, "values") == ("1", "2", "3", "12.5")

    with patch("rgb_inspector.messagebox.askyesno", return_value=False) as confirm:
        assert not app.update_fitting_row(first, ["50", "2", "3", "13"])
        assert confirm.call_args.kwargs["default"] == "no"
    assert app.fit_table.item(first, "values") == ("1", "2", "3", "12.5")
    with patch("rgb_inspector.messagebox.askyesno", return_value=True):
        assert app.update_fitting_row(first, ["50", "2", "3", "13"])
    assert app.fit_table.item(first, "values") == ("50", "2", "3", "13")
    with patch("rgb_inspector.messagebox.showerror") as error:
        for bad in (["256", "2", "3", "13"], ["nan", "2", "3", "13"],
                    ["50", "2", "3", "-1"], ["50", "2", "3", "inf"],
                    ["", "2", "3", "13"], ["50", "2", "3", "abc"]):
            assert not app.update_fitting_row(first, bad)
        assert error.call_count == 6
    with patch("rgb_inspector.messagebox.askyesno", return_value=False):
        assert not app.update_fitting_row(first, ["50", "2", "3", ""])
        app._close()
        assert app.winfo_exists()

    app.fit_table.selection_set(first, second)
    with patch("rgb_inspector.messagebox.askyesno", return_value=False):
        app.delete_fitting_rows()
    assert len(app.fit_table.get_children()) == 2
    with patch("rgb_inspector.messagebox.askyesno", return_value=True) as confirm:
        app.delete_fitting_rows()
        assert "2 行" in confirm.call_args.args[1]
    assert not app.fit_table.get_children()
    print("PASS: add pixel/mean, precision, edit dialog, initial thickness, validation, edit/delete/exit cancellation, confirmed edits and batch deletion")
finally:
    app.destroy()
