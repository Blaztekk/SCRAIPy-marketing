"""Legacy entry point — delegates to streamlit_app.py.

Streamlit Cloud's 'Main file path' setting still references this file.
Update Settings → Main file path → 'streamlit_app.py' to remove this shim.
"""

import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).parent / "streamlit_app.py"),
    run_name="__main__",
)