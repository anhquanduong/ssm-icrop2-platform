import sqlite3
import pandas as pd
import numpy as np
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_EXCEL_PATH = r"D:\OD_personal\OneDrive\8.ProjectLinhTinh\1. icrop\Sample Model\Update icrop model and crop\input_ALL_input_worksheets_20240830.xlsx"

def import_master_crop_parameters(excel_path: str, db_path: str):
    """
    Parses the Crop sheet of the Master Excel sheet and seeds the crops table.
    Uses Pandas to read the spreadsheet, maps variables dynamically, and bulk seeds sqlite.
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel master parameters spreadsheet not found at: {excel_path}")
        
    logger.info(f"Importing crop parameters from spreadsheet: {excel_path}")
    df = pd.read_excel(excel_path, sheet_name="Crop", header=None)
    
    # 1. Parse parameter names from Column 0, rows 6 to the end
    params_map = {}
    for r in range(6, df.shape[0]):
        var_label = df.iloc[r, 0]
        if pd.notna(var_label) and str(var_label).strip() != "":
            clean_name = str(var_label).split("=")[0].split("(")[0].strip()
            params_map[r] = clean_name
            
    # 2. Parse crop columns
    crop_records = []
    for col_idx in range(2, df.shape[1]):
        crop_name = df.iloc[4, col_idx]
        cultivar = df.iloc[5, col_idx]
        
        if pd.notna(crop_name) and str(crop_name).strip() != "" and str(crop_name).upper() not in ["CROP:", "CROPCOLNO -->"]:
            # Parse parameters
            param_dict = {}
            for r, name in params_map.items():
                val = df.iloc[r, col_idx]
                if pd.notna(val) and str(val).strip() != "-":
                    try:
                        param_dict[name] = float(val)
                    except ValueError:
                        param_dict[name] = str(val)
            
            # Map standard crop parameters aliases for engine compatibility
            if "RUE_MAX" not in param_dict and "TBRUE" in param_dict:
                param_dict["RUE_MAX"] = param_dict["TBRUE"]
            if "IRUE" not in param_dict and "TBRUE" in param_dict:
                param_dict["IRUE"] = param_dict["TBRUE"]
            if "TBD" not in param_dict:
                param_dict["TBD"] = 8.0 # fallback default C4
            if "TP1D" not in param_dict:
                param_dict["TP1D"] = 34.0
            if "TP2D" not in param_dict:
                param_dict["TP2D"] = 37.0
            if "TCD" not in param_dict:
                param_dict["TCD"] = 45.0
            if "cpp" not in param_dict:
                param_dict["cpp"] = param_dict.get("CPP", 12.0)
            if "ppsen" not in param_dict:
                param_dict["ppsen"] = param_dict.get("ppsen", 0.0)
            if "bdSOWEMR" not in param_dict:
                param_dict["bdSOWEMR"] = param_dict.get("bdSOWEMR", 4.5)
            if "bdEMREJU" not in param_dict:
                param_dict["bdEMREJU"] = param_dict.get("bdEMRR1", 20.0)
            if "PHYL" not in param_dict:
                param_dict["PHYL"] = param_dict.get("PHYL1", 46.0)
            if "PLACON" not in param_dict:
                param_dict["PLACON"] = 1.0
            if "PLAPOW8" not in param_dict:
                param_dict["PLAPOW8"] = param_dict.get("PLAPOW", 2.15)
            if "SLA" not in param_dict:
                param_dict["SLA"] = 0.021
            if "TKILL" not in param_dict:
                param_dict["TKILL"] = param_dict.get("FrzTh", -4.0)
            if "FRZLDR" not in param_dict:
                param_dict["FRZLDR"] = param_dict.get("FrzLDR", 0.01)
            if "TBRUE" not in param_dict:
                param_dict["TBRUE"] = 2.0
            if "TP1RUE" not in param_dict:
                param_dict["TP1RUE"] = 14.0
            if "TP2RUE" not in param_dict:
                param_dict["TP2RUE"] = 30.0
            if "TCRUE" not in param_dict:
                param_dict["TCRUE"] = 38.0
            if "KPAR" not in param_dict:
                param_dict["KPAR"] = 0.65
            if "IRUE" not in param_dict:
                param_dict["IRUE"] = 2.0
            if "FLF1A" not in param_dict:
                param_dict["FLF1A"] = 0.53
            if "FLF1B" not in param_dict:
                param_dict["FLF1B"] = 0.3
            if "WTOPL" not in param_dict:
                param_dict["WTOPL"] = 180.0
            if "FLF2" not in param_dict:
                param_dict["FLF2"] = 0.13
            if "FRTRL" not in param_dict:
                param_dict["FRTRL"] = 0.22
            if "GCC" not in param_dict:
                param_dict["GCC"] = 1.0
            if "PDHI" not in param_dict:
                param_dict["PDHI"] = 0.02
            if "WDHI1" not in param_dict:
                param_dict["WDHI1"] = 0.0
            if "WDHI2" not in param_dict:
                param_dict["WDHI2"] = 0.0
            if "WDHI3" not in param_dict:
                param_dict["WDHI3"] = 9999.0
            if "WDHI4" not in param_dict:
                param_dict["WDHI4"] = 9999.0
            if "iDEPORT" not in param_dict:
                param_dict["iDEPORT"] = param_dict.get("DEPORT", 150.0)
            if "MEED" not in param_dict:
                param_dict["MEED"] = param_dict.get("EED", 900.0)
            if "GRTDP" not in param_dict:
                param_dict["GRTDP"] = 20.0
            if "TEC" not in param_dict:
                param_dict["TEC"] = param_dict.get("TEC350", 4.5)
            if "WSSG" not in param_dict:
                param_dict["WSSG"] = 0.3
            if "WSSL" not in param_dict:
                param_dict["WSSL"] = 0.4
            if "WSSD" not in param_dict:
                param_dict["WSSD"] = 0.4
            if "FLDKL" not in param_dict:
                param_dict["FLDKL"] = 20.0
                
            crop_name_clean = crop_name.strip()
            cultivar_clean = cultivar.strip() if pd.notna(cultivar) else "Default"
            
            crop_records.append((
                crop_name_clean,
                cultivar_clean,
                json.dumps(param_dict),
                "Fruit/Seed",
                "Annual (Single-Season)",
                5.0,
                0.0
            ))
            
    # Seed SQLite
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ensure crops table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_name TEXT NOT NULL,
            cultivar TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            crop_produce_type TEXT,
            lifecycle_strategy TEXT,
            t_dormancy_trigger REAL,
            t_base_winter REAL,
            UNIQUE(crop_name, cultivar)
        )
    """)
    
    cursor.executemany("""
        INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, crop_records)
    
    conn.commit()
    conn.close()
    logger.info(f"Successfully seeded SQLite crops table with {len(crop_records)} spreadsheet records.")

def check_and_seed_database(db_path: str, excel_path: Optional[str] = None):
    """
    Main database seeder coordinator called during application initialization.
    Checks if database crops table is blank, and seeds it from the Excel file if present.
    Incorporate robust try-except to prevent cloud hosting breakages if Excel path is missing.
    """
    if excel_path is None:
        excel_path = DEFAULT_EXCEL_PATH
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create crops table if not exists to avoid select operational errors
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crop_name TEXT NOT NULL,
            cultivar TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            crop_produce_type TEXT,
            lifecycle_strategy TEXT,
            t_dormancy_trigger REAL,
            t_base_winter REAL,
            UNIQUE(crop_name, cultivar)
        )
    """)
    
    # Check if table is blank
    cursor.execute("SELECT COUNT(*) FROM crops")
    count = cursor.fetchone()[0]
    conn.close()
    
    if count == 0:
        logger.info("Crop varieties database is blank. Initiating automated Excel parameter parsing...")
        try:
            import_master_crop_parameters(excel_path, db_path)
        except Exception as excel_err:
            logger.warning(
                f"Bypassing excel parameters ingestion (local Excel path not accessible/found: {excel_err}). "
                f"Attempting JSON presets seeding fallback..."
            )
            # Fallback to load from committed JSON file
            json_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "data", "seeded_crops_preset.json"
            )
            if os.path.exists(json_path):
                logger.info(f"Seeding crops from committed JSON presets file: {json_path}")
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        records = json.load(f)
                    crop_records = []
                    for r in records:
                        crop_records.append((
                            r["crop_name"],
                            r["cultivar"],
                            r["parameters_json"],
                            r["crop_produce_type"],
                            r["lifecycle_strategy"],
                            r["t_dormancy_trigger"],
                            r["t_base_winter"]
                        ))
                    
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.executemany("""
                        INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, crop_records)
                    conn.commit()
                    conn.close()
                    logger.info(f"Successfully seeded database with {len(crop_records)} records from JSON fallback.")
                except Exception as json_err:
                    logger.error(f"Failed to seed crops database using JSON fallback: {json_err}")
            else:
                logger.error(f"JSON presets file not found at: {json_path}. Database seeding aborted.")
    else:
        logger.info(f"Crop parameter database already contains {count} seeded varieties. Ingestion skipped.")
