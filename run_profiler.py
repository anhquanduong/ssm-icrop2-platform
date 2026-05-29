"""
BOKU SSM-iCrop Growth Platform - Performance Profiler Utility
==============================================================
Profiles the millisecond execution cost of the core SSMiCropEngine simulation loop
independent of the Streamlit server. Run directly from your local terminal:
  python run_profiler.py
"""
import sys
import os
import time
import cProfile
import pstats
import pandas as pd
import numpy as np

# Reconfigure stdout to force UTF-8 encoding on Windows to prevent UnicodeEncodeErrors when printing emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure the root directory is accessible for clean imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.model_engine import SSMiCropEngine

def generate_mock_weather(days=365) -> pd.DataFrame:
    """Generates climatologically consistent daily weather data."""
    dates = pd.date_range(start="2020-01-01", periods=days)
    weather_data = []
    for idx, d in enumerate(dates):
        doy = d.dayofyear
        year = d.year
        # Seasonal temperature cycle (summer peak)
        phase = 2 * np.pi * (doy - 100) / 365.0
        tmax = 22.0 + 8.0 * np.sin(phase) + np.random.uniform(-2, 2)
        tmin = 10.0 + 6.0 * np.sin(phase) + np.random.uniform(-1, 1)
        srad = 16.0 + 8.0 * np.sin(2 * np.pi * (doy - 80) / 365.0) + np.random.uniform(-2, 2)
        rain = 0.0
        if np.random.random() < 0.20:
            rain = round(np.random.uniform(1.0, 15.0), 1)
            
        weather_data.append({
            "YEAR": year,
            "DOY": doy,
            "TMAX": round(tmax, 1),
            "TMIN": round(tmin, 1),
            "SRAD": round(max(0.1, srad), 2),
            "RAIN": rain
        })
    return pd.DataFrame(weather_data)

def profile_simulation():
    print("=================================================================")
    print("🚀 Initializing iCrop v2 Offline Performance Profiler Core...")
    print("=================================================================")
    
    # 1. Prepare inputs
    print("⚙️ Ingesting mock 1-year meteorological matrix...")
    weather_df = generate_mock_weather(365)
    
    soil_params = {
        "NLYER": 5,
        "LDRAIN": 4,
        "SALB": 0.13,
        "U": 6.0,
        "CN": 75.0,
        "DLYER": [150.0, 150.0, 300.0, 300.0, 300.0],
        "SAT": [0.45, 0.43, 0.41, 0.41, 0.40],
        "DUL": [0.35, 0.33, 0.31, 0.31, 0.30],
        "EXTR": [0.15, 0.13, 0.11, 0.11, 0.10],
        "DRAINF": [0.4, 0.4, 0.4, 0.4, 0.4],
        "MAI": [1.0, 1.0, 1.0, 1.0, 1.0]
    }
    
    soil_config = {
        "depth_mm": 1200.0,
        "initial_water_percent": 25.0,
        "pawc_mm_m": 150.0,
        "som_percent": 2.5
    }
    
    fertilizer_schedule = [
        {"doy": 120, "n": 120.0, "p": 40.0, "k": 40.0, "method": "Broadcast"},
        {"doy": 180, "n": 80.0, "p": 0.0, "k": 0.0, "method": "Banding"}
    ]
    
    water_management = {
        "auto_irrigation": True,
        "irrigation": [],
        "drainage": []
    }
    
    advanced_options = {
        "use_vpd": True,
        "use_leaching": True,
        "use_root_growth": True,
        "use_heat_shock": True
    }
    
    # 2. Instantiate core engine
    print("🌱 Initializing crop parameters (Crop Type: Maize)...")
    engine = SSMiCropEngine(
        weather_df=weather_df,
        latitude=48.2830, # Gerasdorf, Austria coordinates
        soil_params=soil_params,
        soil_config=soil_config,
        fertilizer_schedule=fertilizer_schedule,
        water_management=water_management,
        mode="Advanced",
        advanced_options=advanced_options,
        sim_years=1
    )
    
    # 3. Enable performance diagnostic container
    print("🔬 Executing standard profile run...")
    profiler = cProfile.Profile()
    
    start_time = time.perf_counter()
    profiler.enable()
    
    # Run simulation computational loop
    df_results = engine.run_simulation(crop_type="Maize", pden=8.0, vpdf=1.0)
    
    profiler.disable()
    end_time = time.perf_counter()
    
    duration_ms = (end_time - start_time) * 1000.0
    print(f"\n✅ Simulation completed in {duration_ms:.2f} ms!")
    print(f"📊 Captured {len(df_results)} simulated timeline records.")
    
    # 4. Generate statistics reports
    print("\n=================================================================")
    print("            FUNCTION PERFORMANCE PROFILES (Cumulative Time)      ")
    print("=================================================================")
    stats = pstats.Stats(profiler)
    stats.strip_dirs().sort_stats('cumulative').print_stats(15)

if __name__ == "__main__":
    profile_simulation()
