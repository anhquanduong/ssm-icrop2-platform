import os

# ── Database ───────────────────────────────────────────────────────────────────
# Root-relative path: app_v2.db lives at the project root in both local and cloud runs
DB_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app_v2.db")
)

# ── Reference Model Data ───────────────────────────────────────────────────────
# Absolute local paths for developer debugging (home/office OneDrive variants)
_LOCAL_PATHS = [
    # Home PC (F: drive)
    r"F:\PersonalOD\OneDrive\8.ProjectLinhTinh\1. icrop\Sample Model",
    # Office laptop (D: drive)
    r"D:\OD_personal\OneDrive\8.ProjectLinhTinh\1. icrop\Sample Model",
]

PATH_ORIGINAL_SSM = None
PATH_ADVANCED_SSM = None

for _base in _LOCAL_PATHS:
    _candidate_orig = os.path.join(_base, "SSM-iCrop2")
    _candidate_adv  = os.path.join(_base, "SSM-iCrop2N")
    if os.path.isdir(_candidate_orig):
        PATH_ORIGINAL_SSM = _candidate_orig
        PATH_ADVANCED_SSM = _candidate_adv
        break

# Fallback relative paths for Streamlit Community Cloud / Docker / CI runs
FALLBACK_ORIGINAL_SSM = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "baseline")
)
FALLBACK_ADVANCED_SSM = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "advanced")
)

# ── Active resolved paths (prefer absolute local, fall back to bundled data) ───
ACTIVE_ORIGINAL_SSM = PATH_ORIGINAL_SSM or FALLBACK_ORIGINAL_SSM
ACTIVE_ADVANCED_SSM = PATH_ADVANCED_SSM or FALLBACK_ADVANCED_SSM
