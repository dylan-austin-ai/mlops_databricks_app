"""MLOps Command Center — design system implementation for Streamlit.

Two surfaces:
  apply_theme()     — injects all CSS (tokens + Streamlit overrides). Call after set_page_config().
  HTML helpers      — pill(), sev_badge(), pii_badge(), tag(), path_chip(),
                      page_header(), metric_html(), kv_row(), sidebar_brand(),
                      conn_badge(), wizard_steps() — use with st.markdown(unsafe_allow_html=True).
"""

from __future__ import annotations

import streamlit as st

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

/* ============================  TOKENS  ============================ */
:root {
  --bg:            #0b0f1a;
  --bg-deep:       #070a12;
  --surface:       #111827;
  --surface-2:     #161f33;
  --surface-3:     #1b2640;
  --sidebar:       #0d1117;

  --border:        #1a2740;
  --border-bright: #243456;
  --border-strong: #2f4368;

  --text:          #e2e8f0;
  --text-soft:     #a9b6cc;
  --text-muted:    #64748b;
  --text-dim:      #46546e;

  --accent:        #00d4ff;
  --accent-bright: #5ce6ff;
  --accent-deep:   #0891b2;
  --accent-15:     rgba(0,212,255,0.15);
  --accent-10:     rgba(0,212,255,0.10);
  --accent-25:     rgba(0,212,255,0.25);
  --accent-text:   #7de8ff;

  --success:       #10b981;
  --success-15:    rgba(16,185,129,0.15);
  --success-text:  #5eead4;
  --warning:       #f59e0b;
  --warning-15:    rgba(245,158,11,0.15);
  --warning-text:  #fcd34d;
  --error:         #ef4444;
  --error-15:      rgba(239,68,68,0.15);
  --error-text:    #fca5a5;
  --info:          #818cf8;
  --info-15:       rgba(129,140,248,0.15);
  --info-text:     #c7d2fe;

  --glow-accent:    0 0 0 1px var(--accent-25), 0 0 18px rgba(0,212,255,0.35);
  --glow-accent-sm: 0 0 12px rgba(0,212,255,0.30);
  --glow-success:   0 0 14px rgba(16,185,129,0.45);
  --glow-warning:   0 0 14px rgba(245,158,11,0.45);
  --glow-error:     0 0 14px rgba(239,68,68,0.45);

  --shadow-sm: 0 1px 2px rgba(0,0,0,0.40);
  --shadow-md: 0 4px 16px rgba(0,0,0,0.45);

  --font-ui:   'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, 'SF Mono', monospace;

  --fs-display: 30px;
  --fs-h2: 22px;
  --fs-h3: 17px;
  --fs-body: 14px;
  --fs-sm: 13px;
  --fs-xs: 12px;
  --fs-micro: 11px;

  --r-xs: 3px;  --r-sm: 5px;  --r-md: 8px;  --r-lg: 12px;  --r-pill: 999px;
  --ease: cubic-bezier(0.22,1,0.36,1);
  --dur: 180ms;  --dur-fast: 120ms;

  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px;
  --sp-6:24px; --sp-8:32px;
}

/* ============================  BASE  ============================ */
*, *::before, *::after { box-sizing: border-box; }
* { font-family: var(--font-ui); }

::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius:2px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

/* ============================  CANVAS  ============================ */
.stApp {
  background-color: var(--bg) !important;
  background-image:
    radial-gradient(1200px 600px at 70% -10%, rgba(0,212,255,0.06), transparent 60%),
    radial-gradient(900px 500px at -5% 110%, rgba(129,140,248,0.05), transparent 55%),
    linear-gradient(rgba(26,39,64,0.30) 1px, transparent 1px),
    linear-gradient(90deg, rgba(26,39,64,0.30) 1px, transparent 1px) !important;
  background-size: auto, auto, 48px 48px, 48px 48px !important;
  background-attachment: fixed !important;
  color: var(--text) !important;
  -webkit-font-smoothing: antialiased !important;
}

