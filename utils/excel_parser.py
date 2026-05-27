import pandas as pd
import openpyxl
from typing import Dict, Any, Union, Optional
import io
import logging

logger = logging.getLogger(__name__)

# Strict crop engine target variables and their associated user terminology synonyms
SYNONYM_MAP = {
    "TBD": ["tbd", "tbd =", "t_base", "tb", "basetemp", "base_temp", "tbase", "base temp", "temperature base"],
    "TP1D": ["tp1d", "tp1d =", "tp1", "t_opt", "t_opt1", "opt_temp", "opttemp", "to", "topt1", "opt temp 1", "optimum temp 1"],
    "TP2D": ["tp2d", "tp2d =", "tp2", "t_opt2", "topt2", "opt temp 2", "optimum temp 2"],
    "TCD": ["tcd", "tcd =", "t_ceil", "tx", "max_temp", "maxtemp", "ceiling_temp", "tceil", "ceil temp", "ceiling temp"],
    "cpp": ["cpp", "cpp =", "cpp_photo", "photoperiod_threshold", "cpp_hours", "critical photoperiod"],
    "ppsen": ["ppsen", "ppsen =", "photoperiod_sensitivity", "ppsens", "photo sensitivity"],
    "bdSOWEMR": ["bdsowemr", "bd_sowemr", "sow_to_emr", "sowtoemr", "sowing to emergence"],
    "bdEMREJU": ["bdemreju", "bd_emreju", "emr_to_eju", "emrtoeju", "emergence to juvenile"],
    "bdSILPM": ["bdsilpm", "bd_silpm", "sil_to_pm", "siltopm", "bdbsgpm", "bd_bsgpm", "silking to maturity", "seed fill duration"],
    "PHYL": ["phyl", "phyl =", "phyllo", "phyllochron", "phyl_temp", "phyllochron temperature"],
    "PLACON": ["placon", "placon =", "pla_con", "leaf_area_coeff", "leaf area constant"],
    "PLAPOW8": ["plapow8", "plapow8 =", "pla_pow", "plapow", "leaf_power", "leaf exponent"],
    "SLA": ["sla", "sla =", "specific_leaf_area", "specificleafarea", "specific leaf area"],
    "TKILL": ["tkill", "tkill =", "t_kill", "frost_kill", "frost_threshold", "killing temp"],
    "FRZLDR": ["frzldr", "frzldr =", "frost_rate", "freezing rate"],
    "TBRUE": ["tbrue", "tbrue =", "tb_rue", "tbase_rue", "base temp rue"],
    "TP1RUE": ["tp1rue", "tp1rue =", "topt1_rue", "tp1_rue", "opt temp rue"],
    "TP2RUE": ["tp2rue", "tp2rue =", "topt2_rue", "tp2_rue"],
    "TCRUE": ["tcrue", "tcrue =", "tceil_rue", "tmax_rue", "ceil temp rue"],
    "KPAR": ["kpar", "kpar =", "k_par", "extinction_coeff", "k", "light extinction"],
    "IRUE": ["irue", "irue =", "rue_max", "rue", "iruemax", "radiation use efficiency"],
    "FLF1A": ["flf1a", "flf1a =", "alloc_lf1a"],
    "FLF1B": ["flf1b", "flf1b =", "alloc_lf1b"],
    "WTOPL": ["wtopl", "wtopl =", "wtop_limit", "biomass leaf threshold"],
    "FLF2": ["flf2", "flf2 =", "alloc_lf2"],
    "FRTRL": ["frtrl", "frtrl =", "stem_transloc_frac", "translocation fraction"],
    "GCC": ["gcc", "gcc =", "grain_conversion", "grain conversion coeff"],
    "PDHI": ["pdhi", "pdhi =", "hi_increase_rate", "pdhi_rate", "daily hi increase"],
    "iDEPORT": ["ideport", "ideport =", "initial_root_depth", "init root depth"],
    "MEED": ["meed", "meed =", "max_root_depth", "max_rooting_depth", "max root depth"],
    "GRTDP": ["grtdp", "grtdp =", "root_growth_rate", "daily root growth"],
    "TEC": ["tec", "tec =", "tec_coeff", "transp_eff_coeff", "transpiration efficiency"],
    "WSSG": ["wssg", "wssg =", "water_stress_rue", "rue stress limit"],
    "WSSL": ["wssl", "wssl =", "water_stress_lai", "lai stress limit"],
    "WSSD": ["wssd", "wssd =", "water_stress_pheno"],
    "FLDKL": ["fldkl", "fldkl =", "flooding_kill_days", "flood duration threshold"],
    "SLNG": ["slng", "slng =", "leaf_n_green"],
    "SLNS": ["slns", "slns =", "leaf_n_senesced"],
    "SNCG": ["sncg", "sncg =", "stem_n_green"],
    "SNCS": ["sncs", "sncs =", "stem_n_senesced"],
    "GNC": ["gnc", "gnc =", "grain_n_conc"],
    "MXNUP": ["mxnup", "mxnup =", "max_n_uptake"],
    "SNAVL_init": ["snavl_init", "initial_n", "initial_nitrogen", "initial soil nitrogen", "snavl", "soil_n_init"],
    "leach_eff": ["leach_eff", "leach_efficiency", "leaching efficiency", "leaching_eff", "leach efficiency"],
    "tbt": ["tbt", "tipping_bucket_threshold", "tipping bucket", "drainage threshold", "tbt_threshold"]
}

# Pre-compiled BOKU defaults in case of missing variables
DEFAULTS_MATRIX = {
    "BaseTemp": 8.0,
    "OptTemp": 34.0,
    "MaxTemp": 45.0,
    "RUE": 1.6,
    "SpecificLeafArea": 0.02,
    "MaxLAI": 5.0,
    "tbt": 1.0,
    "leach_eff": 0.8,
    "SNAVL_init": 150.0
}


class ExcelIngestionAgent:
    """
    Intelligent Input Ingestion Agent that wraps Excel workbook parsing routines.
    Scans vertical or horizontal sheet layout styles, matches terms to synonyms,
    extracts parameters for Maize/Sorghum cultivars, and maps them to clean engine inputs.
    """

    @staticmethod
    def map_term_to_engine_variable(raw_term: str) -> Optional[str]:
        """
        Translates a raw sheet parameter term to the strict engine variable name using the SYNONYM_MAP.
        """
        clean_term = str(raw_term).strip().lower().replace(":", "")
        for strict_var, synonyms in SYNONYM_MAP.items():
            if clean_term == strict_var.lower() or clean_term in [syn.lower() for syn in synonyms]:
                return strict_var
        return None

    @classmethod
    def ingest(cls, file_input: Union[str, io.BytesIO]) -> Dict[str, Any]:
        """
        Ingests any non-standard crop parameters Excel sheet, maps terminology, and cleans variables.
        
        Parameters:
            file_input (str or BytesIO): Workbook data source.
            
        Returns:
            Dict[str, Any]: Terminology-mapped crop parameters dictionary.
        """
        try:
            # Use pandas ExcelFile to inspect sheet names (supports .xls and .xlsx automatically via xlrd/openpyxl)
            xls = pd.ExcelFile(file_input)
            sheets = xls.sheet_names
            
            # 1. Identify parameter sheets using keyword heuristics
            target_sheet = sheets[0]
            for sheet in sheets:
                lower_s = sheet.lower()
                if "crop" in lower_s or "param" in lower_s or "coeff" in lower_s or "cultivar" in lower_s:
                    target_sheet = sheet
                    break
            
            logger.info(f"Ingestion Agent scanning target parameters sheet: {target_sheet}")
            
            # Load raw sheet data as a 0-indexed DataFrame grid without headers
            df_sheet = pd.read_excel(file_input, sheet_name=target_sheet, header=None)
            max_row = len(df_sheet)
            max_col = len(df_sheet.columns)
            
            # 1-indexed helper matching openpyxl semantics
            def get_cell_val(r_1: int, c_1: int) -> Any:
                r_0 = r_1 - 1
                c_0 = c_1 - 1
                if 0 <= r_0 < max_row and 0 <= c_0 < max_col:
                    val = df_sheet.iloc[r_0, c_0]
                    return val if pd.notna(val) else None
                return None
            
            raw_params = {}
            
            # 2. Check for Vertical Scenario Selection (e.g. BOKU 'CropColNo -->' scenario selector)
            # This identifies sheets where parameters are listed vertically in column 0 or 1,
            # and values exist in scenario columns.
            scenario_col_index = 2 # Default to Column C (index 2)
            has_scenario_selector = False
            
            for r in range(1, min(max_row + 1, 15)):
                val_c0 = get_cell_val(r, 1)
                if val_c0 and "colno" in str(val_c0).lower():
                    # Scenario selector detected! Read selector value from row
                    # Search across row cells for scenario index
                    for col_idx in range(2, min(max_col + 1, 10)):
                        cell_val = get_cell_val(r, col_idx)
                        if cell_val is not None:
                            try:
                                scenario_col_index = int(cell_val) - 1 # BOKU uses 1-based index (e.g., column index 3)
                                has_scenario_selector = True
                                logger.info(f"Ingestion Agent detected scenario selection parameter column: {scenario_col_index + 1}")
                                break
                            except (ValueError, TypeError):
                                pass
                    if has_scenario_selector:
                        break
 
            # 3. Dynamic Vertical Row Extraction Loop
            # Scan rows vertically. Translate terms to strict engine keys.
            vertical_matches = 0
            for r in range(1, max_row + 1):
                key_candidate = get_cell_val(r, 1)
                if key_candidate is None:
                    # Try second column (column B)
                    key_candidate = get_cell_val(r, 2)
                    val_col_idx = scenario_col_index if has_scenario_selector else 3
                else:
                    val_col_idx = scenario_col_index if has_scenario_selector else 2
                    
                if key_candidate is not None:
                    mapped_var = cls.map_term_to_engine_variable(str(key_candidate))
                    if mapped_var:
                        # Extract value from active value column
                        val_candidate = get_cell_val(r, val_col_idx + 1)
                        if val_candidate is not None:
                            try:
                                # Clean string numbers or percentage values
                                if isinstance(val_candidate, str) and "%" in val_candidate:
                                    raw_params[mapped_var] = float(val_candidate.replace("%", "").strip()) / 100.0
                                else:
                                    raw_params[mapped_var] = float(val_candidate) if not isinstance(val_candidate, str) else val_candidate
                                vertical_matches += 1
                            except (ValueError, TypeError):
                                raw_params[mapped_var] = val_candidate
 
            # 4. Fallback: Horizontal Layout Scanning
            # If vertical scanning extracted fewer than 3 parameters, we switch to horizontal scanning
            # (columns represent keys, rows represent scenarios/cultivars)
            if vertical_matches < 3:
                logger.info("Ingestion Agent switching to Horizontal Column Header scanning...")
                df = pd.read_excel(file_input, sheet_name=target_sheet)
                
                # Check if headers contain synonym keys
                mapped_cols = {}
                for col in df.columns:
                    mapped_var = cls.map_term_to_engine_variable(str(col))
                    if mapped_var:
                        mapped_cols[col] = mapped_var
                        
                if len(mapped_cols) >= 3:
                    # Horizontal structure confirmed. Read values from the first data row
                    first_row = df.iloc[0]
                    for raw_col, engine_var in mapped_cols.items():
                        val = first_row[raw_col]
                        try:
                            raw_params[engine_var] = float(val) if pd.notna(val) else val
                        except (ValueError, TypeError):
                            raw_params[engine_var] = val
                            
            # 5. Populate and validate engine constraints
            # Map simplified UI settings to strict parameters if vertical or horizontal keys were simplified
            alias_map = {
                "BaseTemp": "TBD",
                "OptTemp": "TP1D",
                "MaxTemp": "TCD",
                "RUE": "IRUE",
                "SpecificLeafArea": "SLA"
            }
            for alias_k, strict_k in alias_map.items():
                if alias_k in raw_params and strict_k not in raw_params:
                    raw_params[strict_k] = raw_params[alias_k]
                elif strict_k in raw_params and alias_k not in raw_params:
                    raw_params[alias_k] = raw_params[strict_k]

            # Ingestion agent default fallbacks
            for alias_k, default_v in DEFAULTS_MATRIX.items():
                if alias_k not in raw_params:
                    if alias_k in alias_map:
                        strict_k = alias_map[alias_k]
                        if strict_k in raw_params:
                            raw_params[alias_k] = raw_params[strict_k]
                        else:
                            raw_params[alias_k] = default_v
                            raw_params[strict_k] = default_v
                            logger.warning(f"Ingestion Agent using default fallback: {alias_k} = {default_v}")
                    else:
                        raw_params[alias_k] = default_v
                        logger.warning(f"Ingestion Agent using default fallback: {alias_k} = {default_v}")
            
            logger.info(f"Ingestion Agent complete. Parsed {len(raw_params)} parameter keys.")
            return raw_params
            
        except Exception as e:
            logger.error(f"Ingestion Agent encountered an error during Excel parsing: {e}")
            raise RuntimeError(f"Excel Ingestion Agent failed: {str(e)}")


def parse_crop_parameters(file_input: Union[str, io.BytesIO]) -> Dict[str, Any]:
    """
    Wrap function maintaining backwards compatibility for existing systems.
    Delegates to the newly designed ExcelIngestionAgent.
    """
    return ExcelIngestionAgent.ingest(file_input)
