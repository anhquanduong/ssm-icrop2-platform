import pandas as pd
import logging

logger = logging.getLogger(__name__)

def format_simulation_run(results_df: pd.DataFrame, scenario_name: str) -> pd.DataFrame:
    """
    Ingests the raw simulation results dataframe containing daily crop development vectors,
    extracts the target DOY, WTOP, and LAI metrics, converts biomass to kg/ha,
    and extracts F_WATER and F_NUTR stress indices if present.
    
    Parameters:
        results_df (pd.DataFrame): Daily outputs from SSMiCropEngine.
        scenario_name (str): Label used for scenario grouping.
        
    Returns:
        pd.DataFrame: A formatted copy of the dataframe with columns:
                      ['DOY', 'BIOMASS', 'LAI', 'F_WATER', 'F_NUTR', 'Scenario']
    """
    # Biological validation of incoming dataframe columns
    for req_col in ["DOY", "WTOP", "LAI"]:
        if req_col not in results_df.columns:
            logger.error(f"Cannot log run in ledger: Column '{req_col}' is missing.")
            raise KeyError(f"Simulation output lacks mandatory daily variable: '{req_col}'")
            
    logger.info(f"Formatting simulation run '{scenario_name}' for history comparison ledger.")
    
    fidelity_arr = results_df["Model_Fidelity"].values if "Model_Fidelity" in results_df.columns else ["Advanced"] * len(results_df)
    first_fidelity = fidelity_arr[0] if len(fidelity_arr) > 0 else "Advanced"
    mgt_status = "Ignored (Potential Baseline)" if first_fidelity == "Classic" else "Active"
    
    # Extract columns, converting WTOP (g/m²) to BIOMASS (kg/ha)
    compiled_df = pd.DataFrame({
        "DOY": results_df["DOY"].values,
        "Simulation_Timeline_Days": results_df["Simulation_Timeline_Days"].values if "Simulation_Timeline_Days" in results_df.columns else results_df["DOY"].values,
        "BIOMASS": results_df["WTOP"].values * 10.0,  # Conversion factor: 1 g/m² = 10 kg/ha
        "LAI": results_df["LAI"].values,
        "F_WATER": results_df["F_WATER"].values if "F_WATER" in results_df.columns else [1.0] * len(results_df),
        "F_NUTR": results_df["F_NUTR"].values if "F_NUTR" in results_df.columns else [1.0] * len(results_df),
        "Model_Fidelity": fidelity_arr,
        "Management": [mgt_status] * len(results_df),
        "Scenario": scenario_name
    })
    
    return compiled_df
