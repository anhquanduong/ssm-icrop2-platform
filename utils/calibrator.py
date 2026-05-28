import pandas as pd
import numpy as np
import logging
import json
from typing import List, Dict, Any, Tuple, Optional
from core.model_engine import SSMiCropEngine, DEFAULT_CROP_PARAMETERS

logger = logging.getLogger(__name__)

def run_calibration_search(
    observed_data: List[Dict[str, Any]], 
    weather_target_df: pd.DataFrame, 
    soil_target_profile: Dict[str, Any], 
    parameter_bounds: Dict[str, Tuple[float, float]], 
    crop_type: str,
    latitude: float,
    soil_config: Dict[str, Any],
    fertilizer_schedule: List[Dict[str, Any]],
    water_management: Dict[str, Any],
    engine_mode: str = "Advanced",
    advanced_options: Dict[str, bool] = None,
    progress_callback = None
) -> Tuple[Dict[str, float], float, float]:
    """
    Executes a production-grade coordinate descent and adaptive grid search calibration routine.
    Adjusts the crop constants in parameter_bounds to minimize RMSE against observed_data.
    
    Returns:
        Tuple: (optimized_parameters_dict, original_rmse, optimized_rmse)
    """
    # 1. Validation & Setup
    if not observed_data:
        raise ValueError("Observed data matrix is empty! Please provide historical yield targets.")
    if not parameter_bounds:
        raise ValueError("No variables selected for SciPy calibration adjustment!")
        
    # Enforce physically realistic biophysical optimization boundaries
    safe_bounds = {}
    for k, v in parameter_bounds.items():
        low, high = v
        if k in ["IRUE", "RUE_MAX", "RUE"]:
            low = max(low, 1.0)
            high = min(high, 2.5)
        elif k in ["TBD", "t_base", "BaseTemp"]:
            low = max(low, 0.0)
            high = min(high, 15.0)
        elif k in ["TP1D", "TP2D", "t_opt1", "t_opt2"]:
            low = max(low, 20.0)
            high = min(high, 35.0)
        
        if low >= high:
            high = low + 0.1
        safe_bounds[k] = (low, high)
    parameter_bounds = safe_bounds

    num_params = len(parameter_bounds)
    logger.info(f"Initiating calibration optimizer for crop '{crop_type}' on {num_params} variables.")
    
    # Save original parameters to compute original RMSE
    original_params = {}
    for param_name in parameter_bounds.keys():
        original_params[param_name] = DEFAULT_CROP_PARAMETERS[crop_type].get(param_name, 0.0)
        
    # Define candidate evaluation function
    def evaluate_candidate(candidate_params: Dict[str, float]) -> float:
        # Keep track of old coefficients in default parameters dict
        saved_old = {}
        for k, v in candidate_params.items():
            saved_old[k] = DEFAULT_CROP_PARAMETERS[crop_type].get(k)
            DEFAULT_CROP_PARAMETERS[crop_type][k] = v
            
        try:
            # Instantiate simulation engine with active configurations
            engine = SSMiCropEngine(
                weather_df=weather_target_df,
                latitude=latitude,
                soil_params=soil_target_profile,
                soil_config=soil_config,
                fertilizer_schedule=fertilizer_schedule,
                water_management=water_management,
                mode=engine_mode,
                advanced_options=advanced_options,
                sim_years=len(weather_target_df['YEAR'].unique())
            )
            
            # Run simulation
            results_df = engine.run_simulation(crop_type=crop_type)
            
            # Compute RMSE against observations
            total_err_sq = 0.0
            count = 0
            
            for obs in observed_data:
                obs_year = int(obs["Year"])
                obs_yield = float(obs["Observed Yield (t/ha)"])
                obs_lai = obs.get("Observed Peak LAI (Optional)")
                
                # Retrieve year in timeline
                year_subset = weather_target_df[weather_target_df["YEAR"] == obs_year]["Current_Year"].unique()
                if len(year_subset) == 0:
                    continue
                yr_rel = year_subset[0]
                df_yr = results_df[results_df["Current_Year"] == yr_rel]
                if df_yr.empty:
                    continue
                    
                # Determine yield based on crop harvested organ type
                prod_type = DEFAULT_CROP_PARAMETERS[crop_type].get("crop_produce_type", "Fruit/Seed")
                if prod_type == "Tuber/Root":
                    sim_yield_raw = df_yr["WROOT"].max()
                elif prod_type == "Vegetative Foliage":
                    sim_yield_raw = df_yr["WLF"].max()
                else:
                    sim_yield_raw = df_yr["WGRN"].max()
                sim_yield = sim_yield_raw * 0.01  # convert g/m² to t/ha
                
                yield_err = (sim_yield - obs_yield) ** 2
                
                # Check for LAI override
                if obs_lai is not None and pd.notna(obs_lai) and float(obs_lai) > 0:
                    sim_lai = df_yr["LAI"].max()
                    lai_err = 0.5 * ((sim_lai - float(obs_lai)) ** 2)
                    total_err_sq += (yield_err + lai_err)
                else:
                    total_err_sq += yield_err
                count += 1
                
            if count == 0:
                return float('inf')
                
            return np.sqrt(total_err_sq / count)
            
        except Exception as err:
            logger.error(f"Error evaluating candidate parameters {candidate_params}: {err}")
            return float('inf')
            
        finally:
            # Restore defaults in-place
            for k, v in saved_old.items():
                if v is not None:
                    DEFAULT_CROP_PARAMETERS[crop_type][k] = v
                    
    # Calculate original baseline RMSE
    original_rmse = evaluate_candidate(original_params)
    logger.info(f"Baseline crop calibration original RMSE: {original_rmse:.4f}")
    
    # 2. RUN OPTIMIZATION SEARCH
    best_params = original_params.copy()
    best_rmse = original_rmse
    
    # Total progress counting helper
    total_evals = 0
    current_eval = 0
    
    # Initialize optimization search bounds
    active_bounds = {k: list(v) for k, v in parameter_bounds.items()}
    
    if num_params == 1:
        # High-resolution 1D Grid Search (40 points)
        param_name = list(parameter_bounds.keys())[0]
        p_min, p_max = parameter_bounds[param_name]
        grid_points = np.linspace(p_min, p_max, 40)
        total_evals = len(grid_points)
        
        for p_val in grid_points:
            cand = {param_name: float(p_val)}
            rmse_val = evaluate_candidate(cand)
            if rmse_val < best_rmse:
                best_rmse = rmse_val
                best_params = cand.copy()
            current_eval += 1
            if progress_callback:
                progress_callback(current_eval, total_evals)
                
    elif num_params == 2:
        # Adaptive 2D Grid Search (16x16 = 256 divisions) followed by local refinement
        p_names = list(parameter_bounds.keys())
        p0_min, p0_max = parameter_bounds[p_names[0]]
        p1_min, p1_max = parameter_bounds[p_names[1]]
        
        grid_0 = np.linspace(p0_min, p0_max, 16)
        grid_1 = np.linspace(p1_min, p1_max, 16)
        total_evals = len(grid_0) * len(grid_1)
        
        for g0 in grid_0:
            for g1 in grid_1:
                cand = {p_names[0]: float(g0), p_names[1]: float(g1)}
                rmse_val = evaluate_candidate(cand)
                if rmse_val < best_rmse:
                    best_rmse = rmse_val
                    best_params = cand.copy()
                current_eval += 1
                if progress_callback:
                    progress_callback(current_eval, total_evals)
                    
        # Local refinement search (coordinate zoom around grid best)
        ref_bounds = {}
        for p_name in p_names:
            b_val = best_params[p_name]
            p_min, p_max = parameter_bounds[p_name]
            span = (p_max - p_min) * 0.15 # 15% window
            ref_bounds[p_name] = (max(p_min, b_val - span), min(p_max, b_val + span))
            
        # Execute 8x8 refined local search
        grid_ref0 = np.linspace(ref_bounds[p_names[0]][0], ref_bounds[p_names[0]][1], 8)
        grid_ref1 = np.linspace(ref_bounds[p_names[1]][0], ref_bounds[p_names[1]][1], 8)
        
        for r0 in grid_ref0:
            for r1 in grid_ref1:
                cand = {p_names[0]: float(r0), p_names[1]: float(r1)}
                rmse_val = evaluate_candidate(cand)
                if rmse_val < best_rmse:
                    best_rmse = rmse_val
                    best_params = cand.copy()
                    
    else:
        # Multi-variable Coordinate Descent with bound contraction
        p_names = list(parameter_bounds.keys())
        max_iter = 3
        steps_per_param = 15
        total_evals = max_iter * len(p_names) * steps_per_param
        
        # Initialize at current best or midpoint
        for p_name in p_names:
            p_min, p_max = parameter_bounds[p_name]
            best_params[p_name] = float(original_params[p_name] if original_params.get(p_name) is not None else (p_min + p_max) / 2.0)
            
        for iteration in range(max_iter):
            for p_idx, p_name in enumerate(p_names):
                p_min, p_max = active_bounds[p_name]
                grid_coords = np.linspace(p_min, p_max, steps_per_param)
                
                # Optimize this parameter coordinate while locking other variables
                local_best_val = best_params[p_name]
                for g_val in grid_coords:
                    cand = best_params.copy()
                    cand[p_name] = float(g_val)
                    
                    rmse_val = evaluate_candidate(cand)
                    if rmse_val < best_rmse:
                        best_rmse = rmse_val
                        best_params[p_name] = float(g_val)
                        local_best_val = float(g_val)
                    current_eval += 1
                    if progress_callback:
                        progress_callback(min(current_eval, total_evals), total_evals)
                
                # Bound contraction step: zoom in around the local best value
                span = (p_max - p_min) * 0.4  # Contract range by 40%
                active_bounds[p_name] = [
                    max(parameter_bounds[p_name][0], local_best_val - span),
                    min(parameter_bounds[p_name][1], local_best_val + span)
                ]
                
    logger.info(f"Calibration optimization completed. Best RMSE: {best_rmse:.4f} (Original: {original_rmse:.4f})")
    return best_params, original_rmse, best_rmse