.main > div { padding-top: 1.5rem; }

/* ============================  SIDEBAR  ============================ */
[data-testid="stSidebar"] {
  background-color: var(--sidebar) !important;
  border-right: 1px solid var(--border) !important;
  position: relative;
}
/* right-edge accent light */
[data-testid="stSidebar"]::after {
  content: "";
  position: absolute; top: 0; right: 0; bottom: 0; width: 1px;
  background: linear-gradient(180deg, transparent, var(--accent-25), transparent);
  opacity: .5; pointer-events: none;
}
[data-testid="stSidebar"] > div { background: transparent !important; }

/* sidebar headings (brand mark title rendered via HTML helper) */
[data-testid="stSidebar"] h1 {
  font-size: 13px !important;
  font-weight: 700 !important;
  color: #f4f8ff !important;
  letter-spacing: 0.02em !important;
  margin: 0 !important;
  -webkit-text-fill-color: #f4f8ff !important;
  background: none !important;
}

/* rail section label */
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
  font-size: 11px !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.12em !important;
  color: var(--text-dim) !important;
}

/* Hide Streamlit's auto-generated page navigation — we render our own below */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] {
  display: none !important;
}

/* nav page links */
[data-testid="stPageLink"] {
  border-radius: var(--r-sm);
  transition: background var(--dur) var(--ease);
}
[data-testid="stPageLink"] a {
  display: flex !important;
  align-items: center !important;
  gap: var(--sp-3) !important;
  height: 38px !important;
  padding: 0 var(--sp-3) !important;
  border-radius: var(--r-sm) !important;
  color: var(--text-muted) !important;
  font-size: var(--fs-sm) !important;
  font-weight: 500 !important;
  text-decoration: none !important;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease) !important;
}
[data-testid="stPageLink"] a:hover {
  background: var(--surface-2) !important;
  color: var(--text-soft) !important;
}
/* active page link — Streamlit adds aria-current on current page */
[data-testid="stPageLink"] a[aria-current="page"] {
  background: var(--accent-10) !important;
  color: var(--accent-text) !important;
  position: relative;
}
[data-testid="stPageLink"] a[aria-current="page"]::before {
  content: "";
  position: absolute; left: -4px; top: 8px; bottom: 8px; width: 3px;
  border-radius: 2px;
  background: var(--accent);
  box-shadow: var(--glow-accent-sm);
}

/* ============================  HEADINGS  ============================ */
h1 {
  font-size: var(--fs-display) !important;
  font-weight: 700 !important;
  letter-spacing: -0.01em !important;
  line-height: 1.15 !important;
  color: #f4f8ff !important;
  -webkit-text-fill-color: #f4f8ff !important;
  background: none !important;
  margin: 0 !important;
}
h2 {
  font-size: var(--fs-h2) !important;
  font-weight: 600 !important;
  color: #eef3fb !important;
  margin: 0 !important;
}
h3 {
  font-size: var(--fs-h3) !important;
  font-weight: 600 !important;
  color: var(--text) !important;
  margin: 0 !important;
}
hr {
  border: none !important;
  border-top: 1px solid var(--border) !important;
  margin: 0.5rem 0 !important;
}

/* ============================  BUTTONS  ============================ */
.stButton > button {
  font-family: var(--font-ui) !important;
  font-size: var(--fs-sm) !important;
  font-weight: 600 !important;
  letter-spacing: 0.01em !important;
  height: 36px !important;
  border-radius: var(--r-sm) !important;
  transition: background var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
              transform var(--dur-fast) var(--ease) !important;
}
.stButton > button:active { transform: translateY(1px) !important; }

.stButton > button[kind="primary"] {
  background: linear-gradient(180deg, var(--accent-bright), var(--accent)) !important;
  border: none !important;
  color: #04141b !important;
  box-shadow: var(--glow-accent-sm) !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: var(--glow-accent) !important;
}

.stButton > button:not([kind="primary"]) {
  background: var(--surface-2) !important;
  border: 1px solid var(--border-bright) !important;
  color: var(--text) !important;
}
.stButton > button:not([kind="primary"]):hover {
  background: var(--surface-3) !important;
  border-color: var(--border-strong) !important;
}

/* link buttons */
.stLinkButton a {
  font-family: var(--font-ui) !important;
  font-size: var(--fs-sm) !important;
  font-weight: 500 !important;
  height: 36px !important;
  border-radius: var(--r-sm) !important;
  background: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text-soft) !important;
  text-decoration: none !important;
  display: inline-flex !important;
  align-items: center !important;
  padding: 0 var(--sp-4) !important;
  transition: border-color var(--dur) var(--ease), color var(--dur) var(--ease),
              box-shadow var(--dur) var(--ease) !important;
}
.stLinkButton a:hover {
  border-color: var(--accent-25) !important;
  color: var(--accent-text) !important;
  box-shadow: var(--glow-accent-sm) !important;
}

/* ============================  CARDS / CONTAINERS  ============================ */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-md) !important;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color: var(--border-bright) !important;
  box-shadow: var(--shadow-md) !important;
}

/* ============================  METRICS  ============================ */
[data-testid="stMetric"] {
  background: var(--surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-md) !important;
  padding: var(--sp-4) var(--sp-5) !important;
  transition: border-color var(--dur) var(--ease) !important;
}
[data-testid="stMetric"]:hover { border-color: var(--border-bright) !important; }

[data-testid="stMetricLabel"] > div {
  font-size: var(--fs-micro) !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.12em !important;
  color: var(--text-muted) !important;
}
[data-testid="stMetricValue"] > div {
  font-family: var(--font-mono) !important;
  font-size: 28px !important;
  font-weight: 600 !important;
  line-height: 1 !important;
  color: #f4f8ff !important;
  letter-spacing: -0.01em !important;
}
[data-testid="stMetricDelta"] {
  font-family: var(--font-mono) !important;
  font-size: var(--fs-xs) !important;
  font-weight: 600 !important;
}
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Up"]   { fill: var(--success-text) !important; }
[data-testid="stMetricDelta"] svg[data-testid="stMetricDeltaIcon-Down"] { fill: var(--error-text) !important; }

/* ============================  TABS  ============================ */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid var(--border) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
  font-size: var(--fs-xs) !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  color: var(--text-muted) !important;
  padding: var(--sp-3) var(--sp-4) !important;
  border-bottom: 2px solid transparent !important;
  border-radius: 0 !important;
  transition: color var(--dur) var(--ease) !important;
  position: relative !important;
}
[data-testid="stTabs"] [role="tab"]:hover { color: var(--text-soft) !important; }
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--accent-text) !important;
  border-bottom-color: var(--accent) !important;
}
/* glow on active tab underline */
[data-testid="stTabs"] [role="tab"][aria-selected="true"]::after {
  content: "";
  position: absolute; left: var(--sp-2); right: var(--sp-2); bottom: -1px; height: 2px;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
  border-radius: 2px;
}

/* ============================  COLUMNS  =========================== */
/* Pin each column's content to the top so widgets in adjacent columns
   align even when one column has more content (PROJECT_STATUS gap #2). */
[data-testid="stColumn"], [data-testid="column"] { align-self: flex-start !important; }

