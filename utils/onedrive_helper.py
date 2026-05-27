import os
import pandas as pd
import logging
from typing import List, Dict, Any, Tuple, Optional
from utils.file_parser import get_active_directory
from utils.weather_processor import WeatherProcessor
from utils.excel_parser import ExcelIngestionAgent

logger = logging.getLogger(__name__)

def is_onedrive_path_valid() -> bool:
    """
    Checks if the active data directory (OneDrive or Cloud Fallback) is available on the current host.
    """
    active_dir = get_active_directory()
    return os.path.exists(active_dir) and os.path.isdir(active_dir)

def list_onedrive_weather_files() -> List[str]:
    """
    Scans active_directory/Weather for standard weather spreadsheets (.xls or .xlsx).
    """
    if not is_onedrive_path_valid():
        logger.warning("Active reference directory not available.")
        return []
    
    active_dir = get_active_directory()
    weather_dir = os.path.join(active_dir, "Weather")
    if not os.path.exists(weather_dir) or not os.path.isdir(weather_dir):
        logger.warning(f"Weather folder not found inside active directory: {weather_dir}")
        return []
    
    files = []
    try:
        for f in os.listdir(weather_dir):
            if f.endswith(('.xls', '.xlsx', '.xlsm')) and not f.startswith('~$'):
                files.append(f)
    except Exception as e:
        logger.error(f"Failed to list weather files: {e}")
        
    return sorted(files)

def load_onedrive_weather_file(filename: str) -> Tuple[pd.DataFrame, Optional[float], Optional[float]]:
    """
    Resolves the full path of a selected weather sheet and parses it.
    
    Returns:
        Tuple[pd.DataFrame, float, float]: Daily weather DataFrame, extracted Lat, and extracted Lon
    """
    if not is_onedrive_path_valid():
        raise FileNotFoundError("Active reference directory is unavailable.")
        
    active_dir = get_active_directory()
    file_path = os.path.join(active_dir, "Weather", filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Selected weather file does not exist: {file_path}")
        
    logger.info(f"OneDrive Helper: Routing weather ingestion directly to path: {file_path}")
    return WeatherProcessor.parse_ssm_weather_file(file_path)

def list_onedrive_calibration_files() -> List[str]:
    """
    Scans the root of active_directory for crop calibration/parameter workbooks.
    """
    if not is_onedrive_path_valid():
        logger.warning("Active reference directory not available.")
        return []
        
    active_dir = get_active_directory()
    files = []
    try:
        for f in os.listdir(active_dir):
            if f.endswith(('.xls', '.xlsx')) and not f.startswith('~$'):
                lower_f = f.lower()
                # Scans files containing "crop" or "ssm" or "calibration"
                if "crop" in lower_f or "ssm" in lower_f or "calibration" in lower_f:
                    files.append(f)
    except Exception as e:
        logger.error(f"Failed to list calibration files: {e}")
        
    return sorted(files)

def load_onedrive_calibration_file(filename: str) -> Dict[str, Any]:
    """
    Loads and parses cultivar calibration parameters from a local/fallback workbook.
    """
    if not is_onedrive_path_valid():
        raise FileNotFoundError("Active reference directory is unavailable.")
        
    active_dir = get_active_directory()
    file_path = os.path.join(active_dir, filename)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Selected calibration file does not exist: {file_path}")
        
    logger.info(f"OneDrive Helper: Routing calibration ingestion directly to path: {file_path}")
    return ExcelIngestionAgent.ingest(file_path)
