import os
import logging
from core.config import (
    PATH_ORIGINAL_SSM,
    PATH_ADVANCED_SSM,
    FALLBACK_ORIGINAL_SSM,
    FALLBACK_ADVANCED_SSM
)

logger = logging.getLogger(__name__)

def get_active_simulation_mode() -> str:
    """
    Retrieves the currently selected simulation mode from Streamlit session state,
    defaulting to Advanced mode if not running under Streamlit or not yet initialized.
    """
    try:
        import streamlit as st
        # Returns the selectbox value bound to this key, e.g. "Original SSM-iCrop (Potential Yield)"
        return st.session_state.get("icrop2_sim_mode_selection", "Advanced")
    except Exception:
        return "Advanced"

def resolve_file_source(simulation_mode: str, file_name: str) -> str:
    """
    Dynamically resolves a file path based on the simulation mode and accessibility of local drives.
    Falls back to Git-tracked relative paths if the local OneDrive F:\\ path is missing on the current host.
    """
    is_advanced = "Advanced" in simulation_mode or "Nitrogen" in simulation_mode
    
    if is_advanced:
        local_dir = PATH_ADVANCED_SSM
        fallback_dir = FALLBACK_ADVANCED_SSM
    else:
        local_dir = PATH_ORIGINAL_SSM
        fallback_dir = FALLBACK_ORIGINAL_SSM
        
    # Check if the primary local OneDrive F:\\ path is accessible
    if os.path.exists(local_dir) and os.path.isdir(local_dir):
        target_dir = local_dir
    else:
        # Fall back to Git-tracked relative paths for Streamlit Cloud or Docker containers
        target_dir = fallback_dir
        os.makedirs(target_dir, exist_ok=True)
        
    resolved_path = os.path.join(target_dir, file_name)
    logger.debug(f"Resolved file source: {resolved_path} (mode={simulation_mode})")
    return resolved_path

def get_active_directory() -> str:
    """
    Helper to resolve the active directory based on current UI simulation mode.
    """
    mode = get_active_simulation_mode()
    is_advanced = "Advanced" in mode or "Nitrogen" in mode
    
    if is_advanced:
        local_dir = PATH_ADVANCED_SSM
        fallback_dir = FALLBACK_ADVANCED_SSM
    else:
        local_dir = PATH_ORIGINAL_SSM
        fallback_dir = FALLBACK_ORIGINAL_SSM
        
    if os.path.exists(local_dir) and os.path.isdir(local_dir):
        return local_dir
    else:
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir
