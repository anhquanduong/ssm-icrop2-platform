import os
import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Fallback defaults for soil parameters if GEE and SoilGrids APIs fail
CLAY_LOAM_DEFAULT = {
    "Max_Root_Depth": 1200,          # Standard crop rooting depth limit (mm)
    "Soil_Water_Capacity": 180.0,    # Plant Available Water Capacity (PAWC) in mm (1200mm * 0.15 vol)
    "clay_fraction": 0.28,           # Bulk clay content
    "sand_fraction": 0.32,           # Bulk sand content
    "organic_matter": 0.025,         # Soil organic matter fraction
    "bulk_density": 1.35,            # Soil bulk density (g/cm³)
    "source": "BOKU baseline clay-loam preset (Fallback)"
}

class SpatialSoilEstimator:
    """
    Geospatial Soil Mapping Module that extracts localized soil properties (PAWC, Root Depth limits)
    from coordinates using Google Earth Engine or the open-source ISRIC SoilGrids API fallback.
    """

    def __init__(self, use_gee: bool = False):
        """
        Initialize the spatial soil estimator.
        
        Parameters:
            use_gee (bool): If True, attempts to initialize and use GEE (requires private credentials).
                            If False, routes to the token-free SoilGrids REST API.
        """
        self.use_gee = use_gee
        self.gee_initialized = False
        
        if self.use_gee:
            try:
                import ee
                logger.info("Attempting GEE Authentication initialization...")
                ee.Initialize()
                self.gee_initialized = True
                logger.info("Google Earth Engine Python API successfully initialized!")
            except Exception as e:
                logger.warning(
                    f"GEE initialization failed: {e}. "
                    f"spatial_helper.py will route queries to the open-source SoilGrids REST API."
                )
                self.gee_initialized = False

    def query_soilgrids_api(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Queries the ISRIC SoilGrids v2.0 Global Soil REST API to extract localized clay, sand,
        bulk density, and organic carbon fractions, calculating physical water capacity.
        
        Parameters:
            lat (float): Coordinate Latitude.
            lon (float): Coordinate Longitude.
            
        Returns:
            Dict[str, Any]: Extracted physical soil parameters.
        """
        # SoilGrids REST API handles query points globally at 250m resolution
        url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
        params = {
            "lon": lon,
            "lat": lat,
            "property": ["clay", "sand", "bdod", "soc"],
            "depth": ["0-5cm", "15-30cm", "60-100cm"],
            "value": "mean"
        }
        
        try:
            logger.info(f"Querying ISRIC SoilGrids REST API for coordinates: lat={lat}, lon={lon}...")
            response = requests.get(url, params=params, timeout=12)
            
            # Check for ocean / NoData areas
            if response.status_code == 400 or response.status_code == 500:
                raise ValueError(
                    f"SoilGrids server rejected request (status {response.status_code}). "
                    f"Check if coordinate is over ocean or out of land boundaries."
                )
                
            response.raise_for_status()
            data = response.json()
            
            # Verify if coordinates returned land data layers
            properties = data.get("properties", {})
            layers = properties.get("layers", [])
            
            if not layers:
                raise ValueError("NoData pixel: target coordinate lies in ocean or non-mapped territory.")
                
            # Parse parameters by averaging layers
            extracted = {}
            for layer in layers:
                name = layer.get("name")
                depths = layer.get("depths", [])
                
                # Gather mean values across depths
                vals = []
                for d in depths:
                    val_data = d.get("values", {})
                    mean_val = val_data.get("mean")
                    if mean_val is not None:
                        vals.append(mean_val)
                        
                if vals:
                    # SoilGrids returns scaled integers:
                    # - Clay & Sand: g/kg (divide by 1000 to get decimal fraction)
                    # - Bulk density (bdod): cg/cm³ (divide by 100 to get g/cm³)
                    # - Soil Organic Carbon (soc): dg/kg (divide by 100 to get percentage)
                    avg_val = sum(vals) / len(vals)
                    extracted[name] = avg_val
                    
            if not extracted:
                raise ValueError("Incomplete data returned from SoilGrids layers.")
                
            # Process fractions
            clay_frac = (extracted.get("clay", 280) / 1000.0)
            sand_frac = (extracted.get("sand", 320) / 1000.0)
            bulk_density = (extracted.get("bdod", 135) / 100.0)
            soc_perc = (extracted.get("soc", 250) / 10.0) / 10.0  # % organic carbon
            organic_matter = soc_perc * 1.724 / 100.0  # organic matter fraction
            
            # Calculate Plant Available Water Capacity (PAWC) using Rawls-Saxton pedotransfer functions:
            # - Permanent Wilting Point (θ_pwp) = 0.085 - 0.39 * Sand + 0.44 * Clay + 0.063 * OM
            # - Field Capacity (θ_fc) = 0.25 - 0.42 * Sand + 0.52 * Clay + 0.08 * OM
            # - Available water fraction = θ_fc - θ_pwp
            theta_pwp = 0.085 - 0.39 * sand_frac + 0.44 * clay_frac + 0.063 * organic_matter
            theta_fc = 0.25 - 0.42 * sand_frac + 0.52 * clay_frac + 0.08 * organic_matter
            
            # Bounds checking for volumetric capacity
            awc_volumetric = max(0.08, min(0.22, theta_fc - theta_pwp))
            
            max_root_depth = 1200 # Standard crop root depth (mm)
            pawc_total_mm = round(max_root_depth * awc_volumetric, 2)
            
            logger.info("SoilGrids API query parsed successfully. Calculated AWC = %.3f vol" % awc_volumetric)
            
            return {
                "Max_Root_Depth": max_root_depth,
                "Soil_Water_Capacity": pawc_total_mm,
                "clay_fraction": round(clay_frac, 3),
                "sand_fraction": round(sand_frac, 3),
                "organic_matter": round(organic_matter, 4),
                "bulk_density": round(bulk_density, 2),
                "source": "ISRIC SoilGrids 250m Pixel Footprint (Dynamic)"
            }
            
        except Exception as e:
            logger.error(f"SoilGrids extraction failed: {e}. Reverting to standard baseline.")
            raise RuntimeError(f"GIS Soil Extraction failed: {e}")

    def query_gee_api(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Query standard global soil datasets (OpenLandMap or USDA) from GEE.
        Only executed if GEE was successfully initialized.
        """
        import ee
        try:
            point = ee.Geometry.Point([lon, lat])
            
            # Load OpenLandMap Clay Content image
            # Extracted at standard depth layer 0-10cm
            img_clay = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select("b0")
            img_sand = ee.Image("OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02").select("b0")
            
            # Reduce region to get pixel value
            clay_val = img_clay.reduceRegion(ee.Reducer.mean(), point, 250).get("b0").getInfo()
            sand_val = img_sand.reduceRegion(ee.Reducer.mean(), point, 250).get("b0").getInfo()
            
            if clay_val is None or sand_val is None:
                raise ValueError("GEE coordinate reducer returned empty values (pixel in ocean/non-land).")
                
            clay_frac = float(clay_val) / 100.0
            sand_frac = float(sand_val) / 100.0
            
            # Estimate AWC
            theta_pwp = 0.085 - 0.39 * sand_frac + 0.44 * clay_frac
            theta_fc = 0.25 - 0.42 * sand_frac + 0.52 * clay_frac
            awc_vol = max(0.08, min(0.22, theta_fc - theta_pwp))
            
            max_root_depth = 1200
            pawc = round(max_root_depth * awc_vol, 2)
            
            return {
                "Max_Root_Depth": max_root_depth,
                "Soil_Water_Capacity": pawc,
                "clay_fraction": round(clay_frac, 3),
                "sand_fraction": round(sand_frac, 3),
                "organic_matter": 0.025,
                "bulk_density": 1.35,
                "source": "GEE OpenLandMap 250m Reducer (Dynamic)"
            }
        except Exception as e:
            logger.error(f"GEE Reducer failed: {e}")
            raise RuntimeError(f"GEE Reducer failed: {e}")

    def get_soil_profile(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Orchestrates soil query across cloud API pipelines, returning standard physical defaults
        upon coordinate errors or NoData boundaries.
        
        Parameters:
            lat (float): Coordinate Latitude.
            lon (float): Coordinate Longitude.
            
        Returns:
            Dict[str, Any]: Plant-available water capacity dictionary.
        """
        # Validate coordinates bounds
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Geographic coordinates out of bounds: lat={lat}, lon={lon}.")
            
        # 1. Attempt GEE if enabled and authenticated
        if self.use_gee and self.gee_initialized:
            try:
                return self.query_gee_api(lat, lon)
            except Exception:
                logger.warning("GEE pipeline failed. Swapping to SoilGrids API...")
                
        # 2. Attempt ISRIC SoilGrids global REST API fallback
        try:
            return self.query_soilgrids_api(lat, lon)
        except Exception as err:
            logger.warning(
                f"Dynamic cloud soil retrieval failed ({err}). "
                f"Falling back to BOKU baseline clay-loam preset."
            )
            # Graceful fallback return
            return CLAY_LOAM_DEFAULT.copy()
