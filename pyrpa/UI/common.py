import glob
import json
import math
import re
import pyrpa
import pandas as pd
import streamlit as st
import os
from PIL import Image

field_type=None

# Width-to-height ratios offered by aspect_ratio_input(). "Default" keeps each
# tool's original figure size; "Custom..." reveals a free-text field.
ASPECT_PRESETS = {
    "Default": None,
    "16:9 (widescreen)": 16 / 9,
    "3:2": 3 / 2,
    "4:3": 4 / 3,
    "1:1 (square)": 1.0,
    "2:1": 2.0,
    "3:1 (wide)": 3.0,
    "Custom...": "custom",
}

def parse_aspect_ratio(text):
    """Parse a 'W:H' string (or a bare number, treated as W:1) into a width/height
    float. Returns None if the text isn't a usable ratio, so callers can fall back."""
    text = str(text).strip()
    if not text:
        return None

    sep = ":" if ":" in text else ("/" if "/" in text else None)
    try:
        if sep is not None:
            w_str, h_str = text.split(sep, 1)
            w, h = float(w_str), float(h_str)
        else:
            w, h = float(text), 1.0
    except ValueError:
        return None

    if not (math.isfinite(w) and math.isfinite(h)) or w <= 0 or h <= 0:
        return None

    return w / h

def aspect_ratio_input(default_size, key, container=None, label="Aspect ratio"):
    """Aspect-ratio picker returning a matplotlib figsize (width, height) in inches.

    default_size is the tool's original figsize, returned unchanged while the picker
    sits on "Default" so existing charts keep their current proportions. Any other
    choice holds the default width and derives the height from the ratio.

    Pass container=st.sidebar to place the widgets in the sidebar directly; leave it
    as None inside a `with st.sidebar.expander(...)` block so they land in the expander.
    """
    widget = container if container is not None else st

    choice = widget.selectbox(label, list(ASPECT_PRESETS.keys()), index=0, key=key)
    spec = ASPECT_PRESETS[choice]

    if spec is None:
        return tuple(default_size)

    if spec == "custom":
        raw = widget.text_input("Custom ratio (W:H)",
                                value=st.session_state.get(key + "_custom", "16:9"),
                                key=key + "_custom")
        ratio = parse_aspect_ratio(raw)
        if ratio is None:
            widget.warning("Enter a ratio like 16:9 - using the default size for now.")
            return tuple(default_size)
    else:
        ratio = spec

    width = float(default_size[0])
    return (width, width / ratio)

# ── Column auto-mapping ──────────────────────────────────────────────────────
# Name-based guessing of which uploaded column corresponds to which field the
# QA/QC tools need (Lab, Element, Value, Date, ...), plus detection/reshaping of
# "wide" per-element exports (Au_EV, Au_or_ppm, Ag_EV, Ag_or_ppm, ...) into the
# long/tidy format (one Element column, one Value column) the tools expect.

_TOKEN_RE = re.compile(r'[^0-9a-zA-Z]+')

def _tokens(name):
    """Lowercase alnum tokens from a name, splitting on underscores/spaces/
    punctuation and camelCase boundaries (so 'SampleDate' and 'sample_date'
    both tokenize to {'sample', 'date'})."""
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '_', str(name))
    return frozenset(t for t in _TOKEN_RE.split(s.lower()) if t)

def _normalize(name):
    return re.sub(r'[^0-9a-z]', '', str(name).lower())

def _match_names_to_keys(names, synonyms_by_key, keys):
    """Core matcher shared by auto_map_columns() and the wide-reshape suffix-role
    detector: best-effort 1:1 assignment of `names` to `keys`, scored by how well
    each name matches each key's synonym list. A name and a key are each used at
    most once (highest-scoring matches win first). Returns {key: name_or_None}."""
    names = list(names)
    name_tokens = {n: _tokens(n) for n in names}
    name_norm = {n: _normalize(n) for n in names}

    candidates = []  # (score, key, name)
    for key in keys:
        for syn in synonyms_by_key.get(key, []):
            syn_tokens = _tokens(syn)
            if not syn_tokens:
                continue
            syn_norm = _normalize(syn)
            for n in names:
                if name_norm[n] == syn_norm:
                    candidates.append((100, key, n))
                elif len(syn_tokens) >= 2 and syn_tokens <= name_tokens[n]:
                    candidates.append((90, key, n))
                elif len(syn_tokens) == 1 and syn_tokens <= name_tokens[n]:
                    candidates.append((60, key, n))

    candidates.sort(key=lambda t: -t[0])
    result = {k: None for k in keys}
    used_names, used_keys = set(), set()
    for score, key, n in candidates:
        if key in used_keys or n in used_names:
            continue
        result[key] = n
        used_keys.add(key)
        used_names.add(n)
    return result