/* ============================  INPUTS  ============================ */
.stTextInput > label, .stTextArea > label, .stNumberInput > label,
.stSelectbox > label, .stMultiSelect > label, .stSlider > label,
.stRadio > label { display: block; }
.stTextInput > label > div, .stTextArea > label > div, .stNumberInput > label > div,
.stSelectbox > label > div, .stMultiSelect > label > div {
  font-size: var(--fs-micro) !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.12em !important;
  color: var(--text-muted) !important;
}
.stTextInput input,
.stTextArea textarea,
.stNumberInput input {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border-bright) !important;
  border-radius: var(--r-sm) !important;
  color: var(--text) !important;
  font-family: var(--font-ui) !important;
  font-size: var(--fs-sm) !important;
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease) !important;
}
.stTextInput input:hover,
.stTextArea textarea:hover { border-color: var(--border-strong) !important; }
.stTextInput input:focus,
.stTextArea textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-15), var(--glow-accent-sm) !important;
  outline: none !important;
}
.stSelectbox > div > div,
.stMultiSelect > div > div {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border-bright) !important;
  border-radius: var(--r-sm) !important;
  color: var(--text) !important;
}
/* multiselect chips */
[data-baseweb="tag"] {
  background: var(--accent-10) !important;
  border: 1px solid var(--accent-25) !important;
  color: var(--accent-text) !important;
  border-radius: var(--r-sm) !important;
}

/* ============================  CHECKBOXES / RADIO  ============================ */
.stCheckbox label span,
.stRadio label span {
  font-size: var(--fs-sm) !important;
  font-weight: 400 !important;
  text-transform: none !important;
  letter-spacing: normal !important;
  color: var(--text-soft) !important;
}
.stCheckbox label span:first-child { color: var(--text-soft) !important; }

/* ============================  PROGRESS BAR  ============================ */
[data-testid="stProgressBar"] > div {
  background: var(--border) !important;
  border-radius: 2px !important;
  height: 4px !important;
}
[data-testid="stProgressBar"] > div > div {
  background: linear-gradient(90deg, var(--accent-deep), var(--accent)) !important;
  box-shadow: var(--glow-accent-sm) !important;
  border-radius: 2px !important;
}

/* ============================  ALERTS  ============================ */
[data-testid="stAlert"] {
  border-radius: var(--r-sm) !important;
  font-size: var(--fs-sm) !important;
  border-width: 1px !important;
  border-style: solid !important;
}
div[class*="stSuccess"] {
  background: var(--success-15) !important;
  border-color: rgba(16,185,129,0.35) !important;
  color: var(--success-text) !important;
}
div[class*="stError"] {
  background: var(--error-15) !important;
  border-color: rgba(239,68,68,0.35) !important;
  color: var(--error-text) !important;
}
div[class*="stWarning"] {
  background: var(--warning-15) !important;
  border-color: rgba(245,158,11,0.35) !important;
  color: var(--warning-text) !important;
}
div[class*="stInfo"] {
  background: var(--info-15) !important;
  border-color: rgba(129,140,248,0.35) !important;
  color: var(--info-text) !important;
}

/* ============================  EXPANDERS  ============================ */
[data-testid="stExpander"] {
  background: var(--bg-deep) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-md) !important;
}
[data-testid="stExpander"] summary {
  font-size: var(--fs-sm) !important;
  font-weight: 500 !important;
  color: var(--text-muted) !important;
}
[data-testid="stExpander"] summary:hover { color: var(--text-soft) !important; }

/* ============================  DATAFRAME  ============================ */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--r-md) !important;
  overflow: hidden !important;
}

/* ============================  FORMS (st.form)  ============================ */
[data-testid="stForm"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--r-md) !important;
  padding: var(--sp-6) !important;
  background: var(--bg-deep) !important;
}

/* ============================  CAPTIONS  ============================ */
[data-testid="stCaptionContainer"] p {
  font-size: var(--fs-xs) !important;
  color: var(--text-muted) !important;
}

/* ============================  CODE  ============================ */
code {
  font-family: var(--font-mono) !important;
  font-size: 0.82em !important;
  background: var(--bg-deep) !important;
  color: var(--accent-text) !important;
  border: 1px solid var(--border-bright) !important;
  border-radius: var(--r-xs) !important;
  padding: 1px 5px !important;
}
pre code { border: none !important; padding: 0 !important; }
strong { color: var(--text); font-weight: 600; }

/* ============================  SELECT POPOVER  ============================ */
[data-baseweb="popover"] [data-baseweb="menu"] {
  background: var(--surface-2) !important;
  border: 1px solid var(--border-strong) !important;
  border-radius: var(--r-sm) !important;
}
[data-baseweb="option"]:hover { background: var(--surface-3) !important; }
[data-baseweb="option"][aria-selected="true"] { background: var(--accent-10) !important; }

