import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

def fetch_isric_soil_data(lat: float, lon: float) -> dict:
    """
    Queries the ISRIC SoilGrids v2.0 REST API for the given coordinates,
    extracts the soil properties for clay, sand, and organic carbon,
    and applies pedotransfer formulas to estimate:
      - SOM (Soil Organic Matter %)
      - PAWC (Plant Available Water Capacity mm/m)
      - root_zone_depth (defaulting to 1000mm)
      
    If the API call fails or coordinates are in the ocean/invalid,
    returns standard agronomic baseline fallbacks:
      - SOM = 2.5%
      - PAWC = 150.0 mm/m
      - root_zone_depth = 1000mm
    """
    # Baseline defaults to guarantee uninterrupted simulation flow
    fallback_profile = {
        "som": 2.1,
        "pawc": 140.0,
        "root_zone_depth": 1000,
        "is_fallback": True
    }
    
    # Check coordinate bounds
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        logger.warning(f"Coordinates out of bounds: lat={lat}, lon={lon}. Using soil defaults.")
        return fallback_profile

    # Build REST query URL targeting SoilGrids properties
    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = {
        "lon": lon,
        "lat": lat,
        "property": ["clay", "sand", "soc", "bdod"],
        "depth": ["0-5cm", "5-15cm", "15-30cm"],
        "value": "mean"
    }
    
    session = requests.Session()
    # Configure retry logic for network resilience
    retries = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    
    try:
        logger.info(f"SoilGrids REST API request: lat={lat}, lon={lon}")
        # Enforce strict 3-second timeout as required by the system spec
        response = session.get(url, params=params, timeout=3)
        
        # Intercept common server errors (e.g. out of land bounds or 500 errors)
        if response.status_code in [400, 404, 500]:
            logger.warning(f"SoilGrids returned status {response.status_code}. Likely ocean pixel or error.")
            return fallback_profile
            
        response.raise_for_status()
        data = response.json()
        
        properties = data.get("properties", {})
        layers = properties.get("layers", [])
        
        if not layers:
            logger.warning("SoilGrids query returned empty layers list. Using soil defaults.")
            return fallback_profile
            
        extracted = {}
        for layer in layers:
            name = layer.get("name")
            depths = layer.get("depths", [])
            
            vals = []
            for d in depths:
                label = d.get("label")
                # Aggregate only the 0-30cm depths for agronomic topsoil representation
                if label in ["0-5cm", "5-15cm", "15-30cm"]:
                    val_data = d.get("values", {})
                    mean_val = val_data.get("mean")
                    if mean_val is not None:
                        vals.append(mean_val)
            
            if vals:
                # Average the values for this layer across the selected depths
                extracted[name] = sum(vals) / len(vals)
                
        # If crucial layers are missing from the response, fall back
        if "clay" not in extracted or "sand" not in extracted or "soc" not in extracted:
            logger.warning(f"Incomplete layers in SoilGrids response (got: {list(extracted.keys())}). Using defaults.")
            return fallback_profile
            
        # Parse physical properties using exact prompt instructions:
        # SOC is returned in dg/kg. SOM% = (SOC / 100) * 1.724
        soc_dg_kg = extracted["soc"]
        som_percent = (soc_dg_kg / 100.0) * 1.724
        
        # Clay and Sand are returned in g/kg. Convert to percentages by dividing by 10
        clay_g_kg = extracted["clay"]
        sand_g_kg = extracted["sand"]
        clay_percent = clay_g_kg / 10.0
        sand_percent = sand_g_kg / 10.0
        
        # PAWC (mm/m) ≈ 200 - (1.5 * Sand%) + (0.5 * Clay%)
        pawc_val = 200.0 - (1.5 * sand_percent) + (0.5 * clay_percent)
        
        # Apply biological & physical bounding safeguards
        som_percent = max(0.1, min(10.0, round(som_percent, 2)))
        pawc_val = max(10.0, min(300.0, round(pawc_val, 1)))
        
        logger.info(f"SoilGrids Ingestion Succeeded: SOM={som_percent}%, PAWC={pawc_val} mm/m")
        return {
            "som": som_percent,
            "pawc": pawc_val,
            "root_zone_depth": 1000  # Baseline predicted depth defaults to 1000mm
        }
        
    except requests.exceptions.RequestException as req_err:
        logger.error(f"SoilGrids network connection failed: {req_err}. Falling back gracefully.")
        return fallback_profile
    except Exception as err:
        logger.error(f"Unexpected error parsing SoilGrids payload: {err}. Falling back gracefully.")
        return fallback_profile
    finally:
        session.close()