# Synonyms are matched as whole tokens (underscore/space/case-insensitive), not
# substrings, so e.g. "sd" never matches inside "grade" or "date".
FIELD_SYNONYMS = {
    "lab": ["lab", "laboratory", "lab name", "assay lab", "test lab"],
    "primary_lab": ["primary lab", "lab 1", "original lab"],
    "secondary_lab": ["secondary lab", "lab 2", "check lab", "duplicate lab", "umpire lab"],
    "element": ["element", "analyte", "elem"],
    "value": ["value", "result", "grade", "assay value", "assay result", "reading"],
    "original_value": ["original value", "original assay", "original", "primary value", "value"],
    "duplicate_value": ["duplicate value", "duplicate assay", "duplicate", "dup value", "check value"],
    "date": ["date", "sample date", "assay date", "batch date"],
    "unit": ["unit", "units", "uom"],
    "lod": ["lod", "dl", "detection limit", "lower detection limit"],
    "type": ["type", "blank type", "control type", "sample type", "duplicate type"],
    "crm": ["crm", "standard", "control", "standard name", "control type", "control name"],
    "expected": ["expected value", "expected", "ev", "certified value", "certified"],
    "sd": ["sd", "stdev", "std dev", "standard deviation"],
    "project": ["project", "project name", "client", "source"],
    "company": ["company", "client", "project"],
}

def auto_map_columns(columns, field_keys, extra_synonyms=None):
    """Best-effort guess of which column in `columns` corresponds to each of
    `field_keys` (see FIELD_SYNONYMS for the supported keys), by name only --
    case/punctuation/spacing-insensitive, small synonym list per field. Returns
    {field_key: column_name_or_None}. Never assigns the same column to two
    fields. Pass extra_synonyms={field_key: [...]} to extend a field's list for
    one call without touching the shared FIELD_SYNONYMS table.

    Name matching alone can't help with "wide" exports where each element gets
    its own column block (Au_EV, Ag_EV, ...) instead of a single Element/Value
    pair -- see detect_wide_groups() / reshape_wide_to_long() for that case.
    """
    synonyms = dict(FIELD_SYNONYMS)
    if extra_synonyms:
        for k, v in extra_synonyms.items():
            synonyms[k] = synonyms.get(k, []) + list(v)
    return _match_names_to_keys(list(columns), synonyms, list(field_keys))

def detect_wide_groups(columns, min_suffixes_per_group=2, min_groups=2, min_shared_suffixes=2):
    """Detect repeated <PREFIX>_<SUFFIX> column blocks that suggest a wide,
    one-column-block-per-element export (e.g. Au_EV, Au_SD, Au_or_ppm, Ag_EV,
    Ag_SD, Ag_or_ppm) rather than the long/tidy layout the QA/QC tools expect
    (a single Element column plus a single Value column).

    Returns {prefix: {suffix_lower: column_name}} for prefixes that look like
    genuine parallel groups, or {} if nothing qualifies (including plain tidy
    data, which is the common case and should be a no-op).
    """
    groups = {}
    for col in columns:
        if '_' not in col:
            continue
        prefix, suffix = col.split('_', 1)
        if not prefix or not suffix:
            continue
        groups.setdefault(prefix, {})[suffix.lower()] = col

    groups = {p: s for p, s in groups.items() if len(s) >= min_suffixes_per_group}
    if len(groups) < min_groups:
        return {}

    # Require real suffix overlap across groups (e.g. both Au_* and Ag_* have an
    # "EV" and an "SD" column) -- otherwise these are just coincidentally
    # underscore-named columns, not parallel per-element blocks.
    suffix_sets = list(groups.values())
    common = set(suffix_sets[0])
    for s in suffix_sets[1:]:
        common &= set(s)
    if len(common) < min_shared_suffixes:
        return {}

    return groups