/* ============================  SLIDER  ============================ */
[data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-testid="stTickBarMax"] {
  font-size: var(--fs-xs) !important;
  color: var(--text-muted) !important;
}
"""

# ── Shared component HTML ─────────────────────────────────────────────────────

_BADGE_BASE = (
    "display:inline-flex;align-items:center;gap:6px;"
    "height:22px;padding:0 10px;border-radius:999px;"
    "font-size:11px;font-weight:600;letter-spacing:0.06em;"
    "text-transform:uppercase;border:1px solid transparent;"
    "white-space:nowrap;line-height:1;"
)

_PILL_STYLES: dict[str, str] = {
    "production": "color:#5eead4;background:rgba(16,185,129,0.15);"
    "border-color:rgba(16,185,129,0.40);box-shadow:0 0 14px rgba(16,185,129,0.45);",
    "staging": "color:#fcd34d;background:rgba(245,158,11,0.15);border-color:rgba(245,158,11,0.40);",
    "development": "color:#7de8ff;background:rgba(0,212,255,0.15);border-color:rgba(0,212,255,0.25);",
    "created": "color:#7de8ff;background:rgba(0,212,255,0.10);border-color:rgba(0,212,255,0.20);",
    "archived": "color:#64748b;background:rgba(100,116,139,0.12);border-color:rgba(100,116,139,0.3);",
    "deleted": "color:#fca5a5;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.40);",
    "pending": "color:#fcd34d;background:rgba(245,158,11,0.15);border-color:rgba(245,158,11,0.40);",
    "approved": "color:#5eead4;background:rgba(16,185,129,0.15);border-color:rgba(16,185,129,0.40);",
    "rejected": "color:#fca5a5;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.40);",
    "needs_changes": "color:#c7d2fe;background:rgba(129,140,248,0.15);border-color:rgba(129,140,248,0.40);",
}

_SEV_STYLES: dict[str, str] = {
    "none": "color:#94a3b8;background:rgba(71,85,105,0.18);",
    "low": "color:#5eead4;background:rgba(16,185,129,0.15);",
    "medium": "color:#fcd34d;background:rgba(245,158,11,0.15);",
    "high": "color:#fda4af;background:rgba(251,113,133,0.16);",
    "critical": "color:#fca5a5;background:rgba(239,68,68,0.15);box-shadow:0 0 14px rgba(239,68,68,0.45);",
}

_PII_STYLES: dict[str, str] = {
    "none": "color:#94a3b8;background:rgba(71,85,105,0.18);",
    "low": "color:#5eead4;background:rgba(16,185,129,0.15);",
    "medium": "color:#fcd34d;background:rgba(245,158,11,0.15);",
    "high": "color:#fca5a5;background:rgba(239,68,68,0.15);",
}

_TAG_STYLES: dict[str, str] = {
    "input_data": "color:#7de8ff;border-color:rgba(0,212,255,0.25);background:rgba(0,212,255,0.10);",
    "output_data": "color:#5eead4;border-color:rgba(16,185,129,0.35);background:rgba(16,185,129,0.15);",
    "feature_table": "color:#c7d2fe;border-color:rgba(129,140,248,0.35);background:rgba(129,140,248,0.15);",
    "staging_table": "color:#fcd34d;border-color:rgba(245,158,11,0.35);background:rgba(245,158,11,0.15);",
}

_BRAND_SVG = """
<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect x="6.7" y="0.8" width="4.6" height="4.6" rx="1"
        transform="rotate(45 9 3.1)" fill="#00d4ff"/>
  <rect x="1.2" y="12" width="3.4" height="3.4" rx="1" fill="#0891b2"/>
  <rect x="13.4" y="12" width="3.4" height="3.4" rx="1" fill="#0891b2"/>
  <path d="M9 5.4V9M9 9L3 13M9 9l6 4"
        stroke="#5ce6ff" stroke-width="1.1" stroke-linecap="round"/>
  <circle cx="9" cy="9" r="1.5" fill="#5ce6ff"/>
