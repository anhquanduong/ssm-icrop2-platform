import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from datetime import datetime, date, timedelta
import logging
from typing import Dict, Any, Optional
import streamlit as st

logger = logging.getLogger(__name__)

@st.cache_data(ttl=86400)
def fetch_openmeteo_weather(lat: float, lon: float, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    """
    Intelligently queries the Open-Meteo Historical Archive API depending on the requested season range,
    incorporating a resilient connection pooling adapter with progressive backoff retries.
    Returns a standardized Pandas DataFrame formatted exactly for the SSMiCropEngine.
    
    Parameters:
        lat (float): Sowing region latitude.
        lon (float): Sowing region longitude.
        start_date (str): Sowing date in 'YYYY-MM-DD' format.
        end_date (str): Harvest date in 'YYYY-MM-DD' format.
        
    Returns:
        Optional[pd.DataFrame]: Cleaned daily meteorological arrays with columns:
                                [YEAR, DOY, SRAD, TMAX, TMIN, RAIN]
                                Returns None during recoverable network failures.
    """
    # 1. Parse date inputs
    try:
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as val_err:
        raise ValueError(f"Date formatting invalid. Dates must be in YYYY-MM-DD format. Error: {val_err}")
        
    if s_date > e_date:
        raise ValueError(f"Sowing start date ({start_date}) cannot occur after harvest end date ({end_date}).")
        
    # Explicitly center endpoint on stable Historical Archive API cluster
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,precipitation_sum",
        "timezone": "auto"
    }
    
    logger.info(f"Resilient Ingestion Engine contacting Open-Meteo Historical Archive for lat={lat}, lon={lon} ({start_date} to {end_date})...")
    
    # 2. Build resilient HTTP connection pool and retry adapters
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False  # To allow status codes to bubble up for custom handlers
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    try:
        # Enforce strict 10 seconds connection/read timeout
        response = session.get(url, params=params, timeout=10)
        
        # Check for NoData / invalid locations (e.g. coordinates in middle of oceans)
        if response.status_code == 400:
            err_msg = response.json().get("reason", "Unknown request constraint error.")
            raise ValueError(f"Open-Meteo API rejected request: {err_msg} Check if coordinate falls in NoData grid or if dates are in the future.")
            
        response.raise_for_status()
        data = response.json()
        
        if "daily" not in data or not data["daily"].get("time"):
            raise ValueError("Empty or incomplete daily array returned from Open-Meteo.")
            
        daily = data["daily"]
        df = pd.DataFrame(daily)
        
        # 3. Clean and map parameters
        df["time"] = pd.to_datetime(df["time"])
        
        if df.empty:
            raise ValueError(f"No weather records fall within requested bounds: {start_date} to {end_date}.")
            
        # Calculate Day of Year (DOY) and YEAR
        df["DOY"] = df["time"].dt.dayofyear
        df["YEAR"] = df["time"].dt.year
        
        # Map raw variables to strict SSM-iCrop engine variable names
        # TMAX: Max Temp (°C), TMIN: Min Temp (°C), SRAD: Solar Radiation (MJ/m²/day), RAIN: Precip (mm)
        df = df.rename(columns={
            "temperature_2m_max": "TMAX",
            "temperature_2m_min": "TMIN",
            "shortwave_radiation_sum": "SRAD",
            "precipitation_sum": "RAIN"
        })
        
        # Verify required columns are populated and non-null
        required_cols = ["YEAR", "DOY", "TMAX", "TMIN", "SRAD", "RAIN"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Failed to extract parameter '{col}' from Open-Meteo response.")
            # Fill missing entries if any
            if df[col].isnull().any():
                df[col] = df[col].ffill().bfill()

        # -----------------------------------------------------------------
        # SRAD VALIDATION — Open-Meteo returns shortwave_radiation_sum in
        # MJ/m²/day natively. Log a warning if the range looks suspicious
        # (e.g. future API changes could silently switch units).
        # Physical valid range: 0 – 50 MJ/m²/day.
        # -----------------------------------------------------------------
        srad_p95 = df["SRAD"].quantile(0.95)
        if srad_p95 > 100.0:
            # Values >> 50 MJ suggest Wh/m²/day or kJ/m²/day was returned
            logger.warning(
                f"Open-Meteo SRAD 95th-pct = {srad_p95:.1f} — "
                f"suspiciously high. Applying kJ→MJ correction (÷1000)."
            )
            df["SRAD"] = df["SRAD"] / 1000.0
        df["SRAD"] = df["SRAD"].clip(lower=0.0, upper=50.0)
        logger.info(
            f"SRAD range validated: min={df['SRAD'].min():.2f}, "
            f"max={df['SRAD'].max():.2f} MJ/m²/day."
        )

        # Order columns strictly
        final_df = df[required_cols].copy()
        logger.info(f"Meteorological array loaded successfully. Captured {len(final_df)} days.")
        return final_df
        
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as net_err:
        logger.error(f"Network volatility detected during Open-Meteo query: {net_err}")
        # Safe warning display without crashing application thread
        st.warning(f"⚠️ Weather API Connection timeout/failure: {str(net_err)}. Resiliently falling back...")
        return None
    except requests.exceptions.RequestException as http_err:
        logger.error(f"HTTP connection failed for Open-Meteo: {http_err}")
        status_code = getattr(http_err.response, 'status_code', None) if http_err.response is not None else None
        err_msg = f"HTTP {status_code} Error" if status_code else "network timeout"
        raise ConnectionError(f"Could not connect to weather API servers ({err_msg}).")
    except Exception as e:
        logger.error(f"Error parsing meteorological response: {e}")
        raise RuntimeError(f"Weather Ingestion failed: {str(e)}")

def get_fallback_weather(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Generates a high-quality, climatologically consistent default daily weather dataset
    used as a resilient fallback if the Open-Meteo APIs are offline or return NoData.
    
    Parameters:
        start_date (str): Sowing date in 'YYYY-MM-DD' format.
        end_date (str): Harvest date in 'YYYY-MM-DD' format.
        
    Returns:
        pd.DataFrame: Daily baseline weather dataset with columns [YEAR, DOY, TMAX, TMIN, SRAD, RAIN]
    """
    import math
    import random
    
    s_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    e_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    date_range = pd.date_range(start=s_date, end=e_date)
    fallback_data = []
    
    for d in date_range:
        doy = d.dayofyear
        year = d.year
        
        # Seasonally-varying, mid-latitude baseline temperature profile (approx. summer peak)
        season_phase = 2 * math.pi * (doy - 100) / 365.0
        
        tmax = 22.0 + 8.0 * math.sin(season_phase)   # Range: 14°C to 30°C
        tmin = 10.0 + 6.0 * math.sin(season_phase)   # Range: 4°C to 16°C
        srad = 16.0 + 8.0 * math.sin(2 * math.pi * (doy - 80) / 365.0) # Range: 8 to 24 MJ/m²/day
        
        # Occasional dynamic rain event (approx 22% probability, seed-pinned for determinism)
        random.seed(doy)
        rain = 0.0
        if random.random() < 0.22:
            rain = round(random.uniform(1.0, 18.0), 1)
            
        fallback_data.append({
            "YEAR": year,
            "DOY": doy,
            "TMAX": round(tmax, 1),
            "TMIN": round(tmin, 1),
            "SRAD": round(srad, 2),
            "RAIN": rain
        })
        
    final_df = pd.DataFrame(fallback_data)
    logger.info(f"Generated default weather baseline of {len(final_df)} days (Resilient Fallback).")
    return final_df