# Suffix -> role synonyms used only inside a single detected wide-format group
# (a handful of suffixes at a time), so shorter/looser synonyms are safe here in
# a way they wouldn't be matching against a whole file's column names.
_SUFFIX_ROLE_SYNONYMS = {
    "value": ["or ppm", "or", "original", "value", "result", "grade", "assay", "reading",
              "ppm", "pct", "percent", "ppb", "g t", "oz t"],
    "duplicate_value": ["dp ppm", "dp", "duplicate", "dup", "check"],
    "unit": ["unit", "units", "uom"],
    "lod": ["dl", "lod", "detection limit"],
    "expected": ["ev", "expected", "expected value", "certified"],
    "sd": ["sd", "stdev", "std dev", "standard deviation"],
}

_LONG_COLUMN_NAMES = {
    "value": "Value",
    "duplicate_value": "Duplicate_Value",
    "unit": "Unit",
    "lod": "LOD",
    "expected": "Expected",
    "sd": "SD",
}

def reshape_wide_to_long(df, groups, element_col_name="Element"):
    """Melt a wide per-element layout (as detected by detect_wide_groups) into
    one row per sample-element: a single `element_col_name` column holding the
    group prefix (e.g. "Au", "Ag") plus Value/Unit/LOD/Expected/SD/
    Duplicate_Value columns, each pulled from whichever suffix in that group
    best matches the role. Columns not claimed by any group are treated as
    shared and repeated across every element's rows.
    """
    grouped_cols = {col for suffix_map in groups.values() for col in suffix_map.values()}
    shared_cols = [c for c in df.columns if c not in grouped_cols]
    roles = list(_LONG_COLUMN_NAMES.keys())

    pieces = []
    for prefix, suffix_map in groups.items():
        role_to_suffix = _match_names_to_keys(list(suffix_map.keys()), _SUFFIX_ROLE_SYNONYMS, roles)
        piece = df[shared_cols].copy()
        piece[element_col_name] = prefix
        for role, suffix in role_to_suffix.items():
            if suffix is None:
                continue
            piece[_LONG_COLUMN_NAMES[role]] = df[suffix_map[suffix]]
        pieces.append(piece)

    return pd.concat(pieces, ignore_index=True) if pieces else df.copy()

def offer_wide_reshape(df, key):
    """If df looks like a wide, per-element export (see detect_wide_groups),
    show a sidebar prompt offering to reshape it into the long format the
    QA/QC tools expect, with a choice of which element groups to include.
    Returns the reshaped dataframe once the user confirms, else the original
    dataframe unchanged -- a no-op when no groups are detected, which is the
    common case for already-tidy data.

    `key` scopes the session_state used to remember the choice so it survives
    reruns without re-melting on every script execution, and so switching
    tools doesn't leak one tool's reshape choice into another's.

    Callers should follow this with sync_column_mapping() -- reshaping
    changes df.columns, and column-mapping selectboxes need that to notice
    and re-guess (see sync_column_mapping's docstring for why).
    """
    groups = detect_wide_groups(df.columns)
    if not groups:
        return df

    sel_key = key + "_wide_selected"
    skip_key = key + "_wide_skip"

    stored = st.session_state.get(sel_key)
    if stored:
        chosen = {p: groups[p] for p in stored if p in groups}
        if chosen:
            return reshape_wide_to_long(df, chosen)
        del st.session_state[sel_key]  # stale choice from a different upload

    if st.session_state.get(skip_key):
        return df

    with st.sidebar.expander("🔀 Wide-format data detected", expanded=True):
        prefixes = sorted(groups.keys())
        st.write(
            f"Found {len(prefixes)} column group(s) that look like one block per "
            f"element ({', '.join(prefixes)}) instead of a single Element/Value "
            f"column pair. Reshape to long format so column mapping below can "
            f"fill in automatically?"
        )
        selected = st.multiselect("Element groups to include", prefixes, default=prefixes,
                                  key=key + "_wide_groups_pick")
        col_a, col_b = st.columns(2)
        if col_a.button("Reshape", key=key + "_wide_reshape_btn", disabled=not selected):
            st.session_state[sel_key] = selected
            st.rerun()
        if col_b.button("Skip, map manually", key=key + "_wide_skip_btn"):
            st.session_state[skip_key] = True
            st.rerun()

    return df