</svg>
"""

# ── Public API ────────────────────────────────────────────────────────────────


def apply_theme() -> None:
    """Inject all CSS. Call immediately after st.set_page_config()."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def pill(status: str, dot: bool = True) -> str:
    """Return lifecycle/approval status badge HTML."""
    style = _PILL_STYLES.get(status.lower(), _PILL_STYLES["development"])
    label = status.replace("_", " ").title()
    d = (
        '<span style="width:6px;height:6px;border-radius:50%;'
        'background:currentColor;box-shadow:0 0 8px currentColor;flex:none;display:inline-block"></span>'
        if dot
        else ""
    )
    return f'<span style="{_BADGE_BASE}{style}">{d}{label}</span>'


def sev_badge(level: str) -> str:
    """Return severity badge HTML (none/low/medium/high/critical)."""
    style = _SEV_STYLES.get(level.lower(), _SEV_STYLES["none"])
    base = (
        "display:inline-flex;align-items:center;gap:6px;"
        "height:20px;padding:0 9px;border-radius:3px;"
        "font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;"
    )
    dot = (
        "content:'';display:inline-block;width:6px;height:6px;"
        "border-radius:50%;background:currentColor;margin-right:2px;"
    )
    return f'<span style="{base}{style}"><span style="{dot}"></span>{level.upper()}</span>'


def pii_badge(level: str) -> str:
    """Return PII level badge HTML (none/low/medium/high)."""
    style = _PII_STYLES.get(level.lower(), _PII_STYLES["none"])
    base = (
        "display:inline-flex;align-items:center;gap:5px;"
        "height:20px;padding:0 8px;border-radius:3px;"
        "font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;"
    )
    sq = "display:inline-block;width:7px;height:7px;border-radius:2px;background:currentColor;"
    return f'<span style="{base}{style}"><span style="{sq}"></span>PII:{level.upper()}</span>'


def tag(text: str, contract_type: str) -> str:
    """Return contract-type tag HTML."""
    style = _TAG_STYLES.get(contract_type.lower(), _TAG_STYLES["input_data"])
    base = (
        "display:inline-flex;align-items:center;height:20px;padding:0 9px;"
        "border-radius:3px;font-size:11px;font-weight:600;"
        "font-family:'JetBrains Mono',monospace;letter-spacing:.02em;border:1px solid;"
    )
    return f'<span style="{base}{style}">{text}</span>'


def path_chip(uc_path: str) -> str:
    """Return monospace UC path chip HTML (e.g. uc:mlops.project_dev)."""
    parts = uc_path.split(".", 1)
    body = (
        f'<span style="color:#64748b">uc:</span>{uc_path}'
        if len(parts) == 1
        else (f'<span style="color:#64748b">uc:</span>{uc_path}')
    )
    style = (
        "display:inline-flex;align-items:center;gap:4px;"
        "font-family:'JetBrains Mono',monospace;font-size:11px;"
        "color:#7de8ff;background:rgba(0,212,255,0.10);"
        "border:1px solid rgba(0,212,255,0.25);border-radius:3px;padding:3px 8px;"
    )
    return f'<span style="{style}">{body}</span>'


def page_header(eyebrow: str, title: str, subtitle: str = "") -> str:
    """Return page header HTML (eyebrow + h1 + subtitle)."""
    sub = (
        f'<span style="font-size:13px;color:#64748b;display:block;margin-top:4px">{subtitle}</span>' if subtitle else ""
    )
    return f"""
<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:8px">
  <span style="font-size:11px;font-weight:600;text-transform:uppercase;
               letter-spacing:0.12em;color:#7de8ff">{eyebrow}</span>
  <h1 style="font-size:30px;font-weight:700;letter-spacing:-0.01em;
             line-height:1.15;color:#f4f8ff;margin:0">{title}</h1>
  {sub}
</div>"""


