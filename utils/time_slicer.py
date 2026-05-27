import pandas as pd
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class WeatherTimeSlicer:
    """
    Agricultural time-slicing module to scan available years, isolate a single 
    sowing window, and manage rollover transitions seamlessly.
    """
    @staticmethod
    def get_available_years(weather_df: pd.DataFrame) -> List[int]:
        """
        Inspects the 'YEAR' column of the unified weather dataframe,
        extracting and returning a sorted list of unique available calendar years.
        """
        if weather_df is None or weather_df.empty:
            return []
            
        # Standardize columns to uppercase to avoid case issues
        df_cols = [str(c).upper() for c in weather_df.columns]
        
        # Determine year column
        year_col = None
        for col in weather_df.columns:
            if str(col).upper() in ['YEAR', 'YEARS', 'YR']:
                year_col = col
                break
                
        if year_col:
            try:
                unique_years = weather_df[year_col].dropna().unique()
                sorted_years = sorted([int(y) for y in unique_years])
                return sorted_years
            except Exception as e:
                logger.error(f"Error parsing unique years: {e}")
                
        # If no year column, check if there's any datetime or fallback to current year
        if 'TIME' in df_cols or 'DATE' in df_cols:
            try:
                col_name = 'TIME' if 'TIME' in df_cols else 'DATE'
                # Find matching case
                actual_col = [c for c in weather_df.columns if str(c).upper() == col_name][0]
                years = pd.to_datetime(weather_df[actual_col]).dt.year.unique()
                return sorted([int(y) for y in years])
            except Exception:
                pass
                
        # Fallback default
        return [2020]

    @staticmethod
    def slice_crop_season(
        weather_df: pd.DataFrame, 
        target_year: int, 
        sowing_doy: int, 
        simulation_duration: int = 150
    ) -> pd.DataFrame:
        """
        Slices the unified weather dataframe to isolate a single crop growth cycle.
        
        Parameters:
            weather_df (pd.DataFrame): Normalized daily meteorological dataframe.
            target_year (int): Calendar year of planting.
            sowing_doy (int): Sowing Day of Year (DOY) index (1 to 365).
            simulation_duration (int): Number of daily rows to slice (default 150 days).
            
        Returns:
            pd.DataFrame: A cleanly isolated crop season matrix of length `simulation_duration`.
        """
        if weather_df is None or weather_df.empty:
            raise ValueError("Input weather dataframe is empty or invalid.")
            
        # Ensure chronological ordering
        df = weather_df.copy()
        
        # Standardize headers for lookup
        df.columns = [str(c).upper() for c in df.columns]
        
        # Sort chronologically if YEAR and DOY are present
        if 'YEAR' in df.columns and 'DOY' in df.columns:
            df = df.sort_values(by=['YEAR', 'DOY']).reset_index(drop=True)
            
            # Find the starting index matching target_year and sowing_doy
            start_row = df[(df['YEAR'] == target_year) & (df['DOY'] == sowing_doy)]
            
            if start_row.empty:
                # Fallback: Find the closest row in that target year
                start_row = df[(df['YEAR'] == target_year) & (df['DOY'] >= sowing_doy)]
                if start_row.empty:
                    # Second fallback: just take the first row of target_year
                    start_row = df[df['YEAR'] == target_year]
                    
            if not start_row.empty:
                start_idx = start_row.index[0]
                sliced_df = df.iloc[start_idx : start_idx + simulation_duration].copy().reset_index(drop=True)
                
                # Check if the sliced dataframe has enough data rows
                if len(sliced_df) < simulation_duration:
                    logger.warning(
                        f"Sliced crop season only contains {len(sliced_df)} days of data "
                        f"(requested {simulation_duration}). Sowing date may be near the end of the dataset."
                    )
                return sliced_df
                
        # Fallback for datasets without YEAR column: slice strictly by index or DOY
        if 'DOY' in df.columns:
            start_row = df[df['DOY'] == sowing_doy]
            if not start_row.empty:
                start_idx = start_row.index[0]
                return df.iloc[start_idx : start_idx + simulation_duration].copy().reset_index(drop=True)
                
        # Hard fallback: slice first duration rows
        return df.iloc[:simulation_duration].copy().reset_index(drop=True)