# Saved-state keys that describe the app shell or this one load rather than the
# user's work, so restoring them would switch tools or skew the load tracking.
_NON_RESTORABLE_KEYS = {"authenticated", "active_tool", "active_section", "cfg_loaded"}
# Streamlit raises if a button's key is assigned through session_state, and
# these get saved along with everything else whenever the button has rendered.
_NON_RESTORABLE_SUFFIXES = ("_wide_reshape_btn", "_wide_skip_btn",
                            "_restored_file_id", "_mapping_restored")

def load_saved_state(uploaded, key, transform=None):
    """Restore a saved-progress JSON into session_state. Returns True on the
    run the file was applied, so the caller can show a confirmation.

    Applies each uploaded file once: the uploader keeps returning the file on
    every rerun, and re-applying it would undo whatever the user changed since.
    Uploading again (even the same file) gets a new file_id and applies again.

    `key` scopes the tracking the same way as sync_column_mapping(), which this
    tells to keep the saved column mapping rather than re-guess it. `transform`
    optionally converts the parsed values, e.g. ISO strings back into dates.
    """
    id_key = key + "_restored_file_id"
    if uploaded is None or st.session_state.get(id_key) == uploaded.file_id:
        return False

    saved = json.load(uploaded)
    if transform is not None:
        saved = transform(saved)
    st.session_state.update({
        k: v for k, v in saved.items()
        if k not in _NON_RESTORABLE_KEYS and not k.endswith(_NON_RESTORABLE_SUFFIXES)
    })
    st.session_state[id_key] = uploaded.file_id
    st.session_state[key + "_mapping_restored"] = True
    st.session_state["cfg_loaded"] = True
    return True

def sync_column_mapping(df, key, field_map):
    """Keep a tool's column-mapping selectboxes correct whenever the
    uploaded data's columns change -- a fresh upload with different columns,
    or a wide-format reshape via offer_wide_reshape(). Call this once, right
    before creating the column-mapping selectboxes.

    Detects a change via a fingerprint of df.columns stashed in session_state
    (scoped by `key`); on change, re-guesses every mapped field with
    auto_map_columns() and *writes* the result into session_state. A no-op
    (besides updating the fingerprint) when columns haven't changed, so a
    user's manual override of a mapping survives reruns of the same file.

    After load_saved_state(), the first call keeps every saved mapping whose
    column exists in df and only guesses the rest, so resuming doesn't lose the
    user's picks. The restored fingerprint can't be trusted for this: JSON turns
    the tuple into a list, which never compares equal to the current columns.

    This write is necessary, not just a nice-to-have: Streamlit selectboxes
    don't re-validate an existing session_state value against a new options
    list on their own, so a key already set to a now-invalid column (e.g.
    "Au_Element" after a reshape drops that column) keeps displaying that
    stale value indefinitely if merely removed rather than overwritten --
    the same class of staleness documented for multiselect defaults
    elsewhere in this file.

    `field_map` maps each column-mapping session_state key to the
    FIELD_SYNONYMS key it represents, e.g. {"lab_col": "lab", "elem_col":
    "element", "val_col": "value", ...}.
    """
    fp_key = key + "_cols_fp"
    fingerprint = tuple(df.columns)
    restored = st.session_state.pop(key + "_mapping_restored", False)
    if not restored and st.session_state.get(fp_key) == fingerprint:
        return
    st.session_state[fp_key] = fingerprint

    valid = set(df.columns) | {"None"}
    guess = auto_map_columns(df.columns, list(set(field_map.values())))
    for map_key, field_key in field_map.items():
        if restored and st.session_state.get(map_key) in valid:
            continue
        if guess.get(field_key):
            st.session_state[map_key] = guess[field_key]
        else:
            st.session_state.pop(map_key, None)

def show_header():
    path = os.path.dirname(__file__)
    logo = Image.open(os.path.join(path, 'slr_logo.png'))
    st.image(logo, caption='', width=180)