def metric_html(
    label: str,
    value: str,
    foot: str = "",
    accent: bool = False,
) -> str:
    """Return metric card HTML matching design spec."""
    accent_style = ("border-left:2px solid #00d4ff;box-shadow:inset 0 0 30px rgba(0,212,255,0.05);") if accent else ""
    value_color = "#7de8ff" if accent else "#f4f8ff"
    foot_html = f'<span style="font-size:12px;color:#64748b">{foot}</span>' if foot else ""
    return f"""
<div style="background:#111827;border:1px solid #1a2740;border-radius:8px;
            padding:16px 20px;display:flex;flex-direction:column;gap:12px;{accent_style}">
  <span style="font-size:11px;font-weight:600;text-transform:uppercase;
               letter-spacing:0.12em;color:#64748b">{label}</span>
  <span style="font-family:'JetBrains Mono',monospace;font-size:28px;
               font-weight:600;line-height:1;color:{value_color};
               letter-spacing:-0.01em">{value}</span>
  {foot_html}
</div>"""


def kv_row(key: str, value: str, mono: bool = True, last: bool = False) -> str:
    """Return a key-value display row."""
    border = "" if last else "border-bottom:1px solid #1a2740;"
    val_font = "font-family:'JetBrains Mono',monospace;" if mono else ""
    return f"""
<div style="display:flex;align-items:baseline;justify-content:space-between;
            gap:16px;padding:10px 0;{border}">
  <span style="font-size:12px;color:#64748b">{key}</span>
  <span style="font-size:13px;color:#e2e8f0;{val_font}">{value}</span>
</div>"""


def sidebar_brand() -> str:
    """Return brand mark + wordmark HTML for sidebar top."""
    return f"""
<div style="display:flex;align-items:center;gap:12px;padding:8px 8px 20px;">
  <div style="width:34px;height:34px;flex:none;border-radius:5px;
              background:linear-gradient(150deg,#0e2030,#0a131f);
              border:1px solid rgba(0,212,255,0.25);
              display:grid;place-content:center;
              box-shadow:0 0 12px rgba(0,212,255,0.30);">
    {_BRAND_SVG}
  </div>
  <div style="display:flex;flex-direction:column;line-height:1.2;">
    <span style="font-size:13px;font-weight:700;color:#f4f8ff;letter-spacing:0.02em">MLOps</span>
    <span style="font-size:11px;font-weight:600;text-transform:uppercase;
                 letter-spacing:0.12em;color:#7de8ff">Command Center</span>
  </div>
</div>"""


def conn_badge(host: str, catalog: str = "mlops", connected: bool = True) -> str:
    """Return connection status badge HTML for sidebar foot."""
    dot_style = (
        "background:#10b981;box-shadow:0 0 14px rgba(16,185,129,0.45);animation:connpulse 2.4s ease infinite;"
        if connected
        else "background:#ef4444;"
    )
    status_text = "Connected" if connected else "Disconnected"
    host_short = host.replace("https://", "").split(".")[0][:20]
    return f"""
<style>@keyframes connpulse{{0%,100%{{box-shadow:0 0 6px rgba(16,185,129,.5)}}
50%{{box-shadow:0 0 16px rgba(16,185,129,.9)}}}}</style>
<div style="margin-top:auto;padding-top:16px;border-top:1px solid #1a2740;">
  <div style="display:flex;align-items:center;gap:12px;padding:12px;
              border-radius:5px;background:#111827;border:1px solid #1a2740;">
    <span style="width:8px;height:8px;border-radius:50%;flex:none;{dot_style}display:block"></span>
    <span style="display:flex;flex-direction:column;line-height:1.3;">
      <span style="font-size:12px;font-weight:600;color:#e2e8f0">{status_text}</span>
      <span style="font-size:11px;color:#64748b;font-family:'JetBrains Mono',monospace">
        {host_short} · uc:{catalog}
      </span>
    </span>
  </div>
</div>"""


