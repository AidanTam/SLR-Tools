# SLR Celest Resource Estimation Tools

A Streamlit web application providing a suite of resource geology tools for sample analysis, QA/QC, geostatistics, and data validation.

**Version 1.0.2**

### 🌐 Live App

**[slr-tools-hlkbjthxcsk8brkp3deody.streamlit.app](https://slr-tools-hlkbjthxcsk8brkp3deody.streamlit.app)**

Hosted on Streamlit Community Cloud — no install required. Access is protected by a passphrase. The app auto-updates whenever changes are pushed to the `main` branch.

### 📖 User Manual

A full user manual covering the geologist workflow, every file input type, and all 18 tools is available as a Word document — [**docs/Celest-Tools-User-Manual.docx**](docs/Celest-Tools-User-Manual.docx) — or as Markdown at [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

---

## Getting Started

### Installation

Requires **Python 3.12 or newer**. The pinned numpy and pandas versions publish no
wheels for 3.11 or below, so `pip install` fails outright on an older interpreter.
Check with `py --list` on Windows, or `ls /usr/local/bin/python3*` on macOS.

Windows:

```bash
git clone https://github.com/AidanTam/SLR-Tools.git
cd SLR-Tools
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

macOS / Linux:

```bash
git clone https://github.com/AidanTam/SLR-Tools.git
cd SLR-Tools
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Running the App

Double-click the launcher for your platform in the repo root. Either one creates a
`.venv` and installs `requirements.txt` on first run, then starts the app on every
run after that.

| Platform | Launcher | First-run gatekeeping |
|----------|----------|-----------------------|
| Windows | **`Run SLR Tools.bat`** | SmartScreen: *More info* then *Run anyway* |
| macOS | **`Run SLR Tools.command`** | Right-click the file, *Open*, then *Open* again |

macOS blocks scripts from a downloaded zip on a plain double-click. The right-click
*Open* route clears that once, after which double-clicking works. If macOS refuses
outright, run `bash "Run SLR Tools.command"` from Terminal, which is never blocked.

By hand:

```bash
python -m streamlit run pyrpa/UI/rpa_tools.py
```

Opens at `http://localhost:8501` by default. Stop the server with `Ctrl+C` in the terminal it's running in.

### Troubleshooting

- **Code changes not showing up**: editing files in `pyrpa/` (not the entry-point `rpa_tools.py`) won't hot-reload — Python caches imported modules. Fully stop the server (`Ctrl+C`, or kill any process still bound to port 8501) and relaunch.
- **Port already in use**: another Streamlit instance may still be running. Find and stop it, or launch on a different port with `python -m streamlit run pyrpa/UI/rpa_tools.py --server.port 8502`.
- **Missing packages** (e.g. `pygwalker`, `transforms3d`): re-run `pip install -r requirements.txt`.

### Hosted Version

This app can also be deployed to [Streamlit Community Cloud](https://streamlit.io/cloud) for browser access with no local install — see [Deployment](#deployment) below.

---

## Tools

Select a section from the sidebar to browse available tools.

### Plotting Tools
| Tool | Description |
|------|-------------|
| Box Plot | Interactive box plots by domain and subdomain |
| Scatter Plot | Bivariate scatter plots with optional colour and size fields |
| Width Plot | Variable-width bar charts |

### Sample Tools
| Tool | Description |
|------|-------------|
| Statistics | Weighted/unweighted sample statistics by domain |
| Capping Analysis | Interactive capping level selection with spatial and histogram views |
| Uncapped vs Capped Plot | Side-by-side comparison of grade distributions before and after capping |
| Contact Analysis | Contact plots to assess hard/soft/transitional boundaries between domains |
| Calculate DDH Spacing | Nearest-neighbour drillhole spacing by domain |
| Thin DDH Spacing | Thin-sample drillhole spacing analysis |

### Block Model Tools
| Tool | Description |
|------|-------------|
| Convert Rotations | Convert rotation angles between block model conventions |

### Geostats Tools
| Tool | Description |
|------|-------------|
| Gammabar Plot | Gammabar variogram plot for change-of-support analysis |

### QA/QC
| Tool | Description |
|------|-------------|
| Standards | CRM/standard recovery charts and statistics |
| Blanks | Blank sample performance analysis |
| Duplicates | Duplicate pair analysis (Thompson-Howarth, scatter, HARD) |
| Check Assays | Check assay comparison plots |
| Z-Score | Z-score analysis for outlier detection |

### Data Validation
| Tool | Description |
|------|-------------|
| Data Verification Tool | Merge lab certificate files (`.csv`/`.xlsx`/`.xlsm`), compare against assay database |
| Drill Hole Comparison | Nearest-neighbour drillhole comparison |

---

## File Input

All tools that accept data files support two input methods:

- **Drag and drop / browse** — upload a `.csv` or `.dm` (Datamine) file directly via the sidebar uploader
- **Select from folder** — pick a file already in the working directory from the dropdown

---

## Dependencies

| Package | Version |
|---------|---------|
| streamlit | 1.23.1 |
| pandas | 1.4.2 |
| numpy | 1.22.4 |
| plotly | 5.8.2 |
| matplotlib | 3.5.2 |
| Pillow | 9.5.0 |
| transforms3d | 0.4.2 |
| pygwalker | 0.5.0.1 |
| pyrpa | 0.0.5 |

---

## Deployment

This app is deployed at **[slr-tools-hlkbjthxcsk8brkp3deody.streamlit.app](https://slr-tools-hlkbjthxcsk8brkp3deody.streamlit.app)** on [Streamlit Community Cloud](https://share.streamlit.io) (free):

1. Push the repo to GitHub (already done — `AidanTam/SLR-Tools`).
2. Sign in at [share.streamlit.io](https://share.streamlit.io) with your GitHub account and authorize Streamlit's GitHub app.
3. Click **Create app**, select this repo and the `main` branch, and set the main file path to `pyrpa/UI/rpa_tools.py`.
4. Under **Advanced settings**, set the Python version to match local development if needed, and add the access passphrase under **Secrets** in TOML form: `APP_PASSWORD = "your-passphrase"`. This is required: without it the gate in `pyrpa/UI/rpa_tools.py` falls back to the default hardcoded in the source.
5. Click **Deploy**. The app builds from `requirements.txt` in the repo root and is live at a `*.streamlit.app` URL within a few minutes.
6. Future pushes to `main` redeploy automatically.

> **Warning:** Community Cloud identifies an app by its GitHub coordinates (owner, repository, branch,
> entrypoint path). Renaming the repository while the app is deployed breaks it with
> `Failed to download the sources`, GitHub's redirect does not help, and App settings has no repository
> field to repoint. The documented order for any such change is: **delete the app, make the change in
> GitHub, then redeploy.** Deleting the app also clears its saved secrets, so have `APP_PASSWORD` ready
> to paste back in.

> **Note:** Vercel does not support Streamlit — it only runs serverless functions and static sites, not the persistent WebSocket server Streamlit requires. Streamlit Community Cloud, Render, Railway, or a VM are the viable hosts.

---

## Project Structure

```
SLR-Tools/
├── requirements.txt              # Python dependencies (used by Streamlit Cloud)
├── pyrpa/
│   ├── UI/
│   │   ├── rpa_tools.py          # App entry point
│   │   ├── common.py             # Shared widgets and file utilities
│   │   ├── capping_ui_v2.py
│   │   ├── sample_stats_ui.py
│   │   └── ...                   # One *_ui.py per tool
│   ├── capping.py
│   ├── sample.py
│   ├── contact_plot.py
│   └── ...                       # Backend computation modules
```
---

## Recent Improvements

| Module | Improvement |
|--------|-------------|
| All QA/QC tools | **Automatic column mapping**: on upload, each tool now guesses which column fills each field (Lab, Element, Value, Date, Unit, etc.) by name, tolerant of case/spacing/synonyms — "Analyte" → Element, "Assay_Result" → Value, "SampleDate" → Date, and so on. Re-guesses whenever the uploaded file's columns change, so a manual pick you've made survives reruns of the same file but a genuinely new file gets fresh guesses instead of stale ones. Falls back to the old first-column behaviour when nothing matches. |
| All QA/QC tools | **Wide-format detection**: if a file has one column-block per element (e.g. `Au_EV`, `Au_SD`, `Au_or_ppm`, `Ag_EV`, `Ag_SD`, ...) instead of a single Element/Value column pair, a sidebar prompt offers to reshape it into the long format the tools expect, with a choice of which element groups to include. Column mapping then fills in automatically against the reshaped data. |
| All QA/QC tools | New **Aspect ratio** control in the 📐 Style options sets the chart width-to-height ratio — presets (16:9, 3:2, 4:3, 1:1, 2:1, 3:1) plus a `Custom...` option taking a free-text `W:H` value. Leave it on `Default` to keep each tool's original proportions. |
| Blanks, Duplicates | PowerPoint export no longer stretches charts into a fixed 8×4.5 in box — the slide image now follows the chart's own aspect ratio |
| Blanks | Y-axis limits can now be adjusted for blank values in the plot (Custom Y-limits in the Style options) |
| Standards (CRMs) | Automatic detection of header columns (Date, Grade, CRM, Element, Expected Value, Project, Lab, Unit) |
| Standards (CRMs) | Renamed fields: `Categorical column` → `Project`, `Optional Grouping Field 1` → `Lab` |
| Standards (CRMs) | `Unit` is now a trackable, auto-detected column (read per-chart) with a free-text fallback, instead of a fixed predefined list |
| Standards (CRMs) | Removed the upper/lower limit parameters from the combined CRM summary table |
| Capping | `Metal Loss` in the Capping Summary table now matches the `Percent Metal Loss` in the Decile Analysis table (computed from unrounded weighted averages) |
| Capping | Fixed the Capping Summary table rendering as all-NaN under newer pandas (chained-assignment issue) |
| Data Verification | Certificate and assay uploaders now accept Excel (`.xlsx`/`.xlsm`) directly as well as `.csv` — no more Save-As-CSV step. Files that fail to merge now report why instead of failing silently. |

## Planned / Outstanding Updates

| Module | Update | Notes |
|--------|--------|-------|
| Standards (CRMs) | Restore the "no grouping field" chart branch | When no grouping field is selected, no chart/summary currently renders ([CRMs_ui.py](pyrpa/UI/CRMs_ui.py) ~line 1193 is a stub). Partly masked now that `Lab` auto-detects and triggers the working grouped path. |
| Dependencies | Reconcile `requirements.txt` with the installed environment | Pinned versions (pandas 1.4.2, etc.) differ from the environment in use (pandas 3.x); watch for chained-assignment patterns elsewhere. |
