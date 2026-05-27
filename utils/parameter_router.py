import os
import json
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class CropParameterRouter:
    """
    Centralized, scalable parameter management system for the SSM-iCrop Platform.
    Allows dynamic loading, validation, and routing of crop physiological profiles.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the router with the path to the JSON database.
        """
        if db_path is None:
            # Default location relative to app root
            self.db_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "core", "crop_db.json")
            )
        else:
            self.db_path = db_path

    def _load_database(self) -> Dict[str, Any]:
        """
        Reads the underlying crop parameters JSON database.
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Crop database not found at absolute path: {self.db_path}")
            
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading crop parameter database: {e}")
            raise RuntimeError(f"Database ingestion failed: {e}")

    def list_available_crops(self) -> List[str]:
        """
        Returns a list of all supported crop profile names.
        """
        db = self._load_database()
        return [crop.capitalize() for crop in db.keys()]

    def get_profile_by_name(self, crop_name: str) -> Dict[str, Any]:
        """
        Fetches the exact parameter dictionary profile for a requested crop name.
        
        Parameters:
            crop_name (str): Case-insensitive name of the crop (e.g., "Maize", "Sorghum").
            
        Returns:
            Dict[str, Any]: The physiological parameters payload for the requested crop.
        """
        db = self._load_database()
        norm_name = str(crop_name).strip().lower()
        
        if norm_name not in db:
            supported = ", ".join([k.capitalize() for k in db.keys()])
            raise KeyError(
                f"Unsupported crop profile '{crop_name}' requested. "
                f"Currently supported crops in Database: [{supported}]."
            )
            
        profile = db[norm_name].copy()
        
        # Ensure backwards and forwards compatibility between alias mappings
        if "RUE_MAX" in profile and "IRUE" not in profile:
            profile["IRUE"] = profile["RUE_MAX"]
        elif "IRUE" in profile and "RUE_MAX" not in profile:
            profile["RUE_MAX"] = profile["IRUE"]
            
        return profile

    def validate_custom_parameters(self, custom_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitizes, checks ranges, and validates user-uploaded crop parameter coefficients.
        
        Parameters:
            custom_dict (dict): Raw dictionary parsed from an uploaded Excel or user input.
            
        Returns:
            Dict[str, Any]: Sanitized parameter dictionary if validation passes.
            
        Raises:
            ValueError: If a parameter violates logical biological bounds.
        """
        sanitized = {}
        
        # Mapping parameter synonyms if present in custom inputs
        alias_map = {
            "BaseTemp": "TBD",
            "OptTemp": "TP1D",
            "MaxTemp": "TCD",
            "RUE": "RUE_MAX",
            "IRUE": "RUE_MAX"
        }
        
        # Populate raw values into strict target keys
        for k, v in custom_dict.items():
            clean_k = k.strip()
            if clean_k in alias_map:
                target_k = alias_map[clean_k]
                sanitized[target_k] = v
            sanitized[clean_k] = v
            
        # 1. Validate Base Temperature (TBD)
        if "TBD" in sanitized:
            try:
                tbd_val = float(sanitized["TBD"])
                if tbd_val < 0.0:
                    raise ValueError("Base Temperature (TBD) cannot be negative.")
                if tbd_val > 25.0:
                    raise ValueError("Base Temperature (TBD) exceeds reasonable C4 crop limits (> 25°C).")
                sanitized["TBD"] = tbd_val
            except (ValueError, TypeError) as err:
                if isinstance(err, ValueError) and "reasonable" in str(err) or "negative" in str(err):
                    raise
                raise ValueError("Base Temperature (TBD) must be a numeric value.")
                
        # 2. Validate Maximum Radiation Use Efficiency (RUE_MAX)
        if "RUE_MAX" in sanitized:
            try:
                rue_val = float(sanitized["RUE_MAX"])
                # BOKU's reference Maize cultivar uses an active RUE of 3.5 g/MJ, and Sorghum uses 3.2 g/MJ.
                # Standard physiological models estimate RUE between 1.0 and 5.0 g/MJ.
                if not (1.0 <= rue_val <= 5.0):
                    raise ValueError(
                        f"Radiation Use Efficiency (RUE_MAX) of {rue_val} g/MJ falls outside "
                        f"logical agronomic limits (1.0 - 5.0 g/MJ)."
                    )
                sanitized["RUE_MAX"] = rue_val
                sanitized["IRUE"] = rue_val  # maintain engine compatibility
            except (ValueError, TypeError) as err:
                if isinstance(err, ValueError) and "agronomic" in str(err):
                    raise
                raise ValueError("RUE_MAX must be a numeric value.")
                
        # 3. Validate Cardinal Temperatures Coherence
        tbd_val = float(sanitized.get("TBD", 8.0))
        tp1d_val = float(sanitized.get("TP1D", 34.0))
        tp2d_val = float(sanitized.get("TP2D", 37.0))
        tcd_val = float(sanitized.get("TCD", 45.0))
        
        if not (tbd_val < tp1d_val <= tp2d_val < tcd_val):
            raise ValueError(
                f"Cardinal temperatures out of logical sequence. "
                f"Expected: TBD ({tbd_val}) < TP1D ({tp1d_val}) <= TP2D ({tp2d_val}) < TCD ({tcd_val})."
            )
            
        # 4. Validate Specific Leaf Area (SLA)
        if "SLA" in sanitized:
            try:
                sla_val = float(sanitized["SLA"])
                if not (0.005 <= sla_val <= 0.1):
                    raise ValueError(f"SLA of {sla_val} m²/g falls outside logical leaf-thickness limits (0.005 - 0.1 m²/g).")
                sanitized["SLA"] = sla_val
            except (ValueError, TypeError) as err:
                if isinstance(err, ValueError) and "thickness" in str(err):
                    raise
                raise ValueError("SLA must be a numeric value.")
                
        return sanitized
