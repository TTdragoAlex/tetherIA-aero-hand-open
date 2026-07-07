from pathlib import Path
import aero_open_sdk

package_dir = Path(aero_open_sdk.__file__).resolve().parent
gui_path = package_dir / 'gui.py'
text = gui_path.read_text()

old_zoom = '''        if sys.platform.startswith("win"):
            self.state("zoomed")
        else:
            self.attributes("-zoomed", True)
'''
new_zoom = '''        if sys.platform.startswith("win"):
            self.state("zoomed")
        elif sys.platform == "darwin":
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        else:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
'''

if new_zoom not in text and old_zoom in text:
    text = text.replace(old_zoom, new_zoom)

if 'def on_load_current_get_pos' not in text or 'Raw actuator sliders' not in text:
    raise SystemExit(
        f'{gui_path} does not contain the raw actuator GUI patch. '
        'Please restore from the Robot Hand workspace version or rerun the Codex patch.'
    )

gui_path.write_text(text)
print(f'GUI patches verified: {gui_path}')