def extend_list(list1, list2):

    list1.extend(list2)

    return list1;

def get_idx(dlist, value):

    return dlist.index(value);

def get_dict_files(dict_type):

    dict_files = []

    for dict_f in glob.glob("*.dict"):
        df = pd.read_csv(dict_f, index_col=0)
        if df.loc['Dict Type', 'Parameter']==dict_type:
            dict_files.append(dict_f)

    return dict_files;


def get_file_list(extensions, include_none=True):
    '''

    :param extensions:
    :param include_none:
    :return:
    '''
    if include_none:
        file_list = ['--None--']
    else:
        file_list = []

    for ext in extensions:
        file_list = extend_list(file_list, glob.glob("*" + ext))

    return file_list;

def load_file(infile):
    '''

    :param infile:
    :return:
    '''
    if ".dm" in infile:
        df = pyrpa.io.read_datamine(infile)
    elif ".csv" in infile:
        df = pd.read_csv(infile)
    else:
        raise ValueError("Invalid file type")
    return df;

def read_data_file(uploaded):
    """Read an uploaded data file (or path) as a DataFrame, supporting CSV and Excel.
    Picks the reader from the file extension so the QA/QC uploaders accept .xlsx/.xls
    as well as .csv."""
    name = getattr(uploaded, 'name', str(uploaded))
    if name.lower().endswith(('.xlsx', '.xls')):
        return pd.read_excel(uploaded)
    return pd.read_csv(uploaded)

def upload_or_select(extensions, display_text="Data File (.csv or .dm)", key="file", sidebar=True, initial_value=None):
    """Show a drag-and-drop file uploader then a directory-scan selectbox as fallback.
    Upload takes priority. Returns (filename_str, DataFrame) or (None, None)."""
    widget = st.sidebar if sidebar else st

    uploaded = widget.file_uploader(
        display_text,
        type=[e.lstrip('.') for e in extensions],
        key=key + "_upload",
    )
    if uploaded is not None:
        name = uploaded.name
        if '.dm' in name:
            import tempfile
            tmp_path = os.path.join(tempfile.gettempdir(), name)
            with open(tmp_path, 'wb') as f:
                f.write(uploaded.getvalue())
            df = pyrpa.io.read_datamine(tmp_path)
        else:
            df = pd.read_csv(uploaded)
        return name, df

    infiles = get_file_list(extensions)
    if initial_value is not None and initial_value in infiles:
        idx = infiles.index(initial_value)
    else:
        idx = 0
    infile = widget.selectbox("...or select from folder", infiles, index=idx, key=key + "_select")
    if infile != "--None--":
        return infile, load_file(infile)
    return None, None

def get_header(df):
    '''

    :param df:
    :return:
    '''

    return extend_list(['--None--'],df.columns)


def define_sample(df, gradefields, holeid, xyzfields, domainf, weightf):

    '''

    :param df:
    :param gradefields:
    :param holeid:
    :param xyzfields:
    :param domainf:
    :param weightf:
    :return:
    '''

    assert gradefields != "--None--", "Select a grade field"
    assert holeid != "--None--", "Select grade field"
    assert len(xyzfields) == 3, "Select 3 coordinate fields"

    if domainf == "--None--":
        domainf = None
    if weightf == "--None--":
        weightf = None

    smp_obj = pyrpa.smp.Sample(data=df, gradefields=gradefields,
                               holeid=holeid, xyzfields=xyzfields,
                               domainf=domainf, weightf=weightf)
    return smp_obj;

def invalid_number_handling(df, gradefields, option):
    df_out = df.copy()
    for gf in gradefields:
        if option == 'Ignore':
            try:
                df_out = df_out[df_out[gf].str.isnumeric].copy()
            except:
                pass
        else:
            try:
                df_out[gf] = df_out[gf].fillna(0.)
                df_out.loc[df_out[gf].str.isalnum, [gf]] = 0.
            except:
                pass
    return df_out;

