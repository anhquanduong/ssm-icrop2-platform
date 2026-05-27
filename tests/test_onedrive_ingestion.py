import os
import pandas as pd
from unittest.mock import patch
from utils.onedrive_helper import (
    is_onedrive_path_valid,
    list_onedrive_weather_files,
    load_onedrive_weather_file,
    list_onedrive_calibration_files,
    load_onedrive_calibration_file
)
from utils.excel_parser import ExcelIngestionAgent

@patch('utils.file_parser.get_active_simulation_mode')
def test_onedrive_path_valid(mock_mode):
    """
    Asserts that the configured OneDrive reference path is recognized and accessible.
    """
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    assert is_onedrive_path_valid() is True

@patch('utils.file_parser.get_active_simulation_mode')
def test_list_onedrive_weather_files(mock_mode):
    """
    Asserts that BOKU weather sheets are correctly listed from the OneDrive subdirectory.
    """
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    files = list_onedrive_weather_files()
    assert isinstance(files, list)
    assert len(files) > 0
    assert any(f.endswith('.xls') or f.endswith('.xlsx') for f in files)
    assert "AGHTOGHE.xls" in files

@patch('utils.file_parser.get_active_simulation_mode')
def test_load_onedrive_weather_file(mock_mode):
    """
    Loads and parses a real OneDrive weather file (AGHTOGHE.xls) and asserts it matches
    the canonical engine specifications.
    """
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    weather_df, lat, lon = load_onedrive_weather_file("AGHTOGHE.xls")
    
    # Assert return types
    assert isinstance(weather_df, pd.DataFrame)
    assert not weather_df.empty
    
    # Assert columns comply with meteorological specifications
    required_cols = {'YEAR', 'DOY', 'TMAX', 'TMIN', 'SRAD', 'RAIN'}
    assert required_cols.issubset(set(weather_df.columns))
    
    # Assert coordinates were parsed successfully from header metadata
    assert lat is not None
    assert lon is not None
    assert 30.0 < lat < 42.0   # Iran region Latitude bounds
    assert 45.0 < lon < 60.0   # Iran region Longitude bounds

@patch('utils.file_parser.get_active_simulation_mode')
def test_list_onedrive_calibration_files(mock_mode):
    """
    Asserts that cultivar calibration sheets are correctly scanned from the OneDrive folder.
    """
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    files = list_onedrive_calibration_files()
    assert isinstance(files, list)
    assert len(files) > 0
    assert "SSM-iCrop2_2023_2_20.xls" in files

@patch('utils.file_parser.get_active_simulation_mode')
def test_load_onedrive_calibration_file(mock_mode):
    """
    Loads a real OneDrive calibration workbook (SSM-iCrop2_2023_2_20.xls) and validates
    that physiological variables are mapped correctly.
    """
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    params = load_onedrive_calibration_file("SSM-iCrop2_2023_2_20.xls")
    assert isinstance(params, dict)
    assert len(params) > 0
    
    # Assert core physiological keys were mapped and parsed as floats
    assert "TBD" in params or "BaseTemp" in params
    assert "IRUE" in params or "RUE" in params or "RUE_MAX" in params
    assert "SLA" in params or "SpecificLeafArea" in params
    
    # Let's verify specific crop thresholds
    tbd_val = params.get("TBD", params.get("BaseTemp"))
    assert isinstance(tbd_val, float)
    assert tbd_val > 0.0
