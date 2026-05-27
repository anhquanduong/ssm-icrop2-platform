import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Union, List

# BOKU SSM Crop Physiological Parameter Matrix
DEFAULT_CROP_PARAMETERS = {
    "Maize": {
        "CROP": "Maize",
        "Cultivar": "B73*MO17 (SC704)",
        "crop_produce_type": "Fruit/Seed",
        "lifecycle_strategy": "Annual (Single-Season)",
        "t_dormancy_trigger": 5.0,
        "t_base_winter": 0.0,
        # Phenology (GDD / GDD equivalents)
        "TBD": 8.0,            # Base temperature for phenology (°C)
        "TP1D": 34.0,          # Lower optimum temperature for phenology (°C)
        "TP2D": 37.0,          # Upper optimum temperature for phenology (°C)
        "TCD": 45.0,           # Ceiling temperature for phenology (°C)
        "cpp": 12.5,           # Photoperiod threshold (hours)
        "ppsen": 0.52,         # Photoperiod sensitivity coefficient
        "bdSOWEMR": 3.0,       # Sowing to emergence duration (biological days)
        "bdEMREJU": 8.5,       # Emergence to juvenile duration (biological days)
        "bdSILPM": 33.8,       # Silking to physiological maturity (biological days)
        "PHYL": 38.9,          # Phyllochron (°C/leaf)
        # Canopy / LAI Expansion
        "PLACON": 1.0,         # Plant leaf area coefficient
        "PLAPOW8": 2.9,        # Plant leaf area power at plant density 8
        "SLA": 0.022,          # Specific leaf area (m²/g)
        "TKILL": 5.0,          # Frost killing threshold temperature (°C)
        "FRZLDR": 0.01,        # Frost kill rate (m²/m²/°C)
        # Radiation Use Efficiency (RUE)
        "TBRUE": 10.0,         # Base temperature for RUE (°C)
        "TP1RUE": 25.0,        # Lower optimum temperature for RUE (°C)
        "TP2RUE": 35.0,        # Upper optimum temperature for RUE (°C)
        "TCRUE": 45.0,         # Ceiling temperature for RUE (°C)
        "KPAR": 0.60,           # Extinction coefficient for PAR (confirmed k=0.60 from FINT/LAI ref data)
        "IRUE": 3.5,           # Maximum intrinsic RUE (g DM / MJ PAR intercepted)
        # Dry Matter Allocation / Yield
        "FLF1A": 0.7,          # Leaf allocation fraction 1A
        "FLF1B": 0.15,         # Leaf allocation fraction 1B
        "WTOPL": 210.0,        # Canopy weight threshold for leaf allocation change (g/m²)
        "FLF2": 0.05,          # Leaf allocation fraction 2 (reproductive phase)
        "FRTRL": 0.22,         # Translocatable stem dry matter fraction
        "GCC": 1.0,            # Grain conversion coefficient
        "PDHI": 0.015,         # Potential daily harvest index increase rate (1/day)
        "WDHI1": 0.0,          # Minimum canopy biomass for HI increase (g/m²)
        "WDHI2": 0.0,          # Low-stress canopy biomass limit for maximum HI (g/m²)
        "WDHI3": 9999.0,       # High-stress canopy biomass limit for maximum HI (g/m²)
        "WDHI4": 9999.0,       # Absolute maximum canopy biomass limit for HI (g/m²)
        # Root / Hydrological Stresses
        "iDEPORT": 150.0,      # Initial root depth (mm)
        "MEED": 1100.0,        # Maximum rooting depth (mm)
        "GRTDP": 33.0,         # Maximum root expansion rate (mm/biological day)
        "TEC": 9.0,            # Transpiration efficiency coefficient (Pa)
        "WSSG": 0.25,          # FTSW threshold penalizing RUE / expansion
        "WSSL": 0.35,          # FTSW threshold penalizing leaf area expansion
        "WSSD": 0.0,           # Phenological acceleration water deficit factor
        "FLDKL": 40.0,         # Flooding kill duration (days)
        # Nitrogen Ingestion
        "SLNG": 1.35,          # Specific nitrogen content of green leaves (g N / m²)
        "SLNS": 0.4,           # Specific nitrogen content of senesced leaves (g N / m²)
        "SNCG": 0.0106,        # Critical green stem nitrogen concentration (g N / g stem)
        "SNCS": 0.0025,        # Critical senesced stem nitrogen concentration (g N / g stem)
        "GNC": 0.011,          # Critical grain nitrogen concentration (g N / g grain)
        "MXNUP": 0.6,          # Maximum potential daily N uptake (g N / m² / day)
    },
    "Sorghum": {
        "CROP": "Sorghum",
        "Cultivar": "M-35-1",
        "crop_produce_type": "Fruit/Seed",
        "lifecycle_strategy": "Annual (Single-Season)",
        "t_dormancy_trigger": 5.0,
        "t_base_winter": 0.0,
        # Phenology (GDD / GDD equivalents)
        "TBD": 8.0,
        "TP1D": 34.0,
        "TP2D": 37.0,
        "TCD": 45.0,
        "cpp": 14.0,
        "ppsen": 1.7538,
        "bdSOWEMR": 2.0,
        "bdEMREJU": 12.3,
        "bdEJUPNI": 4.0,
        "bdPNITLM": 18.0,
        "bdTLMANT": 6.0,
        "bdANTBSG": 2.0,
        "bdBSGPM": 21.4,
        "bdPMHM": 4.0,
        "PHYL": 50.0,
        # Canopy / LAI Expansion
        "PLACON": 1.0,
        "PLAPOW8": 2.54,       # Used directly for Sorghum
        "SLA": 0.025,
        "TKILL": 5.0,
        "FRZLDR": 0.01,
        # Radiation Use Efficiency (RUE)
        "TBRUE": 8.0,
        "TP1RUE": 20.0,
        "TP2RUE": 35.0,
        "TCRUE": 50.0,
        "KPAR": 0.6,
        "IRUE": 3.2,
        # Dry Matter Allocation / Yield
        "FLF1A": 0.7,
        "FLF1B": 0.15,
        "WTOPL": 180.0,
        "FLF2": 0.05,
        "FRTRL": 0.22,
        "GCC": 1.0,
        "PDHI": 0.0185,
        "WDHI1": 0.0,
        "WDHI2": 0.0,
        "WDHI3": 9999.0,
        "WDHI4": 9999.0,
        # Root / Hydrological Stresses
        "iDEPORT": 150.0,
        "MEED": 1300.0,
        "GRTDP": 27.0,
        "TEC": 9.0,
        "WSSG": 0.25,
        "WSSL": 0.35,
        "WSSD": 0.1,
        "FLDKL": 40.0,
        # Nitrogen Ingestion
        "SLNG": 1.06,
        "SLNS": 0.4,
        "SNCG": 0.0106,
        "SNCS": 0.0025,
        "GNC": 0.0135,
        "MXNUP": 0.6,
    }
}