def guess_field(header, type=None):

    comb_dict = {"xyzfields": [['X', 'Y', 'Z'],
                             ['midx', 'midy', 'midz'],
                             ['EAST', 'NORTH', 'ELEV'],
                             ['mid_x', 'mid_y', 'mid_z'],
                             ['XPT', 'YPT', 'ZPT'],
                             ['Easting', 'Norting', 'Elevation'],
                             ['LOCATIONX', 'LOCATIONY', 'LOCATIONZ']],
                 "holeid": ['BHID', 'HOLEID', 'holeid'],
                 "weightf": ['length', 'LENGTH', 'dcweight'],
                 "domainf": ['ZONE', 'DOMAIN', 'ROCK', 'rock', 'bound']
                 }

    combinations  = comb_dict[type]
    found = 0
    for comb in combinations:
        if found == 0:
            if isinstance(comb, list):
                if all(x in header for x in comb):
                    fields = comb
                    found = 1
            else:
                if comb in header:
                    fields = comb
                    found = 1
    if found == 0:
        fields = None

    return fields;

def selectbox(selection, options, display_text, key, guessheader=False, field_type=None):

    if guessheader and field_type is not None:
        selection = guess_field(header=options, type=field_type)

    if selection != '--None--':
        idx = get_idx(options, selection)
    else:
        idx = 0

    return st.sidebar.selectbox(display_text, options=options, index=idx, key=key);

def multiselect(options, display_text, default_list, default_dictval, key, guessheader=False, field_type='xyzfields'):
    
    if default_list != [""] and default_list != []:
        if isinstance(default_list, float):
            default_list = []
        else:
            default_list = strip_dflist(default_dictval)

    else:
        if guessheader:
            default_list = guess_field(options, field_type)
        else:
            default_list = []

    default_list = st.sidebar.multiselect(display_text, options=options, default=default_list, key=key)

    for i, c in enumerate(default_list):
        if i == 0:
            default_dictval = str(c)
        else:
            default_dictval += ("," + str(c))

    return default_list, default_dictval;


def radio(selection, options, display_text, key, sidebar=False):

    if selection != '--None--':
        idx = get_idx(options, selection)
    else:
        idx = 0
    if sidebar:
        return st.sidebar.radio(display_text, options=options, index=idx, key=key);
    else:
        return st.radio(display_text, options=options, index=idx, key=key);

def strip_dflist(dflist):
    '''
    Function to convert a list stored as a text string back to a list
    :param dflist: str
        list stored as text string
    :return: list
        list string converted back to a list
    '''
    stripped_list = dflist.strip("][").split(',')
    if len(stripped_list) == 1:
        stripped_list =  stripped_list[0].split(',')
    for i in range(len(stripped_list)):
        stripped_list[i] = stripped_list[i].strip("'")
        stripped_list[i] = stripped_list[i].strip('"')
    return stripped_list;

def update_keys(_temp_dict, dict_type='Capping'):

    ignore_values = ["Dict Type", "Description", "Filename"]

    for key in _temp_dict.index.values:
        if key not in ignore_values:
            _temp_dict.loc[key, 'Parameter'] = st.get_option(key=key)
            _temp_dict.to_csv('temp_' + dict_type + "_dict")
            _temp_dict = pd.read_csv('temp_' + dict_type + "_dict", index_col=0)
            st.set_option(key=key, value=_temp_dict.loc[key, 'Parameter'])

def make_whitespace(number_of_lines=1):

    for i in range(number_of_lines):
        st.markdown("")












# ── Chart customisation shared by the QA/QC and comparison charts ────────────
# Marker shapes offered to users, by display name. "Hollow" shapes draw only
# the outline, in the chosen colour.
MARKER_SHAPES = {
    "Dot": "o", "Hollow dot": "o",
    "Star": "*", "Hollow star": "*",
    "Square": "s", "Hollow square": "s",
    "Triangle": "^", "Hollow triangle": "^",
    "Diamond": "D", "Hollow diamond": "D",
    "Cross": "X", "Plus": "P",
}


def _prune_choice(key, options):
    """Drop saved multiselect picks that aren't options any more (a different
    file, a restored JSON, a new bin size): Streamlit raises on them."""
    picked = st.session_state.get(key)
    if isinstance(picked, list):
        st.session_state[key] = [p for p in picked if p in options]


