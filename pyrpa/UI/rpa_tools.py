import sys
import os
import runpy
import io
import time
import zipfile
from importlib import reload
import streamlit as st
from PIL import Image

if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding("utf-8")

path = os.path.dirname(__file__)

# Ensure the repo root is importable regardless of working directory/mount
# layout (e.g. Streamlit Cloud doesn't put it on sys.path the way running
# locally from the repo root does), so `import pyrpa` resolves to the local
# package rather than failing or shadowing an unrelated PyPI package.
_repo_root = os.path.abspath(os.path.join(path, '..', '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

st.set_page_config(page_title="SLR Tools",
                   page_icon=Image.open(os.path.join(path, 'slr_logo.png')),
                   layout="wide")

# Suppress set_page_config in child tool modules — it can only be called once
import streamlit as _st
_st.set_page_config = lambda *args, **kwargs: None

# ── Passphrase gate ─────────────────────────────────────────────────────────
# Internal-tool access control. Set APP_PASSWORD in Streamlit secrets (or the
# APP_PASSWORD env var) to override the default; falls back to "SLR123".
try:
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except Exception:
    APP_PASSWORD = os.environ.get("APP_PASSWORD", "SLR123")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.image(Image.open(os.path.join(path, 'slr_logo.png')), width=220)
    st.title("SLR Tools")
    passphrase = st.text_input("Enter passphrase to continue", type="password")
    if passphrase:
        if passphrase == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect passphrase.")
    st.stop()

logo = Image.open(os.path.join(path, 'slr_logo.png'))
st.sidebar.image(logo, caption='', width=200)
# Celest kept as a smaller secondary mark so the app reads as SLR-first.
celest_logo = Image.open(os.path.join(path, 'Celest.png'))
st.sidebar.image(celest_logo, width=90)


@st.cache_data(show_spinner=False)
def _build_repo_zip():
    """Zip up the currently-running codebase so users can keep a local
    copy that won't change if the hosted version is later updated/broken.

    The zip walks the filesystem (not git), so it deliberately excludes
    virtual environments: those are OS-/machine-specific and huge, and the
    downloaded copy is meant to be rebuilt locally via `pip install -r
    requirements.txt`. Skipping them keeps the download small and portable
    while still shipping requirements.txt so every dependency reinstalls
    cleanly on the user's machine."""
    exclude_dirs = {'.git', '__pycache__', '.streamlit', '.venv', 'venv', 'env', '.claude'}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(_repo_root):
            # Drop excluded names, plus any directory that is itself a virtual
            # environment (pyvenv.cfg is the definitive marker) regardless of
            # what it's named.
            dirs[:] = [d for d in dirs
                       if d not in exclude_dirs
                       and not os.path.isfile(os.path.join(root, d, 'pyvenv.cfg'))]
            for f in files:
                if f.endswith('.pyc'):
                    continue
                full = os.path.join(root, f)
                arc = os.path.relpath(full, _repo_root).replace(os.sep, '/')
                if f.endswith(('.command', '.sh')):
                    _write_shell_launcher(zf, full, arc)
                else:
                    zf.write(full, arc)
    return buf.getvalue()


def _write_shell_launcher(zf, full, arc):
    """Add a shell launcher to the zip so macOS will actually run it.

    Two things a plain ``zf.write`` gets wrong when the app is served from
    Windows, where neither is visible locally:

    * No execute bit. Finder refuses to open a non-executable ``.command`` on
      double-click, so force 0755 rather than inheriting the host's mode.
    * CRLF endings (a Windows checkout with ``core.autocrlf``). bash then fails
      on the shebang line with ``$'\r': command not found``.
    """
    with open(full, 'rb') as fh:
        data = fh.read().replace(b'\r\n', b'\n')
    info = zipfile.ZipInfo(arc, date_time=time.localtime(os.path.getmtime(full))[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100755 << 16
    zf.writestr(info, data)


st.sidebar.download_button(
    "⬇️ Download this version",
    data=_build_repo_zip(),
    file_name="SLR-Tools.zip",
    mime="application/zip",
    use_container_width=True,
    help="Download the codebase exactly as it's running right now, so you have a local copy to fall back on.",
)

with st.sidebar.expander("📖 How to use"):
    st.markdown(
        r"""
**In this hosted app**

Pick a section below, then choose a tool. Upload your CSV or Excel file when
prompted. Files are held in memory for your session only, and nothing is saved
to the server.

---

**Run it on your own machine**

A local copy keeps working if this hosted app is down, updated, or you need to
work offline. Click **⬇️ Download this version** above and unzip it somewhere
convenient.

First install [Python 3.13](https://www.python.org/downloads/).
**Python 3.12 or newer is required**, and the launchers pick a valid one even
if an older Python is already on PATH.

*Windows*

1. Install Python, ticking *Add Python to PATH* during setup.
2. Double-click **Run SLR Tools.bat** in the unzipped folder.
3. If SmartScreen warns about the `.bat`, choose *More info* then *Run anyway*.

*macOS*

1. Install Python using the macOS 64-bit universal2 installer.
2. **Right-click** (or Control-click) **Run SLR Tools.command** in the unzipped
   folder, choose *Open*, then *Open* again in the warning box. macOS blocks
   downloaded scripts on a plain double-click, but only the first time: after
   that, double-clicking it works normally.
3. Still refusing? Open Terminal, type `bash ` (with the space), drag
   **Run SLR Tools.command** onto the Terminal window, and press Enter.

Either way, your browser opens at http://localhost:8501. Leave the console
window open while you work, and press `Ctrl+C` in it to stop the app.

The first run sets itself up: it builds a private Python environment and
installs everything in `requirements.txt`. That takes a few minutes and needs
an internet connection, once. Every run after that starts in seconds.

---

**Running it by hand**

```
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m streamlit run pyrpa/UI/rpa_tools.py
```

On Windows the equivalent paths are `.venv\Scripts\pip` and
`.venv\Scripts\python`.

Run `pip install -r requirements.txt` against a Python older than 3.12 and it
fails with *No matching distribution found for numpy*. Build the environment
with 3.12+ instead.

---

**Notes**

- Setup only happens once per download. After that, the launcher goes straight
  to starting the app.
- The local copy uses the same passphrase screen. Set an `APP_PASSWORD`
  environment variable before launching to change it.
- The download excludes virtual environments, so it stays small and rebuilds
  cleanly on any machine.
        """
    )

st.sidebar.divider()

SECTIONS = ["Home", "Plotting Tools", "Sample Tools", "Block Model Tools", "Geostats Tools", "QA/QC", "Data Validation"]
section = st.sidebar.radio("", SECTIONS)

if 'active_tool' not in st.session_state:
    st.session_state.active_tool = None
if 'active_section' not in st.session_state:
    st.session_state.active_section = section

# Reset tool when the user switches sections
if section != st.session_state.active_section:
    st.session_state.active_tool = None
    st.session_state.active_section = section


def tool_button(label, module):
    if st.button(label, use_container_width=True):
        st.session_state.active_tool = module
        st.rerun()


def run_active_tool():
    col_back, _ = st.columns([1, 5])
    with col_back:
        if st.button("← Back"):
            st.session_state.active_tool = None
            st.rerun()
    st.divider()
    module_path = os.path.join(path, st.session_state.active_tool)
    runpy.run_path(module_path, run_name='__main__')


# ── Home ─────────────────────────────────────────────────────────────────────
if section == "Home":
    st.session_state.active_tool = None
    st.image(Image.open(os.path.join(path, 'slr_logo.png')), width=260)
    st.title("SLR Tools")
    st.caption("Celest · Resource Estimation Tools")
    st.markdown("A collection of miraculous tools for resource geologists.")
    st.markdown("**Version 1.0.3**")
    st.markdown("Select a tool from the sidebar to get started.")
    image = Image.open(os.path.join(path, 'gibraltar_0857.jpg'))
    st.image(image, caption='', use_container_width=True)

# ── Plotting Tools ────────────────────────────────────────────────────────────
elif section == "Plotting Tools":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## Plotting Tools")
        tool_button("Box Plot",        "box_plot_ui.py")
        tool_button("Scatter Plot",    "scatter_plot_ui.py")
        tool_button("Width Plot",      "width_plot_ui.py")

# ── Sample Tools ──────────────────────────────────────────────────────────────
elif section == "Sample Tools":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## Sample Tools")
        tool_button("SIF Certificate → CSV",  "SIF_to_CSV_ui.py")
        tool_button("Statistics",             "sample_stats_ui.py")
        tool_button("Capping Analysis",       "capping_ui_v2.py")
        tool_button("Uncapped vs Capped Plot","capped_vs_uncapped_plot_ui.py")
        tool_button("Contact Analysis",       "contact_plot_ui.py")
        tool_button("Calculate DDH Spacing",  "ddh_spacing_ui.py")
        tool_button("Thin DDH Spacing",       "thin_ddh_spacing_ui.py")

# ── Block Model Tools ─────────────────────────────────────────────────────────
elif section == "Block Model Tools":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## Block Model Tools")
        if st.checkbox("Block Model Validation"):
            tool_button("Convert Rotations (between conventions)", "convert_rotation_ui.py")

# ── Geostats Tools ────────────────────────────────────────────────────────────
elif section == "Geostats Tools":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## Geostats Tools")
        tool_button("Gammabar Plot", "gammabar_ui.py")

# ── QA/QC ─────────────────────────────────────────────────────────────────────
elif section == "QA/QC":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## QA/QC Tools")
        tool_button("Standards",    "CRMs_ui.py")
        tool_button("Blanks",       "Blanks_ui.py")
        tool_button("Duplicates",   "Duplicates_ui_nuggets.py")
        tool_button("Check Assays", "Check_assay_ui.py")
        tool_button("Z-Score",      "Z_Score_ui.py")

# ── Data Validation ───────────────────────────────────────────────────────────
elif section == "Data Validation":
    if st.session_state.active_tool:
        run_active_tool()
    else:
        st.markdown("## Data Validation")
        tool_button("Data Verification Tool", "data_verification_ui.py")
        tool_button("Drill Hole Comparison",  "Get_Nearest_ui.py")