def wizard_steps(current: int, completed: list[int]) -> str:
    """Return wizard step-rail HTML."""
    labels = [
        ("Basic Info", ""),
        ("Model Specs", ""),
        ("Data Specs", ""),
        ("Governance", ""),
        ("Deployment", ""),
        ("Monitoring", ""),
        ("Approval Gates", ""),
    ]
    items = []
    for i, (label, _) in enumerate(labels, 1):
        if i in completed:
            cls_row = "background:transparent;"
            num_s = "background:rgba(16,185,129,0.15);border-color:rgba(16,185,129,0.4);color:#5eead4;"
            lbl_s = "color:#a9b6cc;"
            num_inner = "✓"
        elif i == current:
            cls_row = "background:rgba(0,212,255,0.10);border-radius:5px;"
            num_s = "background:#00d4ff;border-color:#00d4ff;color:#04141b;box-shadow:0 0 12px rgba(0,212,255,0.30);"
            lbl_s = "color:#e2e8f0;"
            num_inner = str(i)
        else:
            cls_row = ""
            num_s = "background:#111827;border-color:#2f4368;color:#64748b;"
            lbl_s = "color:#64748b;"
            num_inner = str(i)

        sub = "active" if i == current else ("done" if i in completed else "pending")
        items.append(f"""
<div style="display:flex;align-items:center;gap:12px;padding:10px 12px;{cls_row}">
  <span style="width:24px;height:24px;flex:none;border-radius:50%;
               display:grid;place-content:center;font-size:11px;font-weight:600;
               font-family:'JetBrains Mono',monospace;border:1px solid;{num_s}">{num_inner}</span>
  <span style="line-height:1.2;{lbl_s}font-size:13px;">
    {label}
    <small style="display:block;font-size:10px;text-transform:uppercase;
                  letter-spacing:0.10em;color:#46546e;">{sub}</small>
  </span>
</div>""")

    return '<div style="display:flex;flex-direction:column;gap:2px;">' + "".join(items) + "</div>"


# ── Shared sidebar renderer ───────────────────────────────────────────────────

_NAV = [
    ("app.py", "Home"),
    ("pages/01_projects.py", "Projects"),
    ("pages/02_new_project.py", "New Project"),
    ("pages/03_approvals.py", "Approval Center"),
    ("pages/04_monitoring.py", "Monitoring"),
    ("pages/07_data_contracts.py", "Data Contracts"),
]
_ADMIN_NAV = [
    ("pages/05_settings.py", "Settings"),
]


def render_sidebar(extra_html: str = "") -> None:
    """Render the full sidebar: brand, nav, optional extra, connection status.

    Call from within ``with st.sidebar:`` or at module level — this function
    opens its own ``st.sidebar`` context.

    Args:
        extra_html: Additional HTML injected between nav and connection badge
                    (e.g. wizard_steps() for the new-project page).
    """
    from config import get_config  # local import avoids circular at module load

    cfg = get_config()

    with st.sidebar:
        st.markdown(sidebar_brand(), unsafe_allow_html=True)

        st.markdown(
            '<p style="font-size:11px;font-weight:600;text-transform:uppercase;'
            'letter-spacing:0.12em;color:#46546e;padding:4px 0 2px">Workspace</p>',
            unsafe_allow_html=True,
        )
        for path, label in _NAV:
            st.page_link(path, label=label)

        st.markdown(
            '<p style="font-size:11px;font-weight:600;text-transform:uppercase;'
            'letter-spacing:0.12em;color:#46546e;padding:12px 0 2px">Admin</p>',
            unsafe_allow_html=True,
        )
        for path, label in _ADMIN_NAV:
            st.page_link(path, label=label)

        if extra_html:
            st.markdown(extra_html, unsafe_allow_html=True)

        st.markdown(
            conn_badge(cfg.databricks_host, cfg.catalog, cfg.is_connected),
            unsafe_allow_html=True,
        )