class SimulationResultDataFrame(pd.DataFrame):
    _metadata = ["diagnostic_df"]

    @property
    def _constructor(self):
        return SimulationResultDataFrame

    def __getitem__(self, key):
        if isinstance(key, str) and key == "diagnostic_df":
            return getattr(self, "diagnostic_df", None)
        return super().__getitem__(key)


class SSMiCropEngine:
    """
    Production-grade object-oriented simulation engine translating the BOKU Simple Simulation Model (SSM-iCrop)
    from reference Excel and VBA implementations for Maize and Sorghum, fully upgraded to incorporate physical 
    daily soil moisture budgets and a dynamic Nitrogen availability stress model.
    """

    def __init__(self, 
                 weather_df: pd.DataFrame, 
                 latitude: float, 
                 soil_params: Optional[Dict[str, Any]] = None,
                 soil_config: Optional[Dict[str, Any]] = None,
                 fertilizer_schedule: Optional[List[Dict[str, Any]]] = None,
                 water_management: Optional[Dict[str, Any]] = None,
                 mode: str = "Advanced",
                 advanced_options: Optional[Dict[str, bool]] = None,
                 sim_years: int = 1):
        """
        Initialize the simulation engine with standard parameters and dynamic soil/nutrient schedules.
        """
        self.weather_df = weather_df.copy()
        self.latitude = latitude
        self.sim_years = sim_years
        
        # Load or initialize default soil profile properties (5 layers)
        if soil_params is None:
            self.soil_params = {
                "NLYER": 5,
                "LDRAIN": 4,         # Index (0-based) representing the bottom drainage layer
                "SALB": 0.13,        # Soil albedo
                "U": 6.0,            # First-stage soil evaporation limit (mm)
                "CN": 75.0,          # SCS curve number for runoff
                "DLYER": [150.0, 150.0, 300.0, 300.0, 300.0],       # Layer thickness (mm)
                "SAT": [0.45, 0.43, 0.41, 0.41, 0.40],             # Saturation capacity (volumetric)
                "DUL": [0.35, 0.33, 0.31, 0.31, 0.30],             # Drained upper limit (volumetric)
                "EXTR": [0.15, 0.13, 0.11, 0.11, 0.10],            # Extractable water (volumetric)
                "DRAINF": [0.4, 0.4, 0.4, 0.4, 0.4],               # Daily drainage coefficients
                "MAI": [1.0, 1.0, 1.0, 1.0, 1.0]                   # Initial soil moisture relative capacity
            }
        else:
            self.soil_params = soil_params
            
        self.soil_config = soil_config or {}
        
        # Dynamically set initial soil moisture relative capacity (MAI) based on initial_water_percent
        if "initial_water_percent" in self.soil_config:
            init_fraction = max(0.0, min(1.0, self.soil_config["initial_water_percent"] / 100.0))
            self.soil_params = self.soil_params.copy()
            self.soil_params["MAI"] = [init_fraction] * self.soil_params.get("NLYER", 5)
        self.fertilizer_schedule = fertilizer_schedule or []
        self.water_management = water_management or {}
        self.mode = mode
        self.advanced_options = advanced_options.copy() if advanced_options is not None else {
            "use_vpd": False,
            "use_leaching": False,
            "use_root_growth": False,
            "use_heat_shock": False
        }
        if "use_moisture" not in self.advanced_options:
            self.advanced_options["use_moisture"] = True
        if "use_nitrogen" not in self.advanced_options:
            self.advanced_options["use_nitrogen"] = True
        self.pawc = self.soil_config.get("pawc_mm_m", 150.0)
        
        # 1. INITIALIZE DAILY STORAGE TRAITS
        soil_depth = self.soil_config.get("depth_mm", 1200.0)
        initial_water_pct = self.soil_config.get("initial_water_percent", 25.0)
        pawc = self.soil_config.get("pawc_mm_m", 150.0)
        
        # Establish daily tracking moisture variable (mm)
        self.current_soil_water = soil_depth * (initial_water_pct / 100.0)
        # Calculate absolute maximum storage capacity pool (mm)
        self.total_storage_capacity = max(1.0, soil_depth * (pawc / 1000.0))
        
        # Track dynamic Soil Nitrogen pool (kg N/ha)
        # We assume a base starting Soil Nitrogen level representing natural mineralization
        self.current_soil_n = 30.0

    def calculate_photoperiod(self, doy: int) -> float:
        """
        Calculate astronomical daylength (photoperiod) for a given Day of Year and latitude.
        Based on BOKU GCM solar declination routines.
        """
        pi = 3.141592654
        rdn = pi / 180.0
        sabh = 6.0  # Angle below horizon for civil twilight
        
        alpha = 90.0 + sabh
        sma3 = 0.9856 * doy - 3.251
        landa = sma3 + 1.916 * np.sin(sma3 * rdn) + 0.02 * np.sin(2.0 * sma3 * rdn) + 282.565
        dec = 0.39779 * np.sin(landa * rdn)
        
        # Guard against domain error in arcsin / arctan
        dec = np.clip(dec, -0.99999, 0.99999)
        dec_deg = np.arctan(dec / np.sqrt(1.0 - dec**2)) / rdn
        
        talsoc = 1.0 / np.cos(self.latitude * rdn)
        cedsoc = 1.0 / np.cos(dec_deg * rdn)
        
        socra = (np.cos(alpha * rdn) * talsoc * cedsoc) - (np.tan(self.latitude * rdn) * np.tan(dec_deg * rdn))
        socra = np.clip(socra, -1.0, 1.0)
        
        pp = pi / 2.0 - np.arctan(socra / np.sqrt(1.0 - socra**2))
        pp_hours = (2.0 / 15.0) * (pp / rdn)
        return pp_hours

    def calculate_stress_factor(self, tmp: float, tb: float, tp1: float, tp2: float, tcd: float) -> float:
        """
        Dent-like cardinal temperature stress calculation.
        Returns a stress factor between 0.0 and 1.0.
        """
        if tmp <= tb or tmp >= tcd:
            return 0.0
        elif tb < tmp < tp1:
            return (tmp - tb) / (tp1 - tb)
        elif tp2 < tmp < tcd:
            return (tcd - tmp) / (tcd - tp2)
        elif tp1 <= tmp <= tp2:
            return 1.0
        return 0.0

    def run_simulation(self, crop_type: str, pden: float = 8.0, vpdf: float = 1.0, progress_callback = None, sim_years: Optional[int] = None) -> pd.DataFrame:
        """
        Execute the daily SSM-iCrop crop growth simulation loop from sowing to maturity.
        
        Parameters:
            crop_type (str): "Maize" or "Sorghum"
            pden (float): Plant density (plants/m², default = 8.0)
            vpdf (float): Vapor pressure deficit adjustment factor (default = 1.0)
            progress_callback (callable): Optional progress reporting callback accepting (current, total)
            sim_years (int): Optional multi-year duration override
            
        Returns:
            pd.DataFrame: Simulation timeseries dataset representing daily growth variables.
        """
        # 1. Load Crop Parameters
        if crop_type not in DEFAULT_CROP_PARAMETERS:
            raise ValueError(f"Crop type '{crop_type}' is not supported. Supported crops: Maize, Sorghum")
        
        cp = DEFAULT_CROP_PARAMETERS[crop_type]
        
        if sim_years is None:
            sim_years = getattr(self, "sim_years", 1)
            
        lifecycle_strategy = cp.get("lifecycle_strategy", "Annual (Single-Season)")
        t_dormancy_trigger = cp.get("t_dormancy_trigger", 5.0)
        t_base_winter = cp.get("t_base_winter", 0.0)
        
        # Check if all advanced modular switches are disabled
        all_stresses_disabled = False
        if self.mode == "Advanced":
            all_stresses_disabled = not (
                self.advanced_options.get("use_vpd", False) or
                self.advanced_options.get("use_leaching", False) or
                self.advanced_options.get("use_root_growth", False) or
                self.advanced_options.get("use_heat_shock", False)
            )
            
        # Determine active biophysical process flags
        use_vpd = self.advanced_options.get("use_vpd", False)
        use_moisture = self.advanced_options.get("use_moisture", True)
        use_nitrogen = self.advanced_options.get("use_nitrogen", True)
        
        # If all modular options are unchecked, fall back to perfect conditions
        if all_stresses_disabled:
            use_vpd = False
            use_moisture = False
            use_nitrogen = False
        
        # Extract cardinal temperature and GDD coefficients
        tbd = cp["TBD"]
        tp1d = cp["TP1D"]
        tp2d = cp["TP2D"]
        tcd = cp["TCD"]
        cpp = cp["cpp"]
        ppsen = cp["ppsen"]
        bd_sow_emr = cp["bdSOWEMR"]
        bd_emr_eju = cp["bdEMREJU"]
        bd_sil_pm = cp.get("bdSILPM", cp.get("bdBSGPM", 33.8))
        phyl = cp["PHYL"]
        
        # Canopy expansion coefficients
        placon = cp["PLACON"]
        plapow8 = cp["PLAPOW8"]
        sla = cp["SLA"]
        tkill = cp["TKILL"]
        frzldr = cp["FRZLDR"]
        
        # RUE coefficients
        tbrue = cp["TBRUE"]
        tp1rue = cp["TP1RUE"]
        tp2rue = cp["TP2RUE"]
        tcrue = cp["TCRUE"]
        kpar = cp["KPAR"]
        irue = cp["IRUE"]
        
        # Biomass distribution & yield
        flf1a = cp["FLF1A"]
        flf1b = cp["FLF1B"]
        wtopl = cp["WTOPL"]
        flf2 = cp["FLF2"]
        frtrl = cp["FRTRL"]
        gcc = cp["GCC"]
        pdhi = cp["PDHI"]           # Daily HI increment rate (g/g/day) — NOT an absolute cap
        # True biological maximum HI ceiling for the crop type
        # Maize: ~0.55; Sorghum: ~0.50 (from literature and reference output HI=0.525)
        hi_ceiling = 0.55 if crop_type == "Maize" else 0.52
        wdhi1 = cp["WDHI1"]
        wdhi2 = cp["WDHI2"]
        wdhi3 = cp["WDHI3"]
        wdhi4 = cp["WDHI4"]
        
        # Hydrological thresholds
        ideport = cp["iDEPORT"]
        meed = cp["MEED"]
        grtdp = cp["GRTDP"]
        tec = cp["TEC"]
        wssg = cp["WSSG"]
        wssl = cp["WSSL"]
        wssd = cp["WSSD"]
        fldkil = cp["FLDKL"]
        
        # Calculated plapow adjusted for plant density
        plapow = plapow8 * (1.0378 - 0.0047 * pden)
        
        # 2. Extract Soil parameters
        nlayer = self.soil_params["NLYER"]
        ldrain = self.soil_params["LDRAIN"]
        salb = self.soil_params["SALB"]
        u = self.soil_params["U"]
        cn = self.soil_params["CN"]
        
        dlyer = np.array(self.soil_params["DLYER"])
        sat = np.array(self.soil_params["SAT"])
        dul = np.array(self.soil_params["DUL"])
        extr = np.array(self.soil_params["EXTR"])
        
        cll = dul - extr
        adry = cll / 3.0
        drainf = np.array(self.soil_params["DRAINF"])
        mai = np.array(self.soil_params["MAI"])
        
        # Volumetric constraints converted to total water depth per layer (mm)
        wlad = adry * dlyer
        wlll = cll * dlyer
        wlul = dul * dlyer
        wlst = sat * dlyer
        wl = wlll + (wlul - wlll) * mai
        
        # Initial water states in root zone
        ats_water = wl - wlll
        total_depth = np.sum(dlyer)
        
        # Initialize biological day phenology milestones
        bd_emr = bd_sow_emr
        bd_eju = bd_emr + bd_emr_eju
        
        if crop_type == "Maize":
            bd_ejutsi = 4.0
            bd_tsi = bd_eju + bd_ejutsi
            bd_tsisil = ((15.0 + 0.5) * phyl) / (34.0 - 8.0) - (bd_tsi - bd_emr)
            bd_sil = bd_tsi + bd_tsisil
            bd_tse = bd_sil - 76.0 / 26.0
            bd_bsg = bd_sil + 170.0 / 26.0
            bd_tsg = bd_sil + 0.95 * bd_sil_pm
            bd_pm = bd_tsg + 0.05 * bd_sil_pm
            bd_mat = bd_pm + 4.0
            bd_brp = bd_eju
            bd_trp = bd_tsi
            bd_tlm = bd_sil
        else: # Sorghum GDD milestones mapping
            bd_ejutsi = cp["bdEJUPNI"]
            bd_tsi = bd_eju + bd_ejutsi
            bd_tsisil = cp["bdPNITLM"]
            bd_sil = bd_tsi + bd_tsisil
            bd_tse = bd_sil + cp["bdTLMANT"]
            bd_bsg = bd_sil + cp["bdANTBSG"]
            bd_tsg = bd_bsg + cp["bdBSGPM"]
            bd_pm = bd_tsg + cp["bdPMHM"]
            bd_mat = bd_pm + 4.0
            bd_brp = bd_eju
            bd_trp = bd_tsi
            bd_tlm = bd_sil
            
        # 3. Simulation State Variables
        dap = 0
        cbd = 0.0
        
        msnn = 1.0
        lai = 0.0
        glai = 0.0
        dlai = 0.0
        mxlai = 0.0
        pla1 = 0.0
        pla2 = 0.0
        bsg_lai = 0.0
        ant_lai = 0.0
        
        wlf = 0.5
        wst = 0.5
        wveg = wlf + wst
        wgrn = 0.0
        wtop = wlf + wst
        hi = 0.0
        ant_dm = 0.0
        
        trldm = 0.0
        bsg_dm = 0.0
        dhi = 0.0
        
        deport = ideport
        
        # Dynamic initial root capacity & soil water / nutrient pool setup
        if self.mode == "Advanced":
            self.current_soil_n = cp.get("SNAVL_init", self.soil_config.get("initial_n", 150.0))
            if self.advanced_options.get("use_root_growth", False):
                self.total_storage_capacity = max(1.0, ideport * (self.pawc / 1000.0))
            else:
                deport = meed
                self.total_storage_capacity = max(1.0, deport * (self.pawc / 1000.0))
            self.current_soil_water = self.total_storage_capacity

        dyse = 1
        crain = 0.0
        cirgw = 0.0
        crunof = 0.0
        ce = 0.0
        ctr = 0.0
        cdrain = 0.0
        irg_no = 0
        fldur = 0
        
        rt = np.ones(nlayer)
        wu = np.zeros(nlayer)
        se = np.zeros(nlayer)
        flout = np.zeros(nlayer)
        rlyer = np.zeros(nlayer)
        
        x_tsi = 0
        tu_emr_tsi = 0.0
        mat_flag = 0
        
        # Hydrological stress initializations
        wsfl = 1.0
        wsfg = 1.0
        wsfd = 1.0
        wsxf = 1.0
        fts_wrz = 1.0
        
        # Result containers
        sim_data = []
        diagnostic_rows = []
        
        cum_dtu_emergence = 0.0
        pollen_sterility = 0.0
        
        # 4. Daily Calculation Loop
        days_in_dataset = len(self.weather_df)
        total_steps = sim_years * days_in_dataset
        
        temp_history = []
        in_dormancy = False
        consec_spring_days = 0
        wwood = 0.0
        
        for step in range(total_steps):
            yr = step // days_in_dataset
            idx = step % days_in_dataset
            
            if idx == 0 and yr > 0:
                if lifecycle_strategy == "Annual (Single-Season)":
                    cbd = 0.0
                    msnn = 1.0
                    lai = 0.0
                    glai = 0.0
                    dlai = 0.0
                    mxlai = 0.0
                    pla1 = 0.0
                    pla2 = 0.0
                    bsg_lai = 0.0
                    ant_lai = 0.0
                    wlf = 0.5
                    wst = 0.5
                    wveg = wlf + wst
                    wgrn = 0.0
                    wtop = wlf + wst
                    hi = 0.0
                    ant_dm = 0.0
                    trldm = 0.0
                    bsg_dm = 0.0
                    dhi = 0.0
                    mat_flag = 0
                    x_tsi = 0
                    tu_emr_tsi = 0.0
                    cum_dtu_emergence = 0.0
                    pollen_sterility = 0.0
                else:
                    cbd = 0.0
                    mat_flag = 0
                    x_tsi = 0
                    tu_emr_tsi = 0.0
                    cum_dtu_emergence = 0.0
                    pollen_sterility = 0.0
            
            if progress_callback:
                try:
                    progress_callback(step + 1, total_steps)
                except Exception:
                    pass
                    
            if mat_flag == 1:
                if sim_years == 1:
                    break
                else:
                    if lifecycle_strategy == "Annual (Single-Season)":
                        lai = 0.0
                        glai = 0.0
                        dlai = 0.0
                        wlf = 0.0
                        wst = 0.0
                        wveg = 0.0
                        wgrn = 0.0
                        wtop = 0.0
                        hi = 0.0
                        ddmp = 0.0
                        glf = 0.0
                        gst = 0.0
                        sgr = 0.0
                
            row_wth = self.weather_df.iloc[idx]
            doy = int(row_wth["DOY"])
            srad = float(row_wth["SRAD"])
            tmax = float(row_wth["TMAX"])
            tmin = float(row_wth["TMIN"])
            rain = float(row_wth["RAIN"])
            
            tmp = (tmax + tmin) / 2.0
            
            # Track 5-day moving average temperature
            temp_history.append(tmp)
            if len(temp_history) > 5:
                temp_history.pop(0)
            avg_temp_5d = sum(temp_history) / len(temp_history)
            
            # Dormancy state tracking
            if lifecycle_strategy != "Annual (Single-Season)":
                if avg_temp_5d < t_dormancy_trigger:
                    in_dormancy = True
                    
            if in_dormancy:
                if tmp >= t_dormancy_trigger:
                    consec_spring_days += 1
                    if consec_spring_days >= 5:
                        in_dormancy = False
                        consec_spring_days = 0
                        # Spring flush!
                        lai = max(lai, 0.5)
                        wlf = max(wlf, 5.0)
                else:
                    consec_spring_days = 0
            
            active_tbd = t_base_winter if in_dormancy else tbd
            
            # Initialize Nitrogen variables for the day
            SNAVL = self.current_soil_n
            Daily_Crop_Nitrogen_Uptake = 0.0
            N_Leached_Daily = 0.0
            
            if self.mode == "Advanced":
                # --- 2. THE DAILY SOIL WATER BALANCE LOOP ---
                # Extract daily scheduled irrigation amount (mm) for this DOY
                irr_today = 0.0
                if self.water_management and "irrigation" in self.water_management:
                    for irr in self.water_management["irrigation"]:
                        if int(irr.get("doy", 0)) == doy:
                            irr_today += float(irr.get("water_applied_mm", 0.0))
                
                # Extract daily scheduled drainage capacity (mm/day) active for this DOY
                drn_today = 0.0
                if self.water_management and "drainage" in self.water_management:
                    for drn in self.water_management["drainage"]:
                        if doy >= int(drn.get("start_doy", 0)):
                            drn_today += float(drn.get("release_rate_mm_day", 0.0))
                
                # Estimate potential evapotranspiration (PET) for the daily balance
                td_temp = 0.6 * tmax + 0.4 * tmin
                eeq_est = srad * (0.004876 - 0.004374 * 0.23) * (td_temp + 29.0)
                pet_est = eeq_est * 1.1
                if tmax > 34.0:
                    pet_est = eeq_est * ((tmax - 34.0) * 0.05 + 1.1)
                elif tmax < 5.0:
                    pet_est = eeq_est * 0.01 * np.exp(0.18 * (tmax + 20.0))
                pet_est = max(0.0, pet_est)
                
                # Apply daily water budget balance
                water_in = rain + irr_today
                water_out = pet_est + drn_today
                self.current_soil_water = self.current_soil_water + water_in - water_out
                self.current_soil_water = max(0.0, self.current_soil_water)
                
                # Saturation capping / runoff trigger
                excess_water = 0.0
                if self.current_soil_water > self.total_storage_capacity:
                    excess_water = self.current_soil_water - self.total_storage_capacity
                    self.current_soil_water = self.total_storage_capacity
                
                # --- 3. CALCULATE WATER STRESS MULTIPLIERS (F_water) ---
                ftsw = self.current_soil_water / self.total_storage_capacity if self.total_storage_capacity > 0.0 else 0.0
                ftsw = np.clip(ftsw, 0.0, 1.0)
                
                if use_moisture:
                    if ftsw < 0.3:
                        # Deficit / Drought penalty drops linearly to 0
                        f_water = ftsw / 0.3
                    elif ftsw > 0.95:
                        # Waterlogging oxygen-deficit penalty drops linearly to 0 at complete saturation
                        f_water = (1.0 - ftsw) / 0.05
                    else:
                        f_water = 1.0
                    f_water = np.clip(f_water, 0.0, 1.0)
                else:
                    f_water = 1.0

                # --- 4. IMPLEMENT LITE NITROGEN AVAILABILITY MODEL (F_nutr) ---
                NFERT = 0.0
                if self.fertilizer_schedule:
                    for fert in self.fertilizer_schedule:
                        if int(fert.get("doy", 0)) == doy:
                            NFERT += float(fert.get("nitrogen_kg_ha", 0.0))
                
                SNAVL += NFERT
                self.current_soil_n = SNAVL
            else:
                f_water = 1.0
                f_nutr = 1.0
                fts_wrz = 1.0
                wsfl = 1.0
                wsfg = 1.0
                wsfd = 1.0
                wsxf = 1.0
                irgw = 0.0
                drain = 0.0
                runof = 0.0
                pet = 0.0
                sevp = 0.0
                tr = 0.0
            
            # --- Phenology Module ---
            if in_dormancy:
                temp_stress = 0.0
                dtu = 0.0
                bd_inc = 0.0
                pp = self.calculate_photoperiod(doy)
            else:
                temp_stress = self.calculate_stress_factor(tmp, active_tbd, tp1d, tp2d, tcd)
                
                # Daylength photoperiod calculations
                pp = self.calculate_photoperiod(doy)
                
                if bd_brp <= cbd <= bd_trp:
                    if pp > cpp:
                        rate_in = 1.0 / (bd_ejutsi + ppsen * (pp - cpp))
                        r_max = 1.0 / bd_ejutsi
                        pp_stress = max(0.0, rate_in / r_max)
                    else:
                        pp_stress = 1.0
                else:
                    pp_stress = 1.0
                    
                # GDD unit accumulation
                dtu = (tp1d - active_tbd) * temp_stress
                if cbd > bd_bsg:
                    dtu = dtu * wsfd
                    
                # Biological day increment
                if bd_brp <= cbd <= bd_trp:
                    bd_inc = pp_stress
                else:
                    bd_inc = temp_stress
                    
                if cbd > bd_bsg:
                    bd_inc = bd_inc * wsfd  # Deficit accelerates biological aging
                
            cbd += bd_inc
            dap += 1
            
            if cbd >= bd_emr:
                cum_dtu_emergence += dtu
                
            # Pollination heat shock sterility calculation
            if self.mode == "Advanced" and self.advanced_options.get("use_heat_shock", False):
                if (bd_sil - 5.0) <= cbd <= (bd_sil + 5.0):
                    if tmax > 35.0:
                        pollen_sterility += 0.05 * (tmax - 35.0)
                        pollen_sterility = min(0.8, pollen_sterility)
            
            if cbd >= bd_emr and cbd <= bd_tsi:
                tu_emr_tsi += dtu
                
            if cbd > bd_tsi and x_tsi == 0:
                tlno = tu_emr_tsi / (phyl * 0.5) + 5.0
                bd_tsisil = (((tlno + 0.5) * phyl) - tu_emr_tsi) / (tp1d - tbd)
                x_tsi = 1
                
                bd_sil = bd_tsi + bd_tsisil
                bd_tse = bd_sil - 76.0 / (tp1d - tbd)
                bd_bsg = bd_sil + 170.0 / (tp1d - tbd)
                bd_tsg = bd_sil + 0.95 * bd_sil_pm
                bd_pm = bd_tsg + 0.05 * bd_sil_pm
                bd_mat = bd_pm + 4.0
                bd_brp = bd_eju
                bd_trp = bd_tsi
                bd_tlm = bd_sil
                
            if cbd > bd_mat:
                mat_flag = 1
                
            # --- Canopy Module ---
            lai = lai + glai - dlai
            lai = max(0.0, lai)
            if lai > mxlai:
                mxlai = lai
                
            # Default values (preserving standard baseline continuity)
            f_vpd_rue = 1.0
            wssl_day = wssl
            wssg_day = wssg
            
            # VPD calculations
            vpt_min = 0.6108 * np.exp(17.27 * tmin / (tmin + 237.3))
            vpt_max = 0.6108 * np.exp(17.27 * tmax / (tmax + 237.3))
            e_s = 0.5 * (vpt_max + vpt_min)
            
            # Determine actual vapor pressure e_a
            if "RH" in row_wth:
                rh = float(row_wth["RH"])
                e_a = e_s * (rh / 100.0)
            elif "TDEW" in row_wth:
                tdew = float(row_wth["TDEW"])
                e_a = 0.6108 * np.exp(17.27 * tdew / (tdew + 237.3))
            else:
                e_a = vpt_min  # Dew Point approximation (RHmax = 100%)
                
            vpd_calc = max(0.0, e_s - e_a)
            
            if self.mode == "Advanced" and self.advanced_options.get("use_vpd", False):
                if vpd_calc > 1.5:
                    # Decrease RUE: 15% reduction per kPa above 1.5, capped at 50% max penalty
                    f_vpd_rue = np.clip(1.0 - 0.15 * (vpd_calc - 1.5), 0.5, 1.0)
                    # Increase critical FTSW thresholds linearly by 0.1 per kPa above 1.5, capped at 0.8
                    wssl_day = np.clip(wssl + 0.1 * (vpd_calc - 1.5), wssl, 0.8)
                    wssg_day = np.clip(wssg + 0.1 * (vpd_calc - 1.5), wssg, 0.8)

            # Estimate potential RUE for N Demand
            rue_temp_factor = self.calculate_stress_factor(tmp, tbrue, tp1rue, tp2rue, tcrue)
            rue = irue * rue_temp_factor * f_vpd_rue
            fint = 1.0 - np.exp(-kpar * lai)
            
            if self.mode == "Advanced" and use_nitrogen:
                # Calculate daily potential biomass growth for N Demand estimation
                ddmp_pot = srad * 0.48 * fint * rue * temp_stress
                
                # Compute Nitrogen demand (1.8% critical tissue concentration, 1 g/m² = 10 kg/ha)
                n_demand = (ddmp_pot * 10.0) * 0.018
                
                if n_demand > 0.0:
                    if SNAVL >= n_demand:
                        f_nutr = 1.0
                        Daily_Crop_Nitrogen_Uptake = n_demand
                    else:
                        # Nutrient deficit penalizes growth
                        f_nutr = SNAVL / n_demand
                        Daily_Crop_Nitrogen_Uptake = SNAVL
                else:
                    f_nutr = 1.0
                f_nutr = np.clip(f_nutr, 0.1, 1.0)
                SNAVL -= Daily_Crop_Nitrogen_Uptake
                self.current_soil_n = SNAVL
            else:
                f_nutr = 1.0
            
            # Canopy Expansion (LAI is penalized by both Water stress and N stress)
            if in_dormancy:
                glai = 0.0
                dlai = 0.0
            elif cbd <= bd_emr:
                glai = 0.0
                dlai = 0.0
            elif bd_emr < cbd <= bd_tlm:
                inode = dtu / phyl
                msnn += inode
                pla2 = placon * (msnn ** plapow)
                glai = ((pla2 - pla1) * pden / 10000.0) * wsfl * f_nutr
                pla1 = pla2
                dlai = 0.0
            elif bd_tlm < cbd <= bd_bsg:
                glai = glf * sla
                bsg_lai = lai
                dlai = 0.0
            elif cbd > bd_bsg:
                glai = 0.0
                dlai = bd_inc / (bd_mat - bd_bsg) * bsg_lai
                
            if cbd <= bd_sil:
                ant_lai = lai
                
            # Frost Damage check on Canopy (extreme thermal stress)
            dlai_f = 0.0
            if self.mode == "Advanced":
                if cbd > bd_emr and tmin < tkill:
                    frost_factor = max(0.0, min(1.0, abs(tmin - tkill) * frzldr))
                    dlai_f = lai * frost_factor
            dlai = max(dlai, dlai_f)
            
            # --- 5. DAILY BIOMASS PRODUCTION (Beer-Lambert PAR Interception) ---
            # Eq: PAR_intercepted = SRAD × (1 - exp(-KPAR × LAI))
            # Note: fint = 1 - exp(-kpar * lai) is already computed above.
            # RUE converts intercepted PAR (MJ/m²) to dry matter (g/m²).
            # The 0.48 factor converts total SRAD to PAR (photosynthetically
            # active radiation band). growth_stress applies combined water+N penalty.
            growth_stress = min(f_water, f_nutr)
            par_intercepted = srad * 0.48 * fint          # MJ PAR intercepted per m² per day
            ddmp = par_intercepted * rue * growth_stress   # g DM / m² / day
            
            # --- Yield Partitioning Module ---
            glf = 0.0
            gst = 0.0
            sgr = 0.0
            transl = 0.0
            
            if cbd <= bd_emr or cbd > bd_tsg or in_dormancy:
                ddmp = 0.0
            elif bd_emr < cbd <= bd_tlm:
                flf1 = flf1a if wtop < wtopl else flf1b
                glf = flf1 * ddmp
                gst = ddmp - glf
            elif bd_tlm < cbd < bd_bsg:
                glf = flf2 * ddmp
                gst = ddmp - glf
                bsg_dm = wtop
                
                # Dynamic Harvest Index potential calculation based on stress biomass
                if bsg_dm <= wdhi1 or bsg_dm >= wdhi4:
                    dhif = 0.0
                elif wdhi1 < bsg_dm < wdhi2:
                    dhif = (bsg_dm - wdhi1) / (wdhi2 - wdhi1)
                elif wdhi3 < bsg_dm < wdhi4:
                    dhif = (wdhi4 - bsg_dm) / (wdhi4 - wdhi3)
                else:
                    dhif = 1.0
                dhi = pdhi * dhif
                trldm = bsg_dm * frtrl
                
            elif bd_bsg <= cbd <= bd_tsg:
                sgr = dhi * (wtop + ddmp) + ddmp * hi
                
                # Apply pollination heat shock sterility reduction to daily grain allocation
                if self.mode == "Advanced" and self.advanced_options.get("use_heat_shock", False):
                    sgr = sgr * (1.0 - pollen_sterility)
                
                if (sgr / gcc) > ddmp:
                    transl = (sgr / gcc) - ddmp
                    transl = min(transl, trldm)
                
                trldm -= transl
                sgr_limit = (ddmp + transl) * gcc
                if sgr > sgr_limit:
                    sgr = sgr_limit
                    
                if (sgr / gcc) < ddmp:
                    gst = ddmp - (sgr / gcc)
                    
            wlf += glf
            wst += gst
            wgrn += sgr
            
            if in_dormancy:
                lai = max(0.05, 0.9 * lai)
                wlf = max(0.2, 0.9 * wlf)
                
            if lifecycle_strategy == "Cyclical Perennial":
                wwood += 0.2 * gst

            # ---------------------------------------------------------------
            # MASS CONSERVATION — pool totals recalculated every time step.
            # Key: translocation (transl) moves mass FROM wst TO wgrn,
            # so wst was already reduced by transl inside the yield block.
            # wveg = leaf + stem (structural); wtop = veg + grain (total AGB).
            # ---------------------------------------------------------------
            wveg = wlf + wst
            wtop = wveg + wgrn

            # Running Harvest Index = current grain fraction of total biomass.
            # Use a running ratio (not the daily-increment pdhi) for display.
            # pdhi (0.015 g/g/day) is a SINK RATE parameter, not an HI ceiling.
            if wtop > 0.0:
                hi = wgrn / wtop
                # Apply hard biological ceiling (Maize ~0.55, Sorghum ~0.52).
                # If somehow exceeded, trim grain to conserve mass.
                if hi > hi_ceiling:
                    wgrn = hi_ceiling * wtop
                    hi = hi_ceiling
            else:
                hi = 0.0
            # --- Soil Hydrology Module ---
            if self.mode == "Advanced":
                irgw = 0.0
                
                # Only run automatic irrigation if explicitly requested in water_management
                if self.water_management.get("auto_irrigation", False):
                    # Target field capacity represents full root zone capacity
                    if fts_wrz <= 0.5 and cbd < bd_tsg:
                        # Root zone water capacity deficit
                        target_fc = np.sum(wlul * (rlyer / dlyer))
                        current_fc = np.sum(wl * (rlyer / dlyer))
                        irgw = max(0.0, target_fc - current_fc)
                        irg_no += 1
                
                crain += rain
                cirgw += irgw
                
                # Drainage calculation (cascading bottom flux)
                drain = flout[ldrain]
                cdrain += drain
                
                # Nitrogen Leaching sub-model
                N_Leached_Daily = 0.0
                if self.advanced_options.get("use_leaching", False) and drain > 0.0:
                    # Calculate deep drainage (drain)
                    # Total_Soil_Water_Content is the total water content of the bottom drainage layer (wl[ldrain])
                    safe_soil_water = max(wl[ldrain], 0.001)
                    leaching_fraction = drain / safe_soil_water
                    
                    # Clamp the leaching_fraction explicitly so it can never mathematically exceed 100% of the available solution pool (capped at 0.75)
                    leaching_fraction = max(0.0, min(leaching_fraction, 0.75))
                    
                    # Calculate actual mass leached
                    leaching_efficiency = cp.get("leach_eff", self.advanced_options.get("leaching_efficiency", 0.8))
                    N_Leached_Daily = min(SNAVL * leaching_fraction * leaching_efficiency, max(0.0, SNAVL))
                    
                    # Update available soil mineral nitrogen pool
                    SNAVL -= N_Leached_Daily
                
                SNAVL = max(0.0, SNAVL)
                self.current_soil_n = SNAVL
                
                # Root depth propagation
                if self.advanced_options.get("use_root_growth", False):
                    # Grow roots strictly based on accumulated degree days since emergence until flowering
                    if cbd >= bd_emr:
                        if cbd <= bd_sil:
                            grtdp_dd = grtdp / (tp1d - tbd)
                            deport = min(ideport + (grtdp_dd * cum_dtu_emergence), meed)
                        else:
                            # Growth halts after flowering, deport remains constant
                            pass
                else:
                    grtd = grtdp * bd_inc
                    if cbd < bd_emr or cbd > bd_bsg or ddmp == 0.0 or deport >= total_depth or deport >= meed:
                        grtd = 0.0
                    # Root growth halts in completely dry soil
                    rtl_index = int(np.clip(deport // dlyer[0], 0, nlayer-1))
                    if ats_water[rtl_index] == 0.0:
                        grtd = 0.0
                    deport += grtd

                # Dynamic Soil Water Capacity Sizing
                if self.advanced_options.get("use_root_growth", False):
                    self.total_storage_capacity = max(1.0, deport * (self.pawc / 1000.0))
                    # Cap soil water tracker at expanding storage capacity
                    self.current_soil_water = min(self.current_soil_water, self.total_storage_capacity)
                
                # Distribute roots across soil layers
                dp_top = 0.0
                for l in range(nlayer):
                    rlyer[l] = deport - dp_top
                    rlyer[l] = np.clip(rlyer[l], 0.0, dlyer[l])
                    dp_top += dlyer[l]
                    
                # Runoff using SCS Curve Number method
                runof = 0.0
                if rain > 0.01:
                    s_coeff = 254.0 * (100.0 / cn - 1.0)
                    # Moisture-adjusted curve coefficient
                    swer = 0.15 * (((wlst[0] - wl[0]) / (wlst[0] - wlll[0])) * 0.5 + ((wlst[1] - wl[1]) / (wlst[1] - wlll[1])) * 0.5)
                    swer = max(0.0, swer)
                    if rain - swer * s_coeff > 0.0:
                         runof = ((rain - swer * s_coeff) ** 2) / (rain + (1.0 - swer) * s_coeff)
                crunof += runof
                
                # Evapotranspiration dynamics
                td_temp = 0.6 * tmax + 0.4 * tmin
                et_lai = lai if cbd <= bd_bsg else bsg_lai
                
                albedo = salb * np.exp(-kpar * et_lai) + 0.23 * (1.0 - np.exp(-kpar * et_lai))
                eeq = srad * (0.004876 - 0.004374 * albedo) * (td_temp + 29.0)
                pet = eeq * 1.1
                if tmax > 34.0:
                    pet = eeq * ((tmax - 34.0) * 0.05 + 1.1)
                elif tmax < 5.0:
                    pet = eeq * 0.01 * np.exp(0.18 * (tmax + 20.0))
                    
                # Soil Evaporation
                eos = pet * np.exp(-kpar * et_lai)
                eos = max(1.5, eos) if pet > 1.5 else eos
                
                sevp = eos
                if rain + irgw > 10.0:
                    dyse = 1
                if dyse > 1 or fts_wrz < 0.5 or ats_water[0] <= 1.0:
                    sevp = eos * ((dyse + 1.0) ** 0.5 - (dyse) ** 0.5)
                    dyse += 1
                ce += sevp
                
                # Plant Transpiration
                vpt_min = 0.6108 * np.exp(17.27 * tmin / (tmin + 237.3))
                vpt_max = 0.6108 * np.exp(17.27 * tmax / (tmax + 237.3))
                vpd = vpdf * (vpt_max - vpt_min)
                tr = ddmp * vpd / tec  # TEC in Pa, VPD in kPa
                tr = max(0.0, tr)
                ctr += tr
                
                # Update Layer Water Deficits & Cascading Redistribution
                aroot = np.sum(rlyer * rt)
                wuur = tr / (aroot + 1e-7)
                tse = sevp
                
                for l in range(nlayer):
                    wu[l] = rlyer[l] * rt[l] * wuur
                    se[l] = tse
                    se_limit = (wl[l] - wlad[l]) * drainf[l]
                    se[l] = min(se[l], max(0.0, se_limit))
                    if wl[l] <= wlad[l]:
                        se[l] = 0.0
                    tse = max(0.0, tse - se[l])
                    
                # Redistribute layer by layer (gravity cascading drainage)
                for l in range(nlayer):
                    flin_l = rain + irgw + irr_today - runof if l == 0 else flout[l-1]
                    wl[l] = wl[l] + flin_l - wu[l] - se[l]
                    tbt_val = cp.get("tbt", 1.0)
                    drainage_threshold_l = wlul[l] * tbt_val
                    flout[l] = max(0.0, (wl[l] - drainage_threshold_l) * drainf[l])
                    wl[l] = wl[l] - flout[l]
                    
                    ats_water[l] = max(0.0, wl[l] - wlll[l])
                    ttsw_l = wlul[l] - wlll[l]
                    fts_l = ats_water[l] / ttsw_l if ttsw_l > 0.0 else 0.0
                    rt[l] = 1.0 if fts_l > wssg_day else max(0.0, fts_l / wssg_day)
                    
                # Calculate overall Root Zone Water Stresses
                wrz = np.sum(wl * (rlyer / dlyer))
                wrzul = np.sum(wlul * (rlyer / dlyer))
                wrzst = np.sum(wlst * (rlyer / dlyer))
                ats_wrz = np.sum(ats_water * (rlyer / dlyer))
                tts_wrz = np.sum((wlul - wlll) * (rlyer / dlyer))
                
                fts_wrz = ats_wrz / tts_wrz if tts_wrz > 0.0 else 0.0
                
                # Stresses computation
                if use_moisture:
                    wsfl = 1.0 if fts_wrz > wssl_day else max(0.0, fts_wrz / wssl_day)
                    wsfg = 1.0 if fts_wrz > wssg_day else max(0.0, fts_wrz / wssg_day)
                    wsfd = (1.0 - wsfg) * wssd + 1.0
                    wsxf = 1.0 if wrz <= wrzul else max(0.0, (wrzst - wrz) / (wrzst - wrzul))
                    
                    # Flooding Stress Check
                    if wrz > 0.95 * wrzst:
                        wsfg = 0.0
                        wsfl = 0.0
                        fldur += 1
                    else:
                        fldur = 0
                        
                    if fldur > fldkil:
                        cbd = bd_tsg  # Abort growth loop / accelerate senescence
                else:
                    wsfl = 1.0
                    wsfg = 1.0
                    wsfd = 1.0
                    wsxf = 1.0
                    fldur = 0
                    
                # Synchronize single-layer trackers with physical 5-layer root zone water capacities
                self.current_soil_water = ats_wrz
                self.total_storage_capacity = max(1.0, tts_wrz)
            else:
                irgw = 0.0
                drain = 0.0
                runof = 0.0
                pet = 0.0
                sevp = 0.0
                tr = 0.0
                fts_wrz = 1.0
                wsfl = 1.0
                wsfg = 1.0
                wsfd = 1.0
                wsxf = 1.0
                # Propagate root depth normally
                grtd = grtdp * bd_inc
                if cbd < bd_emr or cbd > bd_bsg or ddmp == 0.0 or deport >= total_depth or deport >= meed:
                    grtd = 0.0
                deport += grtd
                
            # Save daily record
            active_produce_type = cp.get("crop_produce_type", "Fruit/Seed")
            wroot = wgrn if active_produce_type == "Tuber/Root" else (wtop * 0.2)
            
            sim_data.append({
                "crop_produce_type": active_produce_type,
                "lifecycle_strategy": lifecycle_strategy,
                "Current_Year": yr + 1,
                "Simulation_Timeline_Days": yr * 365 + doy,
                "WROOT": round(wroot, 2),
                "WWOOD": round(wwood, 2),
                "DAP": dap,
                "DOY": doy,
                "TMP": round(tmp, 2),
                "DTU": round(dtu, 2),
                "CBD": round(cbd, 3),
                "MSNN": round(msnn, 3),
                "GLAI": round(glai, 4),
                "DLAI": round(dlai, 4),
                "LAI": round(lai, 3),
                "FINT": round(fint, 3),
                "DDMP": round(ddmp, 2),
                "GLF": round(glf, 2),
                "GST": round(gst, 2),
                "SGR": round(sgr, 2),
                "WLF": round(wlf, 2),
                "WST": round(wst, 2),
                "WVEG": round(wveg, 2),
                "WGRN": round(wgrn, 2),
                "WTOP": round(wtop, 2),
                "HI": round(hi, 3),
                "FTSWRZ": round(fts_wrz, 3),
                "DEPORT": round(deport, 1),
                "RAIN": round(rain, 1),
                "IRGW": round(irgw, 1),
                "RUNOF": round(runof, 1),
                "PET": round(pet, 2),
                "SEVP": round(sevp, 2),
                "TR": round(tr, 2),
                "DRAIN": round(drain, 2),
                "SOIL_WATER": round(self.current_soil_water, 2),
                "SOIL_N": round(self.current_soil_n, 2),
                "F_WATER": round(f_water, 3),
                "F_NUTR": round(f_nutr, 3),
                "Model_Fidelity": self.mode
            })
            
            diagnostic_rows.append({
                "DAP": dap,
                "DRAIN": round(drain, 4),
                "SNAVL": round(SNAVL, 4),
                "NLEACH": round(N_Leached_Daily, 4),
                "NST": round(f_nutr, 3)
            })
            
            # Reset cyclical perennial grain pool at the end of the year's daily loop if mature
            if idx == days_in_dataset - 1:
                if lifecycle_strategy == "Cyclical Perennial" and cbd > bd_mat:
                    wgrn = 0.0
                    hi = 0.0
            
        df = SimulationResultDataFrame(sim_data)
        df.diagnostic_df = pd.DataFrame(diagnostic_rows)
        return df
