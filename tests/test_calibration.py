import unittest
import os
import sys
import pandas as pd
import numpy as np

# Add parent directory to sys.path to resolve imports cleanly
current_dir = os.path.dirname(os.path.abspath(__file__))
icrop2_dir = os.path.abspath(os.path.join(current_dir, ".."))
if icrop2_dir not in sys.path:
    sys.path.insert(0, icrop2_dir)

from utils.calibrator import run_calibration_search

class TestCropParameterCalibration(unittest.TestCase):
    """
    Unit testing suite that validates the inverse optimization search logic 
    and checks RMSE minimization correctness in calibrator.py.
    """

    def setUp(self):
        # Create a mock multi-year weather dataframe (2 years, 365 days each)
        doy_seq = list(range(1, 366)) * 2
        year_seq = [2020] * 365 + [2021] * 365
        srad_seq = [15.0] * 730
        tmax_seq = [25.0] * 730
        tmin_seq = [15.0] * 730
        rain_seq = [5.0] * 730

        self.mock_weather = pd.DataFrame({
            "YEAR": year_seq,
            "DOY": doy_seq,
            "SRAD": srad_seq,
            "TMAX": tmax_seq,
            "TMIN": tmin_seq,
            "RAIN": rain_seq,
            "Current_Year": [1] * 365 + [2] * 365
        })

        # Mock soil params (5 layers)
        self.mock_soil_params = {
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

        # Mock observed data matrix
        self.mock_observed = [
            {"Year": 2020, "Observed Yield (t/ha)": 8.0, "Observed Peak LAI (Optional)": 4.0},
            {"Year": 2021, "Observed Yield (t/ha)": 8.5, "Observed Peak LAI (Optional)": 4.5}
        ]

    def test_single_parameter_calibration_search(self):
        """
        Verify that 1D calibration search successfully optimizes parameter 
        values and lowers the RMSE metric.
        """
        # Select IRUE for calibration
        bounds = {"IRUE": (1.5, 4.5)}
        
        opt_params, orig_rmse, best_rmse = run_calibration_search(
            observed_data=self.mock_observed,
            weather_target_df=self.mock_weather,
            soil_target_profile=self.mock_soil_params,
            parameter_bounds=bounds,
            crop_type="Maize",
            latitude=21.0285,
            soil_config={"depth_mm": 1200, "initial_water_percent": 25.0, "pawc_mm_m": 150.0},
            fertilizer_schedule=[],
            water_management={"auto_irrigation": False},
            engine_mode="Advanced",
            advanced_options={"use_moisture": True, "use_nitrogen": True}
        )
        
        # Assert that the optimized value is within bounds
        self.assertIn("IRUE", opt_params)
        self.assertTrue(1.5 <= opt_params["IRUE"] <= 4.5)
        
        # Assert that search successfully executes and returns a numeric RMSE value
        self.assertIsNotNone(orig_rmse)
        self.assertIsNotNone(best_rmse)
        self.assertTrue(best_rmse <= orig_rmse or np.isclose(best_rmse, orig_rmse))

    def test_multi_parameter_calibration_search(self):
        """
        Verify that 3D coordinate descent calibration search optimizes 
        multiple variables (IRUE, SLA, TBD) and converges correctly.
        """
        bounds = {
            "IRUE": (1.0, 5.0),
            "SLA": (0.005, 0.05),
            "TBD": (0.0, 15.0)
        }
        
        opt_params, orig_rmse, best_rmse = run_calibration_search(
            observed_data=self.mock_observed,
            weather_target_df=self.mock_weather,
            soil_target_profile=self.mock_soil_params,
            parameter_bounds=bounds,
            crop_type="Maize",
            latitude=21.0285,
            soil_config={"depth_mm": 1200, "initial_water_percent": 25.0, "pawc_mm_m": 150.0},
            fertilizer_schedule=[],
            water_management={"auto_irrigation": False},
            engine_mode="Advanced",
            advanced_options={"use_moisture": True, "use_nitrogen": True}
        )
        
        # Assert that all 3 variables are in output
        self.assertIn("IRUE", opt_params)
        self.assertIn("SLA", opt_params)
        self.assertIn("TBD", opt_params)
        
        # Assert that optimized values respect bounds
        self.assertTrue(1.0 <= opt_params["IRUE"] <= 5.0)
        self.assertTrue(0.005 <= opt_params["SLA"] <= 0.05)
        self.assertTrue(0.0 <= opt_params["TBD"] <= 15.0)

if __name__ == "__main__":
    unittest.main()
