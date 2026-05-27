import unittest
import os
import sys
import pandas as pd
import numpy as np

# Add icrop2 folder to sys.path to resolve imports cleanly
current_dir = os.path.dirname(os.path.abspath(__file__))
icrop2_dir = os.path.abspath(os.path.join(current_dir, ".."))
if icrop2_dir not in sys.path:
    sys.path.insert(0, icrop2_dir)

from core.model_engine import SSMiCropEngine

class TestMultiYearSimulation(unittest.TestCase):
    """
    Asserts correct behavior of the continuous multi-year simulation engine loop.
    """

    def setUp(self):
        # Create a mock multi-year weather dataframe (2 years, 365 days each)
        doy_seq = list(range(1, 366)) * 2
        year_seq = [2020] * 365 + [2021] * 365
        srad_seq = [15.0] * 730
        tmax_seq = [25.0] * 730
        tmin_seq = [15.0] * 730
        rain_seq = [5.0] * 730 # light rain daily
        
        self.mock_weather = pd.DataFrame({
            "YEAR": year_seq,
            "DOY": doy_seq,
            "SRAD": srad_seq,
            "TMAX": tmax_seq,
            "TMIN": tmin_seq,
            "RAIN": rain_seq
        })

    def test_continuous_carry_over(self):
        """
        Verify that soil water and nitrogen levels are carried over boundary transitions
        rather than resetting to baseline parameters on Day 1 of Year 2.
        """
        engine = SSMiCropEngine(
            weather_df=self.mock_weather,
            latitude=21.0285,
            sim_years=2
        )
        
        # Run standard Advanced simulation for Maize
        results = engine.run_simulation(crop_type="Maize")
        
        # Check that we got 730 rows of simulation data
        self.assertEqual(len(results), 730)
        
        # Get values at the exact boundary: Year 1 End (Day 365) and Year 2 Start (Day 366)
        row_y1_end = results.iloc[364]
        row_y2_start = results.iloc[365]
        
        # Assert that the year increments correctly
        self.assertEqual(row_y1_end["Current_Year"], 1)
        self.assertEqual(row_y2_start["Current_Year"], 2)
        
        # Assert that the simulation timeline days increments continuously
        self.assertEqual(row_y1_end["Simulation_Timeline_Days"], 365)
        self.assertEqual(row_y2_start["Simulation_Timeline_Days"], 366)
        
        # Assert that Soil Water follows standard mass balance without baseline resets
        expected_sw = row_y1_end["SOIL_WATER"] + row_y2_start["RAIN"] + row_y2_start["IRGW"] - (
            row_y2_start["DRAIN"] + row_y2_start["RUNOF"] + row_y2_start["SEVP"] + row_y2_start["TR"]
        )
        self.assertAlmostEqual(row_y2_start["SOIL_WATER"], expected_sw, places=2)
        
        # Assert that Soil Nitrogen carries over exactly from Year 1 end
        self.assertEqual(row_y2_start["SOIL_N"], row_y1_end["SOIL_N"])

if __name__ == "__main__":
    unittest.main()
