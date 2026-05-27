import os
import pytest
from unittest.mock import patch, MagicMock
from utils.file_parser import resolve_file_source, get_active_directory, get_active_simulation_mode
from utils.onedrive_helper import (
    is_onedrive_path_valid,
    list_onedrive_weather_files,
    list_onedrive_calibration_files
)
from utils.excel_parser import ExcelIngestionAgent
from core.config import (
    PATH_ORIGINAL_SSM,
    PATH_ADVANCED_SSM,
    FALLBACK_ORIGINAL_SSM,
    FALLBACK_ADVANCED_SSM
)

def test_snavl_init_synonym_mapping():
    """
    Verifies that the Excel parameters parser maps the new advanced stress variables correctly.
    """
    mapped_snavl = ExcelIngestionAgent.map_term_to_engine_variable("SNAVL_init")
    assert mapped_snavl == "SNAVL_init"
    
    mapped_leach = ExcelIngestionAgent.map_term_to_engine_variable("leach_efficiency")
    assert mapped_leach == "leach_eff"
    
    mapped_tbt = ExcelIngestionAgent.map_term_to_engine_variable("tipping_bucket_threshold")
    assert mapped_tbt == "tbt"

@patch('utils.file_parser.get_active_simulation_mode')
def test_resolve_file_source_routing(mock_mode):
    """
    Asserts that resolve_file_source points to correct directories depending on simulation mode.
    """
    # 1. Test Advanced track routing
    mock_mode.return_value = "Advanced Agro-Climate Model (Stress Limited)"
    path_adv = resolve_file_source("Advanced", "test.xls")
    
    # If F:\ local drive exists, check it points to PATH_ADVANCED_SSM
    if os.path.exists(PATH_ADVANCED_SSM):
        assert PATH_ADVANCED_SSM in path_adv
    else:
        # Cloud fallback verification
        assert FALLBACK_ADVANCED_SSM in path_adv
        
    # 2. Test Potential track routing
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    path_pot = resolve_file_source("Original", "test.xls")
    
    if os.path.exists(PATH_ORIGINAL_SSM):
        assert PATH_ORIGINAL_SSM in path_pot
    else:
        assert FALLBACK_ORIGINAL_SSM in path_pot

@patch('utils.file_parser.PATH_ADVANCED_SSM', '/mocked/missing/path_adv')
@patch('utils.file_parser.PATH_ORIGINAL_SSM', '/mocked/missing/path_pot')
def test_cloud_relative_fallbacks():
    """
    Mocks a missing F:\\ drive configuration (Streamlit Cloud scenario)
    and asserts that the engine gracefully falls back to Git-tracked relative paths.
    """
    # Verify fallback for Advanced mode
    path_adv = resolve_file_source("Advanced", "test.xls")
    assert FALLBACK_ADVANCED_SSM in path_adv
    
    # Verify fallback for Potential/Original mode
    path_pot = resolve_file_source("Original", "test.xls")
    assert FALLBACK_ORIGINAL_SSM in path_pot

@patch('utils.file_parser.get_active_simulation_mode')
def test_list_files_by_track(mock_mode):
    """
    Verifies that file listing helpers cleanly switch targets depending on the active track.
    """
    # 1. Advanced track checks
    mock_mode.return_value = "Advanced Agro-Climate Model (Stress Limited)"
    adv_cal_files = list_onedrive_calibration_files()
    assert isinstance(adv_cal_files, list)
    assert len(adv_cal_files) > 0
    # The advanced crop calibration workbook should be in the list
    assert "SSM-iCrop2N_2022_05_29.xls" in adv_cal_files
    
    # 2. Original/Potential track checks
    mock_mode.return_value = "Original SSM-iCrop (Potential Yield)"
    pot_cal_files = list_onedrive_calibration_files()
    assert isinstance(pot_cal_files, list)
    assert len(pot_cal_files) > 0
    assert "SSM-iCrop2_2023_2_20.xls" in pot_cal_files

@patch('utils.file_parser.get_active_simulation_mode')
def test_ingest_advanced_calibration_workbook(mock_mode):
    """
    Ingests parameters from the actual SSM-iCrop2N calibration template
    and asserts that advanced stress variables are parsed correctly.
    """
    mock_mode.return_value = "Advanced Agro-Climate Model (Stress Limited)"
    from utils.onedrive_helper import load_onedrive_calibration_file
    
    params = load_onedrive_calibration_file("SSM-iCrop2N_2022_05_29.xls")
    assert isinstance(params, dict)
    assert len(params) > 0
    
    # Verify core mapped keys
    assert "TBD" in params
    assert "IRUE" in params
    assert "SLA" in params
    
    # Check if newly extended BOKU stress thresholds exist (or their fallbacks are populated)
    # The template file might contain values or we fall back
    assert "tbt" in params
    assert "leach_eff" in params
    assert "SNAVL_init" in params