def marker_select(label, key, default="Dot", container=None):
    """A marker-shape selectbox. Returns the display name; pass it to
    marker_kwargs() or line_marker_kwargs()."""
    box = container or st
    names = list(MARKER_SHAPES)
    if st.session_state.get(key) not in names:
        st.session_state.pop(key, None)
    if key in st.session_state:
        # Restored from a saved JSON: passing a default as well makes Streamlit warn.
        return box.selectbox(label, names, key=key)
    return box.selectbox(label, names, index=names.index(default), key=key)


def marker_kwargs(shape, color, size=None, edge_color=None):
    """Keyword arguments for ax.scatter() drawing `shape` in `color`."""
    hollow = shape.startswith("Hollow")
    kw = {
        "marker": MARKER_SHAPES.get(shape, "o"),
        "facecolors": "none" if hollow else color,
        "edgecolors": color if hollow else (edge_color or color),
    }
    if hollow:
        kw["linewidths"] = 1.3
    if size is not None:
        kw["s"] = size
    return kw


def line_marker_kwargs(shape, color, size=None):
    """Keyword arguments for ax.plot() / Line2D markers (legends, lines)."""
    hollow = shape.startswith("Hollow")
    kw = {
        "marker": MARKER_SHAPES.get(shape, "o"),
        "markerfacecolor": "none" if hollow else color,
        "markeredgecolor": color,
    }
    if size is not None:
        kw["markersize"] = size
    return kw


def date_display_options(key, dates, calendar_axis=False, container=None):
    """Sidebar controls for which dates a chart shows.

    `dates` is the date column the charts draw from. With `calendar_axis`
    the chart normally spaces points by calendar date, so it also offers
    "only dates with data", which places dated samples side by side instead
    of leaving gaps for dates with no samples. Returns a dict for
    filter_dates()."""
    box = container or st.sidebar
    days = sorted(pd.to_datetime(dates, errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique())
    with box.expander("🗓️ Dates shown on charts"):
        only_data = True
        if calendar_axis:
            only_data = st.checkbox(
                "Only show dates with data (no gaps)", key=key + "_only_data",
                help="Place samples side by side in date order, instead of spacing "
                     "them on a calendar with gaps for dates that have no samples.")
        min_count = st.number_input(
            "Hide dates with fewer than this many samples", min_value=1, value=1, step=1,
            key=key + "_min_count",
            help="1 shows every date. Applied per chart, so a date can be sparse in "
                 "one chart and kept in another.")
        _prune_choice(key + "_removed", days)
        removed = st.multiselect("Remove dates", days, key=key + "_removed",
                                 help="Leave these dates out of every chart.")
        st.caption("Sample counts and failure rates on the charts cover the dates shown.")
    return {"only_data": only_data, "min_count": int(min_count), "removed": set(removed)}


def filter_dates(df, date_col, opts):
    """Apply date_display_options() to one chart's rows."""
    if df.empty or not opts:
        return df
    day = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    keep = ~day.isin(opts["removed"])
    if opts["min_count"] > 1:
        keep &= day.map(day.value_counts()).fillna(0) >= opts["min_count"]
    return df[keep]


def bucket_display_options(key, buckets, noun="buckets", container=None):
    """Controls for hiding buckets (bars, bins, cutoff ranges) on a chart.
    Returns a dict for keep_buckets()."""
    box = container or st
    buckets = [str(b) for b in buckets]
    with box.expander(f"🪣 {noun.capitalize()} shown"):
        hide_empty = st.checkbox(f"Hide empty {noun}", key=key + "_hide_empty",
                                 help=f"Leave out {noun} with no data in either dataset.")
        _prune_choice(key + "_removed", buckets)
        removed = st.multiselect(f"Remove {noun}", buckets, key=key + "_removed")
    return {"hide_empty": hide_empty, "removed": set(removed)}


def keep_buckets(buckets, totals, opts):
    """The buckets to draw, in order. `totals` gives each bucket's amount of
    data (summed over datasets), used for "hide empty"."""
    kept = []
    for b, total in zip(buckets, totals):
        if str(b) in opts["removed"]:
            continue
        if opts["hide_empty"] and not (pd.notna(total) and total > 0):
            continue
        kept.append(b)
    return kept
