import streamlit as st
import pandas as pd
import datetime
from streamlit_cookies_controller import CookieController
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json
import sys
import os
import re
import time
import folium
from streamlit_folium import st_folium
import logging

import importlib

logger = logging.getLogger(__name__)

# Resolve parent directory to support clean imports from both the 'app' directory and the workspace root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Force-evict any stale cached module objects that predate recent code changes.
# This prevents Streamlit's hot-reload from reusing an old in-memory SSMiCropEngine
# that was compiled before the soil_config parameter was added to __init__.
for _stale_mod in ["core.model_engine", "core.weather_api", "core.soil_api"]:
    if _stale_mod in sys.modules:
        try:
            importlib.reload(sys.modules[_stale_mod])
        except Exception:
            del sys.modules[_stale_mod]

# Import requested backend modules exactly as named in the prompt context
from core.model_engine import SSMiCropEngine, DEFAULT_CROP_PARAMETERS
from utils.parameter_router import CropParameterRouter
from core.weather_api import fetch_openmeteo_weather, get_fallback_weather
from utils.weather_processor import WeatherProcessor
from core.soil_api import fetch_isric_soil_data
from utils.history_ledger import format_simulation_run
from utils.data_exporter import export_history_to_csv, export_history_to_xlsx
from utils.onedrive_helper import (
    is_onedrive_path_valid,
    list_onedrive_weather_files,
    load_onedrive_weather_file,
    list_onedrive_calibration_files,
    load_onedrive_calibration_file
)

# Relational security submodules
from utils.db_manager import DatabaseManager
from utils.auth_secure import (
    register_secure_user, 
    authenticate_secure_user, 
    verify_user_email_token, 
    request_password_reset, 
    execute_password_reset_token, 
    update_user_profile,
    resend_verification_email,
    verify_session_token,
    LOCAL_MAILBOX_SIMULATOR
)
from utils.calibrator import run_calibration_search

# Additional utilities
def is_smtp_configured() -> bool:
    try:
        smtp_secrets = st.secrets.get("smtp", {})
        return bool(smtp_secrets.get("host") and smtp_secrets.get("user") and smtp_secrets.get("password"))
    except Exception:
        return False

from utils.excel_parser import parse_crop_parameters
from utils.spatial_helper import SpatialSoilEstimator
from utils.time_slicer import WeatherTimeSlicer
from utils.performance_defenses import AsyncSimulationRunner

# Page Configuration for Premium Aesthetic
st.set_page_config(
    page_title="BOKU SSM-iCrop Growth Platform",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling Injection (Vanilla CSS for max control & glassmorphism feel)
st.markdown("""
    <style>
    .main-title {
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 2.8rem;
        background: linear-gradient(135deg, #10B981 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-family: 'Inter', sans-serif;
        font-size: 1.1rem;
        color: #6B7280;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #F9FAFB;
        border: 1px solid #E5E7EB;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        text-align: center;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #4B5563;
        font-weight: 500;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #10B981;
    }
    .stButton>button {
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        color: white;
        border: none;
        padding: 0.6rem 1.8rem;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
    }
    .stHeader {
        background-color: #F3F4F6;
        padding: 0.5rem 1rem;
        border-radius: 6px;
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

def configure_multi_year_chart(fig, df):
    """
    Unified multi-year Plotly Express visual formatter. 
    Injects vertical dashed dividers at year boundaries and centers 
    styled background-padded text annotations representing calendar years.
    """
    fig.update_layout(
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.95)", font_size=12)
    )
    if df is not None and "Year" in df.columns:
        av_years = sorted(df["Year"].unique())
        total_years = len(av_years)
        if total_years > 1:
            # Add vertical boundaries
            for i in range(1, total_years):
                day_marker = i * 365
                fig.add_vline(
                    x=day_marker,
                    line_dash="dash",
                    line_color="#9CA3AF",
                    line_width=1.5
                )
            # Center year annotations at the top
            for i in range(total_years):
                yr_val = av_years[i]
                mid_point = i * 365 + 182
                fig.add_annotation(
                    x=mid_point,
                    y=0.98,
                    yref="paper",
                    text=f"Year {i+1} ({int(yr_val)})",
                    showarrow=False,
                    font=dict(size=10, color="#4B5563", weight="bold"),
                    bgcolor="rgba(243, 244, 246, 0.85)",
                    bordercolor="#E5E7EB",
                    borderwidth=1,
                    borderpad=3
                )

def map_soil_profile_to_params(profile: dict) -> dict:
    """
    Maps the single-pixel physical soil profile from SpatialSoilEstimator
    to the 5-layer hydrological model parameter schema required by SSMiCropEngine.
    """
    clay = profile.get("clay_fraction", 0.28)
    sand = profile.get("sand_fraction", 0.32)
    om = profile.get("organic_matter", 0.025)
    
    # Saxton-Rawls equations for permanent wilting point & field capacity
    theta_pwp = 0.085 - 0.39 * sand + 0.44 * clay + 0.063 * om
    theta_fc = 0.25 - 0.42 * sand + 0.52 * clay + 0.08 * om
    
    depth_multipliers = [1.0, 0.94, 0.88, 0.88, 0.85]
    
    sat = []
    dul = []
    extr = []
    
    for mult in depth_multipliers:
        l_fc = max(0.15, min(0.45, theta_fc * mult))
        l_pwp = max(0.05, min(0.35, theta_pwp * mult))
        l_awc = max(0.05, min(0.25, l_fc - l_pwp))
        
        dul.append(round(l_fc, 3))
        sat.append(round(max(l_fc + 0.05, min(0.50, (l_fc + 0.10) * mult)), 3))
        extr.append(round(l_awc, 3))
        
    return {
        "NLYER": 5,
        "LDRAIN": 4,
        "SALB": 0.13,
        "U": 6.0,
        "CN": 75.0,
        "DLYER": [150.0, 150.0, 300.0, 300.0, 300.0],
        "SAT": sat,
        "DUL": dul,
        "EXTR": extr,
        "DRAINF": [0.4, 0.4, 0.4, 0.4, 0.4],
        "MAI": [1.0, 1.0, 1.0, 1.0, 1.0]
    }

# ----------------- SESSION STATE & SECURITY INITIALIZATION -----------------
if "icrop2_logged_in" not in st.session_state:
    st.session_state.icrop2_logged_in = False
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "latitude" not in st.session_state:
    st.session_state["latitude"] = 21.0285
if "longitude" not in st.session_state:
    st.session_state["longitude"] = 105.8542
if "icrop2_user_id" not in st.session_state:
    st.session_state.icrop2_user_id = None
if "icrop2_username" not in st.session_state:
    st.session_state.icrop2_username = None
if "icrop2_email" not in st.session_state:
    st.session_state.icrop2_email = None
if "icrop2_name" not in st.session_state:
    st.session_state.icrop2_name = None
if "icrop2_workplace" not in st.session_state:
    st.session_state.icrop2_workplace = None
if "icrop2_is_verified" not in st.session_state:
    st.session_state.icrop2_is_verified = 0
if "icrop2_user_tier" not in st.session_state:
    st.session_state.icrop2_user_tier = "Researcher"
if "icrop2_run_limit" not in st.session_state:
    st.session_state.icrop2_run_limit = 50
if "icrop2_session_token" not in st.session_state:
    st.session_state.icrop2_session_token = None
if "icrop2_session_key" not in st.session_state:
    st.session_state.icrop2_session_key = None
if "icrop2_async_runner" not in st.session_state:
    st.session_state.icrop2_async_runner = AsyncSimulationRunner()
if "icrop2_lat_key" not in st.session_state:
    st.session_state["icrop2_lat_key"] = 21.0285
if "icrop2_lon_key" not in st.session_state:
    st.session_state["icrop2_lon_key"] = 105.8542
if "icrop2_current_preset" not in st.session_state:
    st.session_state.icrop2_current_preset = "Custom Coordinates"
if "icrop2_fertilizer_rounds" not in st.session_state:
    st.session_state.icrop2_fertilizer_rounds = []
if "icrop2_irrigation_rounds" not in st.session_state:
    st.session_state.icrop2_irrigation_rounds = []
if "icrop2_drainage_rounds" not in st.session_state:
    st.session_state.icrop2_drainage_rounds = []
if "icrop2_som_key" not in st.session_state:
    st.session_state["icrop2_som_key"] = 2.5
if "icrop2_pawc_key" not in st.session_state:
    st.session_state["icrop2_pawc_key"] = 150.0
if "icrop2_depth_key" not in st.session_state:
    st.session_state["icrop2_depth_key"] = 1200
if "icrop2_initial_water_key" not in st.session_state:
    st.session_state["icrop2_initial_water_key"] = 25.0
if "icrop2_sim_history" not in st.session_state:
    st.session_state["icrop2_sim_history"] = {}
if "icrop2_detailed_scenarios" not in st.session_state:
    st.session_state["icrop2_detailed_scenarios"] = {}
if "icrop2_simulation_run_active" not in st.session_state:
    st.session_state.icrop2_simulation_run_active = False
if "icrop2_last_results_df" not in st.session_state:
    st.session_state.icrop2_last_results_df = None
if "icrop2_last_engine_instance" not in st.session_state:
    st.session_state.icrop2_last_engine_instance = None
if "icrop2_last_active_profile" not in st.session_state:
    st.session_state.icrop2_last_active_profile = None
if "icrop2_last_soil_profile" not in st.session_state:
    st.session_state.icrop2_last_soil_profile = None
if "icrop2_last_weather_status_msg" not in st.session_state:
    st.session_state.icrop2_last_weather_status_msg = ""
if "icrop2_cookie_controller" not in st.session_state:
    st.session_state.icrop2_cookie_controller = CookieController()
controller = st.session_state.icrop2_cookie_controller

# Intercept and process browser query parameters for activation, resets, and persistent sessions
query_params = st.query_params

if "session_token" in query_params:
    s_token = query_params["session_token"]
    s_success, s_payload = verify_session_token(s_token)
    if s_success:
        st.session_state.icrop2_logged_in = True
        st.session_state["authenticated"] = True
        st.session_state.icrop2_user_id = s_payload["user_id"]
        st.session_state.icrop2_username = s_payload["username"]
        st.session_state.icrop2_email = s_payload["email"]
        st.session_state.icrop2_name = s_payload["name"]
        st.session_state.icrop2_workplace = s_payload["workplace"]
        st.session_state.icrop2_is_verified = s_payload["is_verified"]
        st.session_state.icrop2_session_token = s_payload["session_token"]
        st.session_state.icrop2_session_key = s_payload["session_key"]
        st.session_state.icrop2_user_tier = s_payload.get("user_tier", "Researcher")
        st.session_state.icrop2_run_limit = s_payload.get("run_limit", 50)
    st.query_params.clear()

# Check cookies for persistent sessions if not currently authenticated
if not st.session_state.icrop2_logged_in:
    token = controller.get("icrop2_session_token")
    if token:
        s_success, s_payload = verify_session_token(token)
        if s_success:
            st.session_state.icrop2_logged_in = True
            st.session_state["authenticated"] = True
            st.session_state.icrop2_user_id = s_payload["user_id"]
            st.session_state.icrop2_username = s_payload["username"]
            st.session_state.icrop2_email = s_payload["email"]
            st.session_state.icrop2_name = s_payload["name"]
            st.session_state.icrop2_workplace = s_payload["workplace"]
            st.session_state.icrop2_is_verified = s_payload["is_verified"]
            st.session_state.icrop2_session_token = s_payload["session_token"]
            st.session_state.icrop2_session_key = s_payload["session_key"]
            st.session_state.icrop2_user_tier = s_payload.get("user_tier", "Researcher")
            st.session_state.icrop2_run_limit = s_payload.get("run_limit", 50)
            st.rerun()

if "verify_token" in query_params:
    token = query_params["verify_token"]
    success, msg = verify_user_email_token(token)
    if success:
        st.success(f"🎉 {msg}")
    else:
        st.error(f"❌ {msg}")
    # Clear parameter to prevent repeated evaluation
    st.query_params.clear()

if "reset_token" in query_params:
    token = query_params["reset_token"]
    st.markdown('<div class="main-title">SSM-iCrop Password Recovery</div>', unsafe_allow_html=True)
    st.subheader("🔄 Define Your New Credentials")
    new_p = st.text_input("New Secure Password", type="password", key="new_p_reset")
    new_p_c = st.text_input("Confirm New Password", type="password", key="new_p_reset_confirm")
    
    if st.button("Apply Password Reset", width='stretch'):
        if new_p != new_p_c:
            st.error("Passwords do not match!")
        else:
            success, msg = execute_password_reset_token(token, new_p)
            if success:
                st.success(f"🎉 {msg}")
                st.query_params.clear()
                # Enforce relogging
                st.session_state.icrop2_logged_in = False
                st.rerun()
            else:
                st.error(f"❌ {msg}")
    st.stop()

# If not authenticated, stop rendering workspace and enforce Auth Panel
if not st.session_state.icrop2_logged_in:
    st.markdown('<div class="main-title">SSM-iCrop Security Gateway</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Authenticate your research account to run crop simulations and access shared datasets.</div>', unsafe_allow_html=True)
    
    tab_login, tab_register, tab_forgot, tab_resend = st.tabs(["🔑 Sign In", "📝 Register Account", "🔒 Forgot Password", "📧 Resend Verification"])
    
    with tab_login:
        login_user = st.text_input("Username or Email", key="login_user_field")
        login_pass = st.text_input("Password", type="password", key="login_pass_field")
        
        # Get user IP (Mocked for local dashboard)
        ip_addr = "127.0.0.1"
        
        if st.button("Log In", width='stretch'):
            success, msg, payload = authenticate_secure_user(login_user, login_pass, ip_addr)
            if success and payload:
                st.session_state.icrop2_logged_in = True
                st.session_state["authenticated"] = True
                st.session_state.icrop2_user_id = payload["user_id"]
                st.session_state.icrop2_username = payload["username"]
                st.session_state.icrop2_email = payload["email"]
                st.session_state.icrop2_name = payload["name"]
                st.session_state.icrop2_workplace = payload["workplace"]
                st.session_state.icrop2_is_verified = payload["is_verified"]
                st.session_state.icrop2_session_token = payload["session_token"]
                st.session_state.icrop2_session_key = payload.get("session_key")
                st.session_state.icrop2_user_tier = payload.get("user_tier", "Researcher")
                st.session_state.icrop2_run_limit = payload.get("run_limit", 50)
                
                controller.set("icrop2_session_token", payload["session_token"])
                st.success("Access Granted! Loading C4 simulation core...")
                import time
                time.sleep(0.5)  # Buffer to allow browser storage write before Streamlit rerun
                st.rerun()
            else:
                st.error(msg)
                
            # Local debug helper: print simulator emails if login attempts increase
            if LOCAL_MAILBOX_SIMULATOR and not is_smtp_configured():
                with st.expander("📬 Debug Mailbox Simulator (Offline Activation Helper)", expanded=True):
                    st.info("Offline verification links generated in-memory during local review:")
                    for m in LOCAL_MAILBOX_SIMULATOR:
                        st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                        lnks = re.findall(r'href="(.*?)"', m["body_html"])
                        if lnks:
                            st.markdown(f"[🔗 Open Email Link]({lnks[0]})")
                
    with tab_register:
        reg_user = st.text_input("Username", key="reg_user_field")
        reg_email = st.text_input("Email Address", key="reg_email_field")
        reg_name = st.text_input("Full Name", key="reg_name_field")
        reg_workplace = st.text_input("Workplace / Institution", key="reg_workplace_field")
        reg_pass = st.text_input("Password (Min 6 chars)", type="password", key="reg_pass_field")
        
        if st.button("Create Account", width='stretch'):
            success, msg = register_secure_user(reg_user, reg_email, reg_pass, reg_name, reg_workplace)
            if success:
                st.success(msg)
            else:
                st.error(msg)
                
            if LOCAL_MAILBOX_SIMULATOR and not is_smtp_configured():
                with st.expander("📬 Debug Mailbox Simulator (Offline Activation Helper)", expanded=True):
                    st.info("Offline verification links generated in-memory during local review:")
                    for m in LOCAL_MAILBOX_SIMULATOR:
                        st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                        lnks = re.findall(r'href="(.*?)"', m["body_html"])
                        if lnks:
                            st.markdown(f"[🔗 Activate Account]({lnks[0]})")
                            
    with tab_forgot:
        st.subheader("🔑 Request Password Reset Link")
        reset_email = st.text_input("Registered Email Address", key="reset_email_field")
        if st.button("Request Reset Token", width='stretch'):
            success, msg = request_password_reset(reset_email)
            st.success(msg) # Standard security response
            
            if LOCAL_MAILBOX_SIMULATOR and not is_smtp_configured():
                with st.expander("📬 Debug Mailbox Simulator (Offline Reset Helper)", expanded=True):
                    st.info("Offline reset links generated in-memory during local review:")
                    for m in LOCAL_MAILBOX_SIMULATOR:
                        st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                        lnks = re.findall(r'href="(.*?)"', m["body_html"])
                        if lnks:
                            st.markdown(f"[🔗 Reset Password]({lnks[0]})")

    with tab_resend:
        st.subheader("📧 Resend Account Activation Link")
        st.info(
            "If your original activation email directed you to **localhost** or the link "
            "has already expired, use this form to request a new one. "
            "To protect against abuse, you may only request a new link once every **2 minutes**."
        )
        resend_identifier = st.text_input(
            "Email Address or Username",
            placeholder="Enter the email or username you registered with",
            key="resend_identifier_field",
        )

        if st.button("📨 Send New Activation Link", width='stretch', key="resend_btn"):
            if not resend_identifier.strip():
                st.warning("Please enter your registered email address or username.")
            else:
                with st.spinner("Processing your request…"):
                    resend_ok, resend_msg = resend_verification_email(resend_identifier.strip())

                if resend_ok:
                    st.success(f"✅ {resend_msg}")
                else:
                    # Distinguish cooldown messages from hard errors for UX clarity
                    if "wait" in resend_msg.lower() and "seconds" in resend_msg.lower():
                        st.warning(f"⏳ {resend_msg}")
                    else:
                        st.error(f"❌ {resend_msg}")

                # Show debug mailbox in offline/local mode
                if LOCAL_MAILBOX_SIMULATOR and not is_smtp_configured():
                    with st.expander("📬 Debug Mailbox Simulator (Offline Activation Helper)", expanded=True):
                        st.info("Offline activation links generated in-memory during local review:")
                        for m in LOCAL_MAILBOX_SIMULATOR:
                            if "Verify" in m.get("subject", "") or "Activation" in m.get("subject", ""):
                                st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                                lnks = re.findall(r'href="(.*?)"', m["body_html"])
                                if lnks:
                                    st.markdown(f"[🔗 Activate Account]({lnks[0]})")

    st.stop()

# Header details for authenticated users
st.sidebar.markdown(f"👤 **Account:** `{st.session_state.icrop2_username}`")
if st.sidebar.button("🚪 Log Out", width='stretch'):
    st.session_state.icrop2_logged_in = False
    st.session_state["authenticated"] = False
    st.session_state.icrop2_user_id = None
    st.session_state.icrop2_username = None
    st.session_state.icrop2_email = None
    st.session_state.icrop2_name = None
    st.session_state.icrop2_workplace = None
    st.session_state.icrop2_is_verified = 0
    st.session_state.icrop2_session_token = None
    st.session_state.icrop2_session_key = None
    st.session_state.icrop2_user_tier = "Researcher"
    st.session_state.icrop2_run_limit = 50
    
    controller.remove("icrop2_session_token")
    import time
    time.sleep(0.5)  # Buffer to allow browser storage removal before Streamlit rerun
    st.rerun()

# ----------------- SIDEBAR CONFIGURATION (Crop parameter routing & tweak panel) -----------------
with st.sidebar:
    st.header("🌱 Crop Profile Settings")
    
    # 1. Fetch available default and community profiles dynamically
    router = CropParameterRouter()
    db = DatabaseManager()
    
    # Fetch profiles matching privacy boundaries: Public OR owned by current user
    db_profiles = db.get_available_profiles(
        current_user_id=st.session_state.icrop2_user_id,
        session_key=st.session_state.get("icrop2_session_key")
    )
    
    # Assemble dropdown selection mapping
    profile_options = []
    profile_map = {}
    
    # - Default presets
    profile_options.append("Default: Maize (BOKU)")
    profile_map["Default: Maize (BOKU)"] = {
        "crop_type": "Maize",
        "parameters": DEFAULT_CROP_PARAMETERS["Maize"].copy(),
        "label": "Default: Maize (BOKU)"
    }
    
    profile_options.append("Default: Sorghum (BOKU)")
    profile_map["Default: Sorghum (BOKU)"] = {
        "crop_type": "Sorghum",
        "parameters": DEFAULT_CROP_PARAMETERS["Sorghum"].copy(),
        "label": "Default: Sorghum (BOKU)"
    }
    
    # - Seeded preset and custom profiles from crops table
    try:
        seeded_crops = db.get_seeded_crops(st.session_state.icrop2_user_id)
        for sc in seeded_crops:
            if sc.get("created_by_user_id") is not None:
                if sc.get("is_public") == 1:
                    lbl = f"🌐 Public Custom: {sc['crop_name']} ({sc['cultivar']})"
                else:
                    lbl = f"🔒 Private Custom: {sc['crop_name']} ({sc['cultivar']})"
            else:
                lbl = f"📦 Preset: {sc['crop_name']} ({sc['cultivar']})"
                
            profile_options.append(lbl)
            profile_map[lbl] = {
                "crop_type": sc["crop_type"],
                "parameters": sc["parameters"],
                "label": lbl
            }
    except Exception as e:
        logger.warning(f"Failed to add seeded crop presets: {e}")
        
    # - Dynamic sqlite custom profiles
    for dp in db_profiles:
        c_name = dp["crop_name"]
        creator = dp["creator"]
        is_pub = dp["is_public"]
        params = dp["parameters"]
        
        # Deduce type based on Sorghum specific key 'bdEJUPNI'
        c_type = "Sorghum" if "bdEJUPNI" in params else "Maize"
        
        if is_pub:
            lbl = f"🌐 Public: {c_name} (Shared by {creator})"
        else:
            lbl = f"🔒 Private: {c_name} (My Profile)"
            
        profile_options.append(lbl)
        profile_map[lbl] = {
            "crop_type": c_type,
            "parameters": params,
            "label": lbl
        }

    # Append static creation option token string to the top of the select list options array
    profile_options.insert(0, "➕ Create New Crop Profile...")
    
    # Manage session state selection to prevent resets
    if "icrop2_selected_crop_profile" not in st.session_state:
        st.session_state["icrop2_selected_crop_profile"] = "Default: Maize (BOKU)"
        
    if st.session_state["icrop2_selected_crop_profile"] not in profile_options:
        st.session_state["icrop2_selected_crop_profile"] = "Default: Maize (BOKU)"
        
    selected_index = profile_options.index(st.session_state["icrop2_selected_crop_profile"])
    
    selected_option = st.selectbox(
        "Select Crop Profile:",
        profile_options,
        index=selected_index
    )
    
    st.session_state["icrop2_selected_crop_profile"] = selected_option

    # Extract resolved crop parameters or set fallbacks if designing a new profile
    if selected_option == "➕ Create New Crop Profile...":
        crop_type = "Maize"
        active_profile = DEFAULT_CROP_PARAMETERS["Maize"].copy()
        
        st.subheader("📝 Design New Crop Profile")
        
        # --- Local OneDrive Cultivar Parameters Ingestion ---
        if is_onedrive_path_valid():
            with st.expander("📂 Ingest Cultivar Parameters from OneDrive", expanded=False):
                cal_files = list_onedrive_calibration_files()
                if cal_files:
                    selected_cal_file = st.selectbox(
                        "Select Calibration File",
                        options=cal_files,
                        help="Pick a crop calibration Excel sheet from local OneDrive reference directory."
                    )
                    if st.button("📥 Ingest and Pre-fill Parameters"):
                        try:
                            parsed_params = load_onedrive_calibration_file(selected_cal_file)
                            st.session_state["icrop2_new_crop_name"] = os.path.splitext(selected_cal_file)[0]
                            st.session_state["icrop2_new_tbd"] = parsed_params.get("TBD", 8.0)
                            st.session_state["icrop2_new_rue"] = parsed_params.get("IRUE", parsed_params.get("RUE", 1.6))
                            st.session_state["icrop2_new_sla"] = parsed_params.get("SLA", parsed_params.get("SpecificLeafArea", 0.022))
                            st.session_state["icrop2_new_produce_type"] = parsed_params.get("crop_produce_type", "Fruit/Seed")
                            st.session_state["icrop2_new_lifecycle_strategy"] = parsed_params.get("lifecycle_strategy", "Annual (Single-Season)")
                            st.session_state["icrop2_new_t_dormancy_trigger"] = parsed_params.get("t_dormancy_trigger", 5.0)
                            st.session_state["icrop2_new_t_base_winter"] = parsed_params.get("t_base_winter", 0.0)
                            st.success("✅ Parameters successfully ingested from local OneDrive file!")
                            st.rerun()
                        except Exception as ing_err:
                            st.error(f"Failed to ingest OneDrive calibration parameters: {ing_err}")
                else:
                    st.warning("⚠️ No valid calibration sheets found in local OneDrive directory.")
        
        # Initialize form state values
        if "icrop2_new_crop_name" not in st.session_state:
            st.session_state["icrop2_new_crop_name"] = ""
        if "icrop2_new_tbd" not in st.session_state:
            st.session_state["icrop2_new_tbd"] = 8.0
        if "icrop2_new_rue" not in st.session_state:
            st.session_state["icrop2_new_rue"] = 1.6
        if "icrop2_new_sla" not in st.session_state:
            st.session_state["icrop2_new_sla"] = 0.022
        if "icrop2_new_produce_type" not in st.session_state:
            st.session_state["icrop2_new_produce_type"] = "Fruit/Seed"
        if "icrop2_new_lifecycle_strategy" not in st.session_state:
            st.session_state["icrop2_new_lifecycle_strategy"] = "Annual (Single-Season)"
        if "icrop2_new_t_dormancy_trigger" not in st.session_state:
            st.session_state["icrop2_new_t_dormancy_trigger"] = 5.0
        if "icrop2_new_t_base_winter" not in st.session_state:
            st.session_state["icrop2_new_t_base_winter"] = 0.0

        with st.form("new_crop_form", clear_on_submit=True):
            new_crop_name = st.text_input(
                "Crop Name (e.g., 'Winter Wheat BOKU')", 
                value=st.session_state["icrop2_new_crop_name"],
                placeholder="Enter unique name..."
            )
            new_tbd = st.number_input(
                "Base Temperature (TBD - °C)", 
                value=st.session_state["icrop2_new_tbd"], 
                step=0.5
            )
            new_rue = st.number_input(
                "Max Radiation Use Efficiency (RUEmax - g/MJ)", 
                value=st.session_state["icrop2_new_rue"], 
                step=0.1, 
                min_value=0.5, 
                max_value=3.5
            )
            new_sla = st.number_input(
                "Specific Leaf Area (SLA - m²/g)", 
                value=st.session_state["icrop2_new_sla"], 
                format="%.4f", 
                step=0.001
            )
            
            produce_options = ["Fruit/Seed", "Tuber/Root", "Vegetative Foliage"]
            strategy_options = ["Annual (Single-Season)", "Multi-Year Accumulation", "Cyclical Perennial"]
            
            prod_idx = produce_options.index(st.session_state["icrop2_new_produce_type"]) if st.session_state["icrop2_new_produce_type"] in produce_options else 0
            strat_idx = strategy_options.index(st.session_state["icrop2_new_lifecycle_strategy"]) if st.session_state["icrop2_new_lifecycle_strategy"] in strategy_options else 0

            crop_produce_type = st.selectbox(
                "🌾 Primary Harvested Organ (Production Type):",
                options=produce_options,
                index=prod_idx,
                help="Select what component of the biomass constitutes the economic yield for this crop species."
            )
            lifecycle_strategy = st.selectbox(
                "⏳ Crop Lifecycle Growth Strategy:",
                options=strategy_options,
                index=strat_idx,
                help="Select the physiological lifecycle pattern. Multi-Year Accumulation keeps plants alive continuously. Cyclical Perennial resets fruit pools annually."
            )
            
            st.markdown("### ❄️ Winter & Dormancy Physiological Traits")
            t_dormancy_trigger = st.slider(
                "🍁 Leaf Senescence/Dormancy Trigger Temperature (°C):",
                min_value=-5.0, max_value=12.0, 
                value=float(st.session_state["icrop2_new_t_dormancy_trigger"]), 
                step=0.5,
                help="When the 5-day moving average temperature drops below this value, the canopy automatically goes dormant."
            )
            t_base_winter = st.slider(
                "🥶 Winter Base Metabolic Temperature (Tbase_winter, °C):",
                min_value=-2.0, max_value=5.0, 
                value=float(st.session_state["icrop2_new_t_base_winter"]), 
                step=0.5,
                help="The absolute temperature floor below which biological development stalls entirely for this crop."
            )
            
            publish_community = st.checkbox("🌐 Publish this calibrated crop variety to the community library", value=False)
            
            submit_btn = st.form_submit_button("Save and Register Crop Profile")
            
            if submit_btn:
                # Clear custom ingestion session states after save
                for k in ["icrop2_new_crop_name", "icrop2_new_tbd", "icrop2_new_rue", "icrop2_new_sla", "icrop2_new_produce_type", "icrop2_new_lifecycle_strategy", "icrop2_new_t_dormancy_trigger", "icrop2_new_t_base_winter"]:
                    if k in st.session_state:
                        del st.session_state[k]
                # Validation rules
                if not new_crop_name.strip():
                    st.error("Crop name cannot be empty.")
                else:
                    # Check against existing custom profiles to prevent unique constraint conflicts
                    existing_names = [dp["crop_name"].strip().lower() for dp in db_profiles]
                    existing_names.extend(["default: maize (boku)", "default: sorghum (boku)"])
                    if new_crop_name.strip().lower() in existing_names:
                        st.error(f"A crop profile named '{new_crop_name.strip()}' already exists. Please choose a unique name.")
                    else:
                        # Construct active C4 parameter set based on Maize default coefficients
                        new_params = DEFAULT_CROP_PARAMETERS["Maize"].copy()
                        new_params["TBD"] = new_tbd
                        new_params["RUE_MAX"] = new_rue
                        new_params["IRUE"] = new_rue
                        new_params["SLA"] = new_sla
                        new_params["crop_produce_type"] = crop_produce_type
                        new_params["lifecycle_strategy"] = lifecycle_strategy
                        new_params["t_dormancy_trigger"] = t_dormancy_trigger
                        new_params["t_base_winter"] = t_base_winter
                        
                        is_public_flag = 1 if publish_community else 0
                        created_by_user = st.session_state.icrop2_user_id
                        
                        try:
                            # Save directly to 'crops' table
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter, is_public, created_by_user_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (new_crop_name.strip(), "Custom", json.dumps(new_params), crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter, is_public_flag, created_by_user))
                                conn.commit()
                                
                            st.toast("✅ New Crop Profile Registered Successfully!")
                            
                            # Update selected focus dynamically
                            if is_public_flag:
                                newly_created_label = f"🌐 Public Custom: {new_crop_name.strip()} (Custom)"
                            else:
                                newly_created_label = f"🔒 Private Custom: {new_crop_name.strip()} (Custom)"
                            st.session_state["icrop2_selected_crop_profile"] = newly_created_label
                            st.rerun()
                        except Exception as save_err:
                            st.error(f"Failed to register new crop profile: {save_err}")
                            
        default_lat = st.session_state.get("icrop2_lat_key", 21.0285)
        default_lon = st.session_state.get("icrop2_lon_key", 105.8542)
    else:
        resolved_profile = profile_map[selected_option]
        crop_type = resolved_profile["crop_type"]
        active_profile = resolved_profile["parameters"].copy()
        
        # 2. Add File Uploader for Custom parameters
        uploaded_crop_file = st.file_uploader(
            "Upload Custom Parameters (Excel/JSON)",
            type=["xls", "xlsm", "xlsx", "json"],
            help="Upload custom parameter templates to override baseline coefficients dynamically."
        )
        
        if uploaded_crop_file is not None:
            try:
                if uploaded_crop_file.name.endswith(".json"):
                    custom_dict = json.load(uploaded_crop_file)
                else:
                    custom_dict = parse_crop_parameters(uploaded_crop_file)
                    
                # Validate uploaded parameters
                validated = router.validate_custom_parameters(custom_dict)
                active_profile.update(validated)
                st.success("Custom parameters merged & validated successfully!")
            except Exception as e:
                st.error(f"Failed to merge custom parameters: {e}")
    
        # 3. Add sliders for on-screen real-time scenario tweaking
        st.subheader("🛠️ Tweak Physiological Coefficients")
        with st.expander("Adjust Engine Parameter Bounds", expanded=True):
            tweak_tbd = st.slider(
                "Base Temperature (TBD, °C)",
                min_value=0.0,
                max_value=15.0,
                value=float(active_profile.get("TBD", 8.0)),
                step=0.5,
                help="Minimum temperature threshold at which phenology development ceases."
            )
            tweak_rue = st.slider(
                "Radiation Use Efficiency (RUE_MAX, g/MJ)",
                min_value=1.0,
                max_value=5.0,
                value=float(active_profile.get("RUE_MAX", 3.5)),
                step=0.1,
                help="Maximum dry matter accumulated per unit of absorbed solar PAR."
            )
            tweak_sla = st.slider(
                "Specific Leaf Area (SLA, m²/g)",
                min_value=0.005,
                max_value=0.08,
                value=float(active_profile.get("SLA", 0.022)),
                step=0.001,
                help="Leaf area expansion per unit leaf dry weight."
            )
            
            # Apply slide tweaks to active profile
            active_profile["TBD"] = tweak_tbd
            active_profile["RUE_MAX"] = tweak_rue
            active_profile["IRUE"] = tweak_rue
            active_profile["SLA"] = tweak_sla
            
            # Validate adjusted values
            try:
                active_profile = router.validate_custom_parameters(active_profile)
            except ValueError as err:
                st.error(f"Coefficient conflict: {err}")
    
        # 4. Save tweaked profiles to Cloud Database
        st.subheader("💾 Save Profile to Cloud")
        with st.expander("Save Current Profile", expanded=False):
            new_profile_name = st.text_input("Profile Name", placeholder="e.g. Maize-Hybrid-Iowa")
            publish_community_tweak = st.checkbox("🌐 Publish this calibrated crop variety to the community library", value=False, key="tweak_publish_cb")
            is_public_flag = 1 if publish_community_tweak else 0
            created_by_user = st.session_state.icrop2_user_id
            
            if st.button("Save Profile"):
                if not new_profile_name.strip():
                    st.error("Please enter a valid profile name.")
                else:
                    try:
                        # Save directly to 'crops' table
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter, is_public, created_by_user_id)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (new_profile_name.strip(), "Custom", json.dumps(active_profile), active_profile.get("crop_produce_type", "Fruit/Seed"), active_profile.get("lifecycle_strategy", "Annual (Single-Season)"), active_profile.get("t_dormancy_trigger", 5.0), active_profile.get("t_base_winter", 0.0), is_public_flag, created_by_user))
                            conn.commit()
                        
                        st.success(f"Successfully saved profile '{new_profile_name}'!")
                        if is_public_flag:
                            st.session_state["icrop2_selected_crop_profile"] = f"🌐 Public Custom: {new_profile_name.strip()} (Custom)"
                        else:
                            st.session_state["icrop2_selected_crop_profile"] = f"🔒 Private Custom: {new_profile_name.strip()} (Custom)"
                        st.rerun()
                    except Exception as save_err:
                        st.error(f"Failed to save profile: {save_err}")
    
        # 5. Interactive Simulation Presets
        st.subheader("📍 Location Presets")
        presets_list = ["Custom Coordinates", "Gerasdorf, Austria (Wheat/Maize Study)", "Iowa, USA (Maize Belt)", "Mekong Delta, Vietnam (Rice/Crops)"]
        
        # Dynamically deduce preset from active coordinates to prevent state drift
        active_lat = st.session_state.get("icrop2_lat_key", 21.0285)
        active_lon = st.session_state.get("icrop2_lon_key", 105.8542)
        if abs(active_lat - 48.2830) < 1e-4 and abs(active_lon - 16.4670) < 1e-4:
            preset_val = "Gerasdorf, Austria (Wheat/Maize Study)"
        elif abs(active_lat - 42.0300) < 1e-4 and abs(active_lon - -93.6310) < 1e-4:
            preset_val = "Iowa, USA (Maize Belt)"
        elif abs(active_lat - 10.0330) < 1e-4 and abs(active_lon - 105.7830) < 1e-4:
            preset_val = "Mekong Delta, Vietnam (Rice/Crops)"
        else:
            preset_val = "Custom Coordinates"
            
        preset_index = presets_list.index(preset_val)
        preset = st.selectbox(
            "Choose Region Preset:",
            presets_list,
            index=preset_index
        )
        
        # Update coordinates only if preset selected changes
        if preset != preset_val:
            if preset == "Gerasdorf, Austria (Wheat/Maize Study)":
                st.session_state["icrop2_lat_key"], st.session_state["icrop2_lon_key"] = 48.2830, 16.4670
            elif preset == "Iowa, USA (Maize Belt)":
                st.session_state["icrop2_lat_key"], st.session_state["icrop2_lon_key"] = 42.0300, -93.6310
            elif preset == "Mekong Delta, Vietnam (Rice/Crops)":
                st.session_state["icrop2_lat_key"], st.session_state["icrop2_lon_key"] = 10.0330, 105.7830
            elif preset == "Custom Coordinates":
                st.session_state["icrop2_lat_key"], st.session_state["icrop2_lon_key"] = 21.0285, 105.8542
            st.session_state["latitude"] = st.session_state["icrop2_lat_key"]
            st.session_state["longitude"] = st.session_state["icrop2_lon_key"]
            st.rerun()
            
        default_lat = st.session_state["icrop2_lat_key"]
        default_lon = st.session_state["icrop2_lon_key"]
        
    # Persistent Copyright notice at the bottom of the sidebar layout
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #888888; font-size: 0.85rem; font-weight: 500; margin-top: 1rem;'>"
        "Copyright of Icrop by Dr Amad Manschadi"
        "</div>", 
        unsafe_allow_html=True
    )

# Unconditional fallback: ensure default_lat/default_lon are always defined
# regardless of which sidebar branch (Create Profile vs existing profile) was taken.
default_lat = st.session_state.get("icrop2_lat_key", 21.0285)
default_lon = st.session_state.get("icrop2_lon_key", 105.8542)

# Create Two-Column Layout for Main Panel
col_left, col_right = st.columns([1, 1.2], gap="large")

# ----------------- LEFT COLUMN: DUAL-WEATHER CONFIGURATION -----------------
with col_left:
    st.subheader("⚙️ Simulation Settings")
    
    # Model Simulation Fidelity selectbox
    sim_mode_selection = st.selectbox(
        "Select Model Simulation Fidelity", 
        ["Original SSM-iCrop (Potential Yield)", "Advanced Agro-Climate Model (Stress Limited)"],
        index=1,  # Default to Advanced
        key="icrop2_sim_mode_selection",
        help="Choose 'Original SSM-iCrop (Potential Yield)' to run textbook potential yields bypass soil moisture/nutrient stresses entirely, or select 'Advanced' for full biophysical environmental simulation."
    )
    engine_mode = "Classic" if "Original" in sim_mode_selection else "Advanced"
    is_potential_mode = "Original" in sim_mode_selection
    
    advanced_options = {}
    if engine_mode == "Advanced":
        with st.expander("🛠️ Advanced Biophysical Process Selectors", expanded=True):
            use_vpd = st.checkbox(
                "Enable Vapor Pressure Deficit (VPD) Stress", 
                value=True, 
                help="Reduces Radiation Use Efficiency and dynamically increases drought stress thresholds under high atmospheric demand."
            )
            use_leaching = st.checkbox(
                "Enable Nitrogen Leaching via Drainage", 
                value=True, 
                help="Simulates Nitrogen chemical washout during heavy rain or drainage events."
            )
            use_root_growth = st.checkbox(
                "Enable Dynamic Phased Root Growth", 
                value=True, 
                help="Expands root depth dynamically, sizing active soil capacity proportionally."
            )
            use_heat_shock = st.checkbox(
                "Enable Pollination Heat Shock", 
                value=True, 
                help="Accumulates pollen sterility under extreme temperatures (>35°C) during anthesis."
            )
            advanced_options = {
                "use_vpd": use_vpd,
                "use_leaching": use_leaching,
                "use_root_growth": use_root_growth,
                "use_heat_shock": use_heat_shock
            }
    
    sim_years = 1
    st.markdown("##### 1. Meteorological Ingestion Engine")
    weather_options = [
        "🌐 Use System Weather (Auto-Fetch via Coordinates/Map)", 
        "📁 Upload My Own Weather Data File (.csv / .xlsx)"
    ]
    
    weather_source = st.radio(
        "Select Weather Data Source",
        weather_options
    )
    
    weather_df = None
    uploaded_lat = None
    uploaded_lon = None
    selected_w_file = None
    
    if "📁 Upload My Own Weather" in weather_source:
        uploaded_weather_file = st.file_uploader(
            "Drag and drop your SSM weather file here",
            type=["xls", "xlsx", "txt", "csv"],
            help="Upload a standard BOKU weather spreadsheet (.xls) or raw text file containing headers."
        )
        if uploaded_weather_file is not None:
            try:
                weather_df, uploaded_lat, uploaded_lon = WeatherProcessor.parse_ssm_weather_file(uploaded_weather_file)
                st.success(f"Successfully loaded {len(weather_df)} weather days!")
                if uploaded_lat is not None and uploaded_lon is not None:
                    st.info(f"📍 Extracted header coordinates: Lat = {uploaded_lat:.3f}, Lon = {uploaded_lon:.3f}")
            except Exception as e:
                st.error(f"Weather parsing error: {e}")
    elif "📂 Load Weather from OneDrive" in weather_source:
        weather_files = list_onedrive_weather_files()
        if weather_files:
            selected_w_file = st.selectbox(
                "Select OneDrive Weather File",
                options=weather_files,
                help="Pick a pre-loaded BOKU weather spreadsheet from your local OneDrive Weather folder."
            )
            if selected_w_file:
                try:
                    weather_df, uploaded_lat, uploaded_lon = load_onedrive_weather_file(selected_w_file)
                    st.success(f"Successfully loaded {len(weather_df)} weather days from OneDrive: {selected_w_file}")
                    if uploaded_lat is not None and uploaded_lon is not None:
                        st.info(f"📍 Extracted coordinates: Lat = {uploaded_lat:.3f}, Lon = {uploaded_lon:.3f}")
                except Exception as e:
                    st.error(f"Failed to read OneDrive weather file: {e}")
        else:
            st.warning("⚠️ No valid weather sheets found in the OneDrive Weather directory.")
    else:
        # Option 1: System Weather Ingestion Conditional Layout
        st.markdown("##### 2. Interactive Map (Click to Select Coordinates)")
        
        # 1. WIDGET KEY STATE SEEDING
        if "latitude" not in st.session_state:
            st.session_state["latitude"] = 21.0285
        if "longitude" not in st.session_state:
            st.session_state["longitude"] = 105.8542
        if "icrop2_lat_key" not in st.session_state:
            st.session_state["icrop2_lat_key"] = st.session_state["latitude"]
        if "icrop2_lon_key" not in st.session_state:
            st.session_state["icrop2_lon_key"] = st.session_state["longitude"]
            
        # 2. DECOUPLED FOLIUM ENGINE RENDERING
        m = folium.Map(
            location=[st.session_state["latitude"], st.session_state["longitude"]], 
            zoom_start=6
        )
        
        # Add dynamic marker precisely at target coordinates
        folium.Marker(
            location=[st.session_state["latitude"], st.session_state["longitude"]],
            popup=f"Active Location: {st.session_state['latitude']:.4f}, {st.session_state['longitude']:.4f}",
            tooltip="Click anywhere on the map to select new coordinates",
            icon=folium.Icon(color="green", icon="info-sign")
        ).add_to(m)
        
        # Render component inside st_folium with explicit center and zoom
        map_data = st_folium(
            m,
            center=[st.session_state["latitude"], st.session_state["longitude"]],
            zoom=6,
            width=700,
            height=450,
            key="icrop2_folium_map"
        )
        
        # 3. INTERCEPT AND PARSE MAP CLICKS SECURELY ACROSS RERUNS (Deferred Soil Fetching)
        if st.session_state.get("icrop2_folium_map") and "last_clicked" in st.session_state["icrop2_folium_map"]:
            click_data = st.session_state["icrop2_folium_map"]["last_clicked"]
            if click_data:
                new_lat = click_data.get("lat", st.session_state["latitude"])
                new_lon = click_data.get("lng", st.session_state["longitude"])
                
                # If map click provides new values, update session states without auto-fetching soil (deferred to button)
                if new_lat != st.session_state["latitude"] or new_lon != st.session_state["longitude"]:
                    st.session_state["latitude"] = new_lat
                    st.session_state["longitude"] = new_lon
                    st.session_state["icrop2_lat_key"] = new_lat
                    st.session_state["icrop2_lon_key"] = new_lon
                    st.rerun()

        # 4. BALANCED NUMERIC ENTRY SYNC BINDING DIRECTLY TO PERSISTENT STATE KEYS
        c_lat, c_lon = st.columns(2)
        
        manual_lat = c_lat.number_input(
            "Latitude", 
            format="%.4f", 
            value=float(st.session_state["latitude"]),
            key="manual_latitude_input"
        )
        manual_lon = c_lon.number_input(
            "Longitude", 
            format="%.4f", 
            value=float(st.session_state["longitude"]),
            key="manual_longitude_input"
        )
        
        # Sync manually typed coordinates immediately to session states
        if manual_lat != st.session_state["latitude"]:
            st.session_state["latitude"] = manual_lat
            st.session_state["icrop2_lat_key"] = manual_lat
            st.rerun()
            
        if manual_lon != st.session_state["longitude"]:
            st.session_state["longitude"] = manual_lon
            st.session_state["icrop2_lon_key"] = manual_lon
            st.rerun()
        
        # --- Soil Data Failover/Override System Interface ---
        st.markdown("##### ⚙️ Soil Data Source & Failover Settings")
        
        # Check if isric_available key exists in session state
        if "isric_available" not in st.session_state:
            st.session_state["isric_available"] = True
            
        # 1. API Availability Display Alert
        if not st.session_state["isric_available"]:
            st.error("⚠️ ISRIC Soil Database is temporarily offline. Please select an alternate data source below.")
            soil_source_selection = st.radio(
                "Select Failover Soil Data Source:",
                ["Use BOKU Fallback Data", "Input My Own Measured Soil Parameters"],
                key="icrop2_failover_soil_source"
            )
        else:
            soil_source_selection = "ISRIC API"
            
        # 2. Universal Override Checkbox
        st.session_state["icrop2_soil_universal_override"] = st.checkbox(
            "✍️ Override with manual soil core measurements",
            value=st.session_state.get("icrop2_soil_universal_override", False),
            help="Check this box to bypass cloud soil databases (ISRIC/BOKU) and input your exact field core parameters for 5 distinct layers."
        )

        # Expose individual soil layers override table/columns if checked or selected
        if st.session_state["icrop2_soil_universal_override"] or (not st.session_state["isric_available"] and soil_source_selection == "Input My Own Measured Soil Parameters"):
            st.markdown("##### 🔬 Manual Soil Core Measurements (5 Layers)")
            st.info("Input soil physical parameters for 5 distinct horizons. These values directly shape the tipping-bucket simulation loop.")
            
            # Setup layer table header columns
            hdr_cols = st.columns(5)
            dlyers = []
            duls = []
            pwps = []
            wls = []
            
            # Layer standard defaults
            default_thicknesses = [150.0, 150.0, 300.0, 300.0, 300.0]
            default_duls = [0.28, 0.28, 0.26, 0.26, 0.24]
            default_pwps = [0.12, 0.12, 0.11, 0.11, 0.10]
            default_wls = [0.20, 0.20, 0.18, 0.18, 0.16]
            
            for idx in range(5):
                with hdr_cols[idx]:
                    st.markdown(f"**Horizon {idx+1}**")
                    dl = st.number_input(
                        "Thick (mm)", 
                        min_value=10.0, max_value=1000.0, 
                        value=float(st.session_state.get(f"override_dlyer_{idx}", default_thicknesses[idx])), 
                        key=f"override_dlyer_{idx}"
                    )
                    dul = st.number_input(
                        "DUL (vol)", 
                        min_value=0.05, max_value=0.50, 
                        value=float(st.session_state.get(f"override_dul_{idx}", default_duls[idx])), 
                        format="%.3f", 
                        key=f"override_dul_{idx}"
                    )
                    pwp = st.number_input(
                        "PWP (vol)", 
                        min_value=0.01, max_value=0.40, 
                        value=float(st.session_state.get(f"override_pwp_{idx}", default_pwps[idx])), 
                        format="%.3f", 
                        key=f"override_pwp_{idx}"
                    )
                    wl = st.number_input(
                        "Init (vol)", 
                        min_value=0.01, max_value=0.50, 
                        value=float(st.session_state.get(f"override_wl_{idx}", default_wls[idx])), 
                        format="%.3f", 
                        key=f"override_wl_{idx}"
                    )
                    dlyers.append(dl)
                    duls.append(dul)
                    pwps.append(pwp)
                    wls.append(wl)
                    
        # Local compatibility mapping for downstream simulation and weather API components
        lat = st.session_state["latitude"]
        lon = st.session_state["longitude"]
        
        # Date range timeframe selector
        st.markdown("##### 3. Simulation Timeframe")
        min_val = datetime.date(1940, 1, 1)
        max_val = datetime.date(2026, 12, 31)
        
        timeframe_input = st.date_input(
            "Select Simulation Timeframe",
            [datetime.date(2020, 1, 1), datetime.date(2020, 12, 31)],
            min_value=min_val,
            max_value=max_val,
            help="Select a simulation period. Global reanalysis data is available from 1940 to 2026."
        )
        
        if isinstance(timeframe_input, (list, tuple)) and len(timeframe_input) == 2:
            start_date, end_date = timeframe_input
        else:
            start_date = timeframe_input[0] if isinstance(timeframe_input, (list, tuple)) and len(timeframe_input) > 0 else timeframe_input
            end_date = start_date
        sim_years = max(1, end_date.year - start_date.year + 1)
    
    # 4. Sowing Configuration and Time Slicing
    st.markdown("##### 4. Sowing Window & Time Slicing")
    
    # Extract available years dynamically
    available_years = []
    if "🌐 Use System Weather" in weather_source:
        if 'start_date' in locals() and 'end_date' in locals():
            available_years = list(range(start_date.year, end_date.year + 1))
        else:
            available_years = [2020]
    else:
        if weather_df is not None:
            available_years = WeatherTimeSlicer.get_available_years(weather_df)
            
    if available_years:
        total_years = len(available_years)
        st.info(f"📅 Ingested Weather Timeline: {total_years} Year(s) detected ({available_years[0]} to {available_years[-1]}).")
    else:
        st.info("📅 Ingested Weather Timeline: No weather data detected. Upload weather data or configure coordinates first.")
        
    sowing_doy = st.number_input(
        "Sowing Day of Year (DOY)",
        min_value=1,
        max_value=365,
        value=120,
        step=1,
        help="Sowing day of the year (1 to 365). Day 120 corresponds to April 30th."
    )
    
    # Calculate human-readable date
    sow_doy_date = datetime.date(2025, 1, 1) + datetime.timedelta(days=sowing_doy - 1)
    sow_date_str = sow_doy_date.strftime("%B %d")
    st.info(f"📅 Day {sowing_doy} corresponds to {sow_date_str}")

    # 1. STRUCTURED SOIL PARAMETER EXPANDER
    with st.expander("🌱 Configure Local Soil Profile Settings", expanded=False):
        # Explicit SoilGrids API fetch button to prevent automatic resets on map clicks
        if st.button("📥 Download Soil Profile from ISRIC SoilGrids", key="download_soil_profile_btn", help="Fetch physical soil properties (Organic Matter, PAWC, Depth) from global ISRIC SoilGrids dataset for the current active coordinates."):
            with st.spinner("Fetching global ISRIC SoilGrids grid profile characteristics..."):
                try:
                    from utils.soil_handler import fetch_isric_soil_data_with_failover
                    isric_profile = fetch_isric_soil_data_with_failover(st.session_state["latitude"], st.session_state["longitude"])
                    if isric_profile:
                        # Map to UI states
                        st.session_state["icrop2_som_key"] = isric_profile.get("organic_matter", 0.025) * 100.0
                        st.session_state["icrop2_pawc_key"] = isric_profile.get("Soil_Water_Capacity", 180.0) / 1.2
                        st.session_state["icrop2_depth_key"] = int(isric_profile.get("Max_Root_Depth", 1200))
                        
                        if not st.session_state.get("isric_available", True):
                            st.toast("⚠️ ISRIC Soil Database is temporarily offline. BOKU local fallback loaded.", icon="🌍")
                        else:
                            st.toast("✅ Soil profile successfully updated from ISRIC SoilGrids!", icon="🌍")
                        st.rerun()
                except Exception as fetch_err:
                    st.error(f"Soil fetch error: {fetch_err}")
                    
        st.markdown("---")

        soil_depth = st.number_input(
            "Total Root Zone Depth (mm)", 
            min_value=100, 
            max_value=3000, 
            value=int(st.session_state.get("icrop2_depth_key", 1200)),
            step=50,
            key="depth_key",
            help="Total vertical thickness of the active crop rooting profile."
        )
        soil_initial_water = st.number_input(
            "Initial Soil Water Content (% Volumetric)", 
            min_value=0.0, 
            max_value=50.0, 
            value=float(st.session_state.get("icrop2_initial_water_key", 25.0)),
            step=1.0,
            key="initial_water_key",
            help="Starting volumetric water content at the time of sowing."
        )
        soil_pawc = st.number_input(
            "Plant Available Water Capacity (PAWC) (mm/m)", 
            min_value=10.0, 
            max_value=300.0, 
            value=float(st.session_state.get("icrop2_pawc_key", 150.0)),
            step=5.0,
            key="pawc_key",
            help="Maximum amount of water the soil profile can hold for plant extraction."
        )
        soil_som = st.number_input(
            "Soil Organic Matter (SOM) (%)", 
            min_value=0.1, 
            max_value=10.0, 
            value=float(st.session_state.get("icrop2_som_key", 2.5)),
            step=0.1,
            key="som_key",
            help="Percentage of organic matter in topsoil."
        )
        
        # Keep keys synchronized when user manually updates the inputs
        st.session_state["icrop2_depth_key"] = soil_depth
        st.session_state["icrop2_initial_water_key"] = soil_initial_water
        st.session_state["icrop2_pawc_key"] = soil_pawc
        st.session_state["icrop2_som_key"] = soil_som

    # 2. CROP NUTRITION & FERTILIZER SCHEDULES (Dynamic Rows)
    with st.expander("🧪 Crop Nutrition & Fertilizer Management", expanded=False):
        if is_potential_mode:
            st.warning("⚠️ **Note:** You are currently in **Potential Yield Mode**. Under this textbook configuration, the engine assumes infinite soil nutrients. Your NPK rounds below will be recorded but will **not** alter the biomass curve. Switch to **Advanced Agro-Climate Mode** to simulate nutrient deficiencies.")
        col_add, col_remove = st.columns(2)
        if col_add.button("➕ Add Fertilizer Round", key="add_fert_round_btn"):
            st.session_state.icrop2_fertilizer_rounds.append(
                {"doy": 120, "n": 0.0, "p": 0.0, "k": 0.0, "method": "Broadcast"}
            )
            st.rerun()

        if col_remove.button("➖ Remove Last Round", key="remove_fert_round_btn"):
            if len(st.session_state.icrop2_fertilizer_rounds) > 0:
                st.session_state.icrop2_fertilizer_rounds.pop()
                st.rerun()

        if len(st.session_state.icrop2_fertilizer_rounds) == 0:
            st.info("ℹ️ No scheduled operations added yet. Click '➕ Add Round' below to configure an application event.")
        else:
            for idx, round_item in enumerate(st.session_state.icrop2_fertilizer_rounds):
                st.markdown(f"**Round {idx+1}**")
                cols = st.columns(5)
                
                doy = cols[0].number_input(
                    "DOY", 
                    min_value=1, 
                    max_value=365, 
                    value=int(round_item["doy"]), 
                    key=f"fert_doy_{idx}"
                )
                n = cols[1].number_input(
                    "N (kg/ha)", 
                    min_value=0.0, 
                    max_value=500.0, 
                    value=float(round_item["n"]), 
                    key=f"fert_n_{idx}"
                )
                p = cols[2].number_input(
                    "P₂O₅ (kg/ha)", 
                    min_value=0.0, 
                    max_value=300.0, 
                    value=float(round_item["p"]), 
                    key=f"fert_p_{idx}"
                )
                k = cols[3].number_input(
                    "K₂O (kg/ha)", 
                    min_value=0.0, 
                    max_value=300.0, 
                    value=float(round_item["k"]), 
                    key=f"fert_k_{idx}"
                )
                method = cols[4].selectbox(
                    "Method", 
                    ["Broadcast", "Banding", "Fertigation", "Foliar"],
                    index=["Broadcast", "Banding", "Fertigation", "Foliar"].index(round_item["method"]) if round_item["method"] in ["Broadcast", "Banding", "Fertigation", "Foliar"] else 0,
                    key=f"fert_method_{idx}"
                )
                
                round_item["doy"] = doy
                round_item["n"] = n
                round_item["p"] = p
                round_item["k"] = k
                round_item["method"] = method
                
    # 3. IRRIGATION & DRAINAGE WATER REGIME CONTROL (Dynamic Rows)
    with st.expander("💧 Water Management (Irrigation & Drainage)", expanded=False):
        if is_potential_mode:
            st.warning("⚠️ **Note:** You are currently in **Potential Yield Mode**. The engine assumes perfect, non-limiting soil moisture conditions. Your irrigation schedule below will **not** alter the growth matrix. Switch to **Advanced Agro-Climate Mode** to activate drought/waterlogging physics.")
        st.selectbox(
            "Irrigation Mode",
            ["Rainfed / Manual Scheduler", "Automatic Irrigation (Maintain >50% Soil Moisture)"],
            key="auto_irrigation_key",
            help="Choose 'Rainfed / Manual Scheduler' to run simulation under natural rainfall and any manually configured irrigation events, or select 'Automatic' to automatically irrigate back to field capacity whenever root zone moisture falls below 50% capacity."
        )
        st.markdown("---")
        st.markdown("##### 🚿 Irrigation Events Scheduler")
        col_irr_add, col_irr_remove = st.columns(2)
        if col_irr_add.button("➕ Add Irrigation Round", key="add_irr_round_btn"):
            st.session_state.icrop2_irrigation_rounds.append(
                {"doy": 130, "amount": 0.0, "type": "Drip"}
            )
            st.rerun()

        if col_irr_remove.button("➖ Remove Last Irrigation", key="remove_irr_round_btn"):
            if len(st.session_state.icrop2_irrigation_rounds) > 0:
                st.session_state.icrop2_irrigation_rounds.pop()
                st.rerun()

        if len(st.session_state.icrop2_irrigation_rounds) == 0:
            st.info("ℹ️ No scheduled operations added yet. Click '➕ Add Round' below to configure an application event.")
        else:
            for idx, round_item in enumerate(st.session_state.icrop2_irrigation_rounds):
                st.markdown(f"**Irrigation Event {idx+1}**")
                cols = st.columns(3)
                
                doy = cols[0].number_input(
                    "DOY", 
                    min_value=1, 
                    max_value=365, 
                    value=int(round_item["doy"]), 
                    key=f"irr_doy_{idx}"
                )
                amount = cols[1].number_input(
                    "Amount (mm)", 
                    min_value=0.0, 
                    max_value=200.0, 
                    value=float(round_item["amount"]), 
                    key=f"irr_amount_{idx}"
                )
                sys_type = cols[2].selectbox(
                    "System Type", 
                    ["Drip", "Sprinkler", "Flood"],
                    index=["Drip", "Sprinkler", "Flood"].index(round_item["type"]) if round_item["type"] in ["Drip", "Sprinkler", "Flood"] else 0,
                    key=f"irr_type_{idx}"
                )
                
                round_item["doy"] = doy
                round_item["amount"] = amount
                round_item["type"] = sys_type

        st.markdown("---")
        st.markdown("##### 📐 Drainage Operations Scheduler")
        col_drn_add, col_drn_remove = st.columns(2)
        if col_drn_add.button("➕ Add Drainage Setup", key="add_drn_round_btn"):
            st.session_state.icrop2_drainage_rounds.append(
                {"doy": 150, "rate": 0.0, "type": "Surface Runoff"}
            )
            st.rerun()

        if col_drn_remove.button("➖ Remove Last Drainage", key="remove_drn_round_btn"):
            if len(st.session_state.icrop2_drainage_rounds) > 0:
                st.session_state.icrop2_drainage_rounds.pop()
                st.rerun()

        if len(st.session_state.icrop2_drainage_rounds) == 0:
            st.info("ℹ️ No scheduled operations added yet. Click '➕ Add Round' below to configure an application event.")
        else:
            for idx, round_item in enumerate(st.session_state.icrop2_drainage_rounds):
                st.markdown(f"**Drainage Operation {idx+1}**")
                cols = st.columns(3)
                
                doy = cols[0].number_input(
                    "Start DOY", 
                    min_value=1, 
                    max_value=365, 
                    value=int(round_item["doy"]), 
                    key=f"drn_doy_{idx}"
                )
                rate = cols[1].number_input(
                    "Release Rate (mm/day)", 
                    min_value=0.0, 
                    max_value=100.0, 
                    value=float(round_item["rate"]), 
                    key=f"drn_rate_{idx}"
                )
                drn_type = cols[2].selectbox(
                    "Infrastructure Type", 
                    ["Surface Runoff", "Tile Drainage", "Subsurface"],
                    index=["Surface Runoff", "Tile Drainage", "Subsurface"].index(round_item["type"]) if round_item["type"] in ["Surface Runoff", "Tile Drainage", "Subsurface"] else 0,
                    key=f"drn_type_{idx}"
                )
                
                round_item["doy"] = doy
                round_item["rate"] = rate
                round_item["type"] = drn_type

    with st.expander("🛠️ View Current Coefficients (Active Matrix)", expanded=False):
        st.json(active_profile)

    # Simulation Trigger Button & Scenario Label
    c_btn, c_name = st.columns([1.5, 1])
    with c_name:
        scenario_name = st.text_input(
            "Scenario Label",
            value=f"Run #{len(st.session_state.get('icrop2_sim_history', {})) + 1}",
            help="Enter a unique tag name to save this simulation run in history."
        )
    # Check active storage limits
    current_saved_runs = len(db.get_simulation_runs(st.session_state.icrop2_user_id))
    limit_reached = current_saved_runs >= st.session_state.icrop2_run_limit
    
    if limit_reached:
        st.error(f"⚠️ **Storage Limit Reached ({current_saved_runs}/{st.session_state.icrop2_run_limit} runs):** You must delete old simulations in **My Research Workspace** before executing new runs.")
        run_btn = False
    else:
        with c_btn:
            run_btn = st.button("🚀 Run SSM-iCrop Simulation", width='stretch')

# ----------------- RIGHT COLUMN: CHARTS & METRICS VIEWPORT -----------------
with col_right:
    st.markdown(
        """
        <div style="display: flex; align-items: center; margin-bottom: 20px;">
            <span style="font-size: 28px; font-weight: 800; color: #1E3A8A; font-family: 'Inter', sans-serif; letter-spacing: -0.5px;">
                🌱 SSM-iCrop<span style="color: #10B981;">2</span>
            </span>
            <span style="margin-left: 12px; padding: 3px 8px; font-size: 11px; font-weight: 600; color: #047857; background-color: #D1FAE5; border-radius: 12px; font-family: 'Inter', sans-serif;">
                v2.0 Core
            </span>
        </div>
        """, 
        unsafe_allow_html=True
    )
    nav_tabs = ["📊 Simulation Dashboard", "🔄 Scenario Comparison", "👤 My Research Workspace", "🔬 Calibration Wizard"]
    if st.session_state.get("icrop2_user_tier") == "Admin":
        nav_tabs.append("🛡️ Admin Control Panel")
        
    tabs = st.tabs(nav_tabs)
    tab_sim = tabs[0]
    tab_comp = tabs[1]
    tab_workspace = tabs[2]
    tab_calibration = tabs[3]
    if st.session_state.get("icrop2_user_tier") == "Admin":
        tab_admin = tabs[4]
    
    with tab_sim:
        metrics_placeholder = st.empty()
        chart1_placeholder = st.empty()
        chart2_placeholder = st.empty()
        chart3_placeholder = st.empty()
        status_placeholder = st.empty()
        
        # Enforce email verification lockout
        if st.session_state.icrop2_is_verified == 0:
            st.warning("⚠️ **Email Verification Pending:** Your account has not been activated. Please check your email inbox to verify your account and unlock the crop simulation dashboard.")
            
            # Local debug helper: display mailbox simulator
            my_emails = [m for m in LOCAL_MAILBOX_SIMULATOR if m["to"] == st.session_state.icrop2_email]
            if my_emails and not is_smtp_configured():
                with st.expander("📬 Local Mailbox Simulator (Debug Account Verification)", expanded=True):
                    st.info("Verification emails found in local memory cache:")
                    for m in my_emails:
                        st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                        lnks = re.findall(r'href="(.*?)"', m["body_html"])
                        if lnks:
                            st.markdown(f"[🔗 Verify My Account Link]({lnks[0]})")
            st.stop()
        
        # Initial Landing Page wireframe
        if not run_btn and not st.session_state.icrop2_simulation_run_active:
            with metrics_placeholder.container():
                m1, m2, m3 = st.columns(3)
                m1.markdown('<div class="metric-card"><div class="metric-label">Max LAI</div><div class="metric-value">-</div></div>', unsafe_allow_html=True)
                m2.markdown('<div class="metric-card"><div class="metric-label">Biomass (t/ha)</div><div class="metric-value">-</div></div>', unsafe_allow_html=True)
                m3.markdown('<div class="metric-card"><div class="metric-label">Grain Yield (t/ha)</div><div class="metric-value">-</div></div>', unsafe_allow_html=True)
            
            with chart1_placeholder.container():
                st.image(
                    "https://images.unsplash.com/photo-1574323347407-f5e1ad6d020b?auto=format&fit=crop&w=800&q=80",
                    caption="Click 'Run SSM-iCrop Simulation' to execute BOKU crop physiological model.",
                    width='stretch'
                )
        else:
            # EXECUTE SIMULATION CYCLE OR RESTORE FROM SESSION STATE
            try:
                if run_btn:
                    # Compile unified agricultural management payload
                    # Use session state fallbacks in case widgets weren't explicitly rendered
                    soil_config = {
                        "depth_mm": st.session_state.get("icrop2_depth_key", 1200),
                        "initial_water_percent": st.session_state.get("icrop2_initial_water_key", 25.0),
                        "pawc_mm_m": st.session_state.get("icrop2_pawc_key", 150.0),
                        "som_percent": st.session_state.get("icrop2_som_key", 2.5)
                    }
                    
                    fertilizer_schedule = [
                        {
                            "doy": int(item["doy"]),
                            "nitrogen_kg_ha": float(item["n"]),
                            "phosphorus_kg_ha": float(item["p"]),
                            "potassium_kg_ha": float(item["k"]),
                            "method": item["method"]
                        }
                        for item in st.session_state.icrop2_fertilizer_rounds
                    ]
                    
                    water_management = {
                        "auto_irrigation": "Automatic" in st.session_state.get("icrop2_auto_irrigation_key", "Rainfed / Manual Scheduler"),
                        "irrigation": [
                            {
                                "doy": int(item["doy"]),
                                "water_applied_mm": float(item["amount"]),
                                "system_type": item["type"]
                            }
                            for item in st.session_state.icrop2_irrigation_rounds
                        ],
                        "drainage": [
                            {
                                "start_doy": int(item["doy"]),
                                "release_rate_mm_day": float(item["rate"]),
                                "infrastructure_type": item["type"]
                            }
                            for item in st.session_state.icrop2_drainage_rounds
                        ]
                    }
                    
                    # Combine into unified package
                    management_payload = {
                        "soil": soil_config,
                        "fertilizer": fertilizer_schedule,
                        "water": water_management
                    }
                    
                    # Print unified payload to terminal/logs for auditing
                    logger.info(f"Unified agricultural management payload compiled: {json.dumps(management_payload, indent=2)}")

                    # Resolve effective coordinates cleanly across both routes
                    # lat/lon are only defined in system weather path; use session state as fallback
                    _lat_fallback = st.session_state.get("icrop2_lat_key", 21.0285)
                    _lon_fallback = st.session_state.get("icrop2_lon_key", 105.8542)
                    if "🌐 Use System Weather" in weather_source:
                        effective_lat = st.session_state.get("icrop2_lat_key", _lat_fallback)
                        effective_lon = st.session_state.get("icrop2_lon_key", _lon_fallback)
                    else:
                        effective_lat = uploaded_lat if uploaded_lat is not None else default_lat
                        effective_lon = uploaded_lon if uploaded_lon is not None else default_lon
                    
                    # 1. Resolve Weather data frame
                    if "📁 Upload My Own Weather" in weather_source:
                        if weather_df is None:
                            raise ValueError("Please upload an SSM Weather File first.")
                        weather_status_msg = "Successfully loaded weather matrix from custom uploaded SSM workbook."
                    elif "📂 Load Weather from OneDrive" in weather_source:
                        if weather_df is None:
                            raise ValueError("Please select a OneDrive Weather File first.")
                        weather_status_msg = f"Successfully loaded weather matrix from local OneDrive workbook: {selected_w_file}"
                    else:
                        # Option 1: fetch from Open-Meteo API
                        # 3. TIMEFRAME VALIDATION LOGIC
                        if (end_date - start_date).days > 50 * 365:
                            st.error("❌ Selected date range exceeds the maximum limit of 50 years. Please choose a shorter timeframe.")
                            st.stop()
                        if end_date > datetime.date.today():
                            st.warning("⚠️ You selected a date range in the future. Open-Meteo historical climate reanalysis data might not yet exist for future dates.")
                            
                        status_placeholder.warning("⏳ Accessing Open-Meteo API for real-time historical daily data...")
                        start_str = start_date.strftime("%Y-%m-%d")
                        end_str = end_date.strftime("%Y-%m-%d")
                        
                        try:
                            weather_df = fetch_openmeteo_weather(effective_lat, effective_lon, start_str, end_str)
                            if weather_df is None:
                                raise ConnectionError("Network connection timeout or failure after progressive retries.")
                            weather_status_msg = "Successfully ingested Open-Meteo meteorological data."
                        except Exception as w_err:
                            st.warning(f"⚠️ Weather Ingestion API query failed ({w_err}). Falling back to standard climatological baseline.")
                            weather_df = get_fallback_weather(start_str, end_str)
                            weather_status_msg = "Reverted to standard climatological weather baseline."
                    
                    # 2. Extract Soil profile and map it using failover/override checks
                    status_placeholder.warning("🌍 Resolving spatial soil parameters and overrides...")
                    
                    is_override_active = st.session_state.get("icrop2_soil_universal_override", False) or \
                        (not st.session_state.get("isric_available", True) and st.session_state.get("icrop2_failover_soil_source") == "Input My Own Measured Soil Parameters")
                    
                    if is_override_active:
                        # Construct from manual horizon inputs
                        dlyers = [float(st.session_state[f"override_dlyer_{i}"]) for i in range(5)]
                        duls = [float(st.session_state[f"override_dul_{i}"]) for i in range(5)]
                        pwps = [float(st.session_state[f"override_pwp_{i}"]) for i in range(5)]
                        wls = [float(st.session_state[f"override_wl_{i}"]) for i in range(5)]
                        
                        # SAT = DUL + 0.05
                        sat = [round(min(0.50, d + 0.05), 3) for d in duls]
                        # EXTR (Plant available water capacity fraction) = DUL - PWP
                        extr = [round(max(0.05, d - p), 3) for d, p in zip(duls, pwps)]
                        
                        soil_params = {
                            "NLYER": 5,
                            "LDRAIN": 4,
                            "SALB": 0.13,
                            "U": 6.0,
                            "CN": 75.0,
                            "DLYER": dlyers,
                            "SAT": sat,
                            "DUL": duls,
                            "EXTR": extr,
                            "DRAINF": [0.4, 0.4, 0.4, 0.4, 0.4],
                            "MAI": [1.0, 1.0, 1.0, 1.0, 1.0]
                        }
                        
                        # Estimate organic matter and fractions for diagnostic display
                        soil_profile = {
                            "Max_Root_Depth": int(sum(dlyers)),
                            "Soil_Water_Capacity": round(sum(d * e for d, e in zip(dlyers, extr)), 1),
                            "clay_fraction": 0.25,
                            "sand_fraction": 0.35,
                            "organic_matter": float(st.session_state.get("icrop2_som_key", 2.5)) / 100.0,
                            "bulk_density": 1.35,
                            "source": "Manual Soil Core Measurements (User Override)"
                        }
                    else:
                        # Standard routing with ISRIC API try-except failover
                        try:
                            from utils.soil_handler import fetch_isric_soil_data_with_failover
                            soil_profile = fetch_isric_soil_data_with_failover(effective_lat, effective_lon)
                            st.session_state["isric_available"] = True
                        except Exception as isric_err:
                            logger.warning(f"ISRIC API failed in run thread ({isric_err}). Using fallback.")
                            st.session_state["isric_available"] = False
                            from utils.soil_handler import load_boku_fallback_soil
                            soil_profile = load_boku_fallback_soil(effective_lat, effective_lon)
                            
                        soil_params = map_soil_profile_to_params(soil_profile)
                    
                    # 3. Update the global crop parameter matrix in-memory so the computational loop runs custom parameters
                    DEFAULT_CROP_PARAMETERS[crop_type].update(active_profile)
                    
                    status_placeholder.warning("⚙️ Ingesting weather and soil vectors into SSM-iCrop dynamic growth loop...")
                    
                    # 4. Instantiate & Execute simulation engine asynchronously
                    status_placeholder.warning("⚙️ Preparing background execution container...")
                    
                    # Slice weather starting from sowing DOY of the first available year to the very end
                    weather_sorted = weather_df.copy()
                    weather_sorted.columns = [str(c).upper() for c in weather_sorted.columns]
                    weather_sorted = weather_sorted.sort_values(by=['YEAR', 'DOY']).reset_index(drop=True)
                    available_years = sorted(weather_sorted['YEAR'].unique())
                    start_year = available_years[0]
                    
                    start_row = weather_sorted[(weather_sorted['YEAR'] == start_year) & (weather_sorted['DOY'] == sowing_doy)]
                    if start_row.empty:
                        start_row = weather_sorted[(weather_sorted['YEAR'] == start_year) & (weather_sorted['DOY'] >= sowing_doy)]
                        if start_row.empty:
                            start_row = weather_sorted[weather_sorted['YEAR'] == start_year]
                            
                    start_idx = start_row.index[0] if not start_row.empty else 0
                    sliced_weather = weather_sorted.iloc[start_idx:].copy().reset_index(drop=True)
                    
                    if sliced_weather.empty:
                        raise ValueError(f"No weather records available in sliced window starting at DOY {sowing_doy} in {start_year}.")
                        
                    sim_years = len(sliced_weather['YEAR'].unique())
                    
                    advanced_options = advanced_options.copy()
                    advanced_options["sim_years"] = sim_years
                    
                    engine_instance = SSMiCropEngine(
                        weather_df=sliced_weather, 
                        latitude=effective_lat, 
                        soil_params=soil_params,
                        soil_config=soil_config,
                        fertilizer_schedule=fertilizer_schedule,
                        water_management=water_management,
                        mode=engine_mode,
                        advanced_options=advanced_options,
                        sim_years=sim_years
                    )
                    
                    # Dispatch the simulation asynchronously to performance thread pool
                    runner = st.session_state.icrop2_async_runner
                    tracker = runner.execute_async_simulation(
                        engine_instance=engine_instance,
                        crop_type=crop_type,
                        pden=8.0,
                        vpdf=1.0
                    )
                    
                    # Render lightweight non-blocking UI visual feedback progress bar and spinner
                    progress_bar = st.progress(0)
                    spinner = st.spinner("Processing agricultural simulation formulas safely on the server...")
                    
                    # Dynamically poll background worker progress state smoothly
                    with spinner:
                        while not tracker.completed:
                            state = tracker.get_state()
                            progress_val = int(state["progress"])
                            progress_bar.progress(progress_val)
                            time.sleep(0.02) # Polling rate check
                            
                        # Final state check
                        final_state = tracker.get_state()
                        if final_state["error"]:
                            raise RuntimeError(final_state["error"])
                            
                        results_df = tracker.result
                        
                        # Log run in simulation history ledger
                        try:
                            compiled_df = format_simulation_run(results_df, scenario_name)
                            st.session_state["icrop2_sim_history"][scenario_name] = compiled_df
                            if "icrop2_detailed_scenarios" not in st.session_state:
                                st.session_state["icrop2_detailed_scenarios"] = {}
                            st.session_state["icrop2_detailed_scenarios"][scenario_name] = results_df.copy()
                            logger.info(f"Scenario '{scenario_name}' logged in simulation ledger.")
                        except Exception as hist_err:
                            logger.warning(f"Failed to log run to history: {hist_err}")

                        # Clear progress UI elements smoothly
                        progress_bar.empty()
                    
                    st.session_state.icrop2_last_results_df = results_df
                    st.session_state.icrop2_last_engine_instance = engine_instance
                    st.session_state.icrop2_last_soil_profile = soil_profile
                    st.session_state.icrop2_last_weather_status_msg = weather_status_msg
                    st.session_state.icrop2_simulation_run_active = True
                else:
                    # Restore from session state
                    results_df = st.session_state.icrop2_last_results_df
                    engine_instance = st.session_state.icrop2_last_engine_instance
                    soil_profile = st.session_state.icrop2_last_soil_profile
                    weather_status_msg = st.session_state.icrop2_last_weather_status_msg
                
                # 5. Extract results metrics
                max_lai_val = results_df["LAI"].max()
                # g/m² → t/ha conversion: 1 g/m² = 0.01 t/ha (same as ÷100)
                final_biomass_val = results_df["WTOP"].iloc[-1] / 100.0
                final_yield_val   = results_df["WGRN"].iloc[-1] / 100.0
                # Safety assertion: grain yield must be a subset of total biomass
                final_yield_val = min(final_yield_val, final_biomass_val)

                status_placeholder.success(f"🎉 Simulation run complete! {weather_status_msg}")
                
                # Render Metrics card
                with metrics_placeholder.container():
                    m1, m2, m3 = st.columns(3)
                    m1.markdown(f'<div class="metric-card"><div class="metric-label">Max LAI</div><div class="metric-value">{max_lai_val:.2f}</div></div>', unsafe_allow_html=True)
                    m2.markdown(f'<div class="metric-card"><div class="metric-label">Biomass (t/ha)</div><div class="metric-value">{final_biomass_val:.2f}</div></div>', unsafe_allow_html=True)
                    m3.markdown(f'<div class="metric-card"><div class="metric-label">Grain Yield (t/ha)</div><div class="metric-value">{final_yield_val:.2f}</div></div>', unsafe_allow_html=True)
                
                # Save simulation run sandbox box
                with st.expander("💾 Save Simulation Run to My Research Workspace Sandbox", expanded=False):
                    col_save_txt, col_save_btn = st.columns([2, 1])
                    run_save_name = col_save_txt.text_input("Persistent Save Name", value=scenario_name, key="workspace_save_run_name")
                    if col_save_btn.button("💾 Save Run", key="workspace_save_run_btn"):
                        # Prepare data
                        raw_dicts = results_df.to_dict(orient="records")
                        cleaned_raw = []
                        for row in raw_dicts:
                            cleaned_row = {}
                            for k, v in row.items():
                                if isinstance(v, (pd.DataFrame, pd.Series, dict, list)):
                                    continue
                                if pd.isna(v):
                                    cleaned_row[k] = None
                                elif isinstance(v, (datetime.date, datetime.datetime)):
                                    cleaned_row[k] = v.isoformat()
                                else:
                                    cleaned_row[k] = v
                            cleaned_raw.append(cleaned_row)
                            
                        summary_metrics = {
                            "max_lai": float(max_lai_val),
                            "biomass_tha": float(final_biomass_val),
                            "yield_tha": float(final_yield_val)
                        }
                        
                        # Determine Crop ID
                        crop_id = None
                        if selected_option.startswith("🔒 Private Custom:") or selected_option.startswith("🌐 Public Custom:") or selected_option.startswith("📦 Preset:"):
                            for sc in seeded_crops:
                                if sc.get("created_by_user_id") is not None:
                                    if sc.get("is_public") == 1:
                                        opt_lbl = f"🌐 Public Custom: {sc['crop_name']} ({sc['cultivar']})"
                                    else:
                                        opt_lbl = f"🔒 Private Custom: {sc['crop_name']} ({sc['cultivar']})"
                                else:
                                    opt_lbl = f"📦 Preset: {sc['crop_name']} ({sc['cultivar']})"
                                if opt_lbl == selected_option:
                                    crop_id = sc["id"]
                                    break
                                    
                        success_s, msg_s = db.save_simulation_run(
                            st.session_state.icrop2_user_id,
                            run_save_name,
                            crop_id,
                            summary_metrics,
                            cleaned_raw
                        )
                        if success_s:
                            st.success(f"🎉 {msg_s}")
                        else:
                            st.error(f"❌ {msg_s}")
                            
                # 6. Plot Interactive Biomass line chart via Plotly Express
                with chart1_placeholder.container():
                    st.markdown("##### 🌱 Daily Dry Biomass and Grain Weight Accumulation")
                    fig_biomass = px.line(
                        results_df,
                        x="Simulation_Timeline_Days",
                        y=["WTOP", "WGRN"],
                        labels={"value": "Dry Weight (g/m²)", "variable": "Organ Type", "Simulation_Timeline_Days": "Timeline Duration (Days Continuously Formatted)"},
                        color_discrete_map={"WTOP": "#3B82F6", "WGRN": "#10B981"}
                    )
                    fig_biomass.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=10, b=20),
                        xaxis=dict(gridcolor='#E5E7EB'),
                        yaxis=dict(gridcolor='#E5E7EB'),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig_biomass.update_xaxes(showspikes=True, spikethickness=1, spikedash="dot", spikemode="across", dtick=365)
                    configure_multi_year_chart(fig_biomass, results_df)
                    st.plotly_chart(fig_biomass, width='stretch')
                    
                # 7. Plot Leaf Area Index (LAI) Trajectory
                with chart2_placeholder.container():
                    st.markdown("##### 🍀 Leaf Area Index (LAI) Trajectory")
                    fig_lai = px.line(
                        results_df,
                        x="Simulation_Timeline_Days",
                        y="LAI",
                        labels={"LAI": "LAI (m²/m²)", "Simulation_Timeline_Days": "Timeline Duration (Days Continuously Formatted)"},
                        color_discrete_sequence=["#10B981"]
                    )
                    fig_lai.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=10, b=20),
                        xaxis=dict(gridcolor='#E5E7EB'),
                        yaxis=dict(gridcolor='#E5E7EB')
                    )
                    fig_lai.update_xaxes(showspikes=True, spikethickness=1, spikedash="dot", spikemode="across", dtick=365)
                    configure_multi_year_chart(fig_lai, results_df)
                    st.plotly_chart(fig_lai, width='stretch')
                    
                # 8. Plot Daily Temperature Development Stress Impact Chart
                with chart3_placeholder.container():
                    st.markdown("##### 🌡️ Development Temperature Stress Impacts")
                    # Calculate daily phenological temp stress factor (0 = extreme stress, 1 = optimal)
                    temp_stresses = results_df.apply(
                        lambda r: engine_instance.calculate_stress_factor(
                            r["TMP"], active_profile["TBD"], active_profile["TP1D"], active_profile["TP2D"], active_profile["TCD"]
                        ),
                        axis=1
                    )
                    results_df["Temperature Factor"] = temp_stresses
                    
                    fig_temp = px.line(
                        results_df,
                        x="Simulation_Timeline_Days",
                        y="Temperature Factor",
                        labels={"Temperature Factor": "Stress Coefficient (1=Optimal, 0=Stressed)", "Simulation_Timeline_Days": "Timeline Duration (Days Continuously Formatted)"},
                        color_discrete_sequence=["#EF4444"]
                    )
                    fig_temp.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=20, r=20, t=10, b=20),
                        xaxis=dict(gridcolor='#E5E7EB'),
                        yaxis=dict(gridcolor='#E5E7EB', range=[-0.05, 1.05])
                    )
                    fig_temp.update_xaxes(showspikes=True, spikethickness=1, spikedash="dot", spikemode="across", dtick=365)
                    configure_multi_year_chart(fig_temp, results_df)
                    st.plotly_chart(fig_temp, width='stretch')
                    
                # 9. Render Annual Performance & Soil Continuity Matrix
                if "Year" in results_df.columns:
                    av_years = sorted(results_df["Year"].unique())
                    if len(av_years) >= 1:
                        st.markdown("### 📊 Annual Performance & Soil Continuity Matrix")
                        st.markdown(
                            "This matrix compiles structural crop performance indicators alongside residual year-end soil metrics, "
                            "demonstrating continuous biophysical carry-over dynamics across consecutive years."
                        )
                        matrix_rows = []
                        for i, yr_val in enumerate(av_years):
                            yr_rel = i + 1
                            df_yr = results_df[results_df["Current_Year"] == yr_rel]
                            if not df_yr.empty:
                                max_lai_y = df_yr["LAI"].max()
                                end_sw_y = df_yr["SOIL_WATER"].iloc[-1]
                                end_n_y = df_yr["SOIL_N"].iloc[-1]
                                
                                # Determine yield: peak of the year's produce pool
                                prod_type = df_yr["crop_produce_type"].iloc[0] if "crop_produce_type" in df_yr.columns else "Fruit/Seed"
                                if prod_type == "Tuber/Root":
                                    yield_val_y = df_yr["WROOT"].max()
                                elif prod_type == "Vegetative Foliage":
                                    yield_val_y = df_yr["WLF"].max()
                                else:
                                    yield_val_y = df_yr["WGRN"].max()
                                    
                                yield_tha_y = yield_val_y * 0.01  # Convert g/m2 to t/ha
                                
                                matrix_rows.append({
                                    "Simulation Year": f"Year {yr_rel} ({int(yr_val)})",
                                    "Final Yield (t/ha)": round(yield_tha_y, 2),
                                    "Max Leaf Area Index (LAI)": round(max_lai_y, 2),
                                    "Ending Soil Water (mm)": round(end_sw_y, 1),
                                    "Ending Available Nitrogen (kg N/ha)": round(end_n_y, 1)
                                })
                        
                        summary_df = pd.DataFrame(matrix_rows)
                        st.dataframe(summary_df, use_container_width=True)
                    
                # Render Troubleshooting/Diagnostic logs
                simulation_results = results_df
                if st.checkbox("🔍 Activate Deep Backend Engineering Diagnostic Logs"):
                    st.subheader("Daily Nitrogen & Leaching State Matrix")
                    st.markdown(
                        """
                        This live diagnostic viewer exposes internal, daily-resolution biophysical state variables 
                        directly from the core simulation engine loop. Use this matrix to trace Nitrogen availability, 
                        drainage events, and nitrogen leaching mass dynamics day-by-day.
                        """
                    )
                    st.dataframe(
                        simulation_results["diagnostic_df"],
                        use_container_width=True,
                        column_config={
                            "DAP": st.column_config.NumberColumn("DAP", help="Days After Planting"),
                            "DRAIN": st.column_config.NumberColumn("Drainage (mm)", help="Daily Drainage volume"),
                            "SNAVL": st.column_config.NumberColumn("Soil N Pool (kg N/ha)", help="Available Soil Nitrogen pool"),
                            "NLEACH": st.column_config.NumberColumn("N Leached (kg N/ha)", help="Daily Nitrogen Leached mass"),
                            "NST": st.column_config.NumberColumn("N Stress Factor", help="Final Nitrogen Stress Factor (0=Extreme stress, 1=Optimal)")
                        }
                    )
                    
                # Render physical soil parameter expander
                with st.expander("🌍 Active Spatial Soil Profile Details", expanded=True):
                    s_col1, s_col2, s_col3 = st.columns(3)
                    s_col1.metric("Available Water (PAWC)", f"{soil_profile.get('Soil_Water_Capacity')} mm", help="Dynamic plant-available water capacity via Rawls-Saxton")
                    s_col2.metric("Soil Texture (Clay/Sand)", f"{soil_profile.get('clay_fraction')*100:.1f}% / {soil_profile.get('sand_fraction')*100:.1f}%")
                    s_col3.metric("Bulk Density / OM", f"{soil_profile.get('bulk_density')} g/cm³ / {soil_profile.get('organic_matter')*100:.2f}%")
                    st.info(f"**Data Source:** {soil_profile.get('source')}")

            except Exception as sim_err:
                st.error(f"Simulation Engine aborted: {sim_err}")
                status_placeholder.error("Simulation failed.")

    with tab_comp:
        st.subheader("📊 Simulation History & Scenario Comparison Workspace")
        
        if not st.session_state.get("icrop2_sim_history"):
            st.info("ℹ️ No historical runs logged yet. Execute a simulation to seed the ledger.")
            
            with st.expander("📥 Export Results & Simulation Data Logs", expanded=False):
                st.info("No recorded simulations available for export yet.")
        else:
            selected_runs = st.multiselect(
                "Select Scenarios to Compare", 
                options=list(st.session_state["icrop2_sim_history"].keys()), 
                default=list(st.session_state["icrop2_sim_history"].keys()),
                help="Select one or more runs to construct overlay comparisons."
            )
            
            if selected_runs:
                import plotly.express as px
                combined_df = pd.concat([st.session_state["icrop2_sim_history"][run] for run in selected_runs])
                
                # Multi-scenario Biomass Comparison Chart
                st.markdown("##### 🌱 Biomass Accumulation Overlay (kg/ha)")
                fig_biomass = px.line(
                    combined_df, 
                    x="Simulation_Timeline_Days", 
                    y="BIOMASS", 
                    color="Scenario", 
                    labels={"Simulation_Timeline_Days": "Timeline Duration (Days Continuously Formatted)", "BIOMASS": "Biomass (kg/ha)", "Scenario": "Run Label"},
                    title="Biomass Accumulation Impact Analysis (kg/ha)"
                )
                fig_biomass.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=20, t=30, b=20),
                    xaxis=dict(gridcolor='#E5E7EB'),
                    yaxis=dict(gridcolor='#E5E7EB')
                )
                fig_biomass.update_xaxes(showspikes=True, spikethickness=1, spikedash="dot", spikemode="across", dtick=365)
                configure_multi_year_chart(fig_biomass, combined_df)
                st.plotly_chart(fig_biomass, width='stretch')
                
                # Multi-scenario LAI Comparison Chart
                st.markdown("##### 🍀 Canopy Leaf Area Index (LAI) Overlay")
                fig_lai = px.line(
                    combined_df, 
                    x="Simulation_Timeline_Days", 
                    y="LAI", 
                    color="Scenario", 
                    labels={"Simulation_Timeline_Days": "Timeline Duration (Days Continuously Formatted)", "LAI": "Leaf Area Index (m²/m²)", "Scenario": "Run Label"},
                    title="Canopy Development Impact Analysis"
                )
                fig_lai.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=20, r=20, t=30, b=20),
                    xaxis=dict(gridcolor='#E5E7EB'),
                    yaxis=dict(gridcolor='#E5E7EB')
                )
                fig_lai.update_xaxes(showspikes=True, spikethickness=1, spikedash="dot", spikemode="across", dtick=365)
                configure_multi_year_chart(fig_lai, combined_df)
                st.plotly_chart(fig_lai, width='stretch')
            else:
                st.warning("⚠️ Please select at least one scenario run to build charts.")
                
            st.markdown("---")
            st.markdown("### 📊 Deep-Dive Scenario Data Inspector")
            
            history_options = list(st.session_state.get("icrop2_detailed_scenarios", {}).keys())
            
            if history_options:
                selected_inspect_run = st.selectbox(
                    "🔍 Select a specific historical run to inspect in close detail:",
                    options=history_options,
                    index=len(history_options) - 1 # Default highlight to the most recent run
                )
                
                # Pull the unredacted daily dataframe slice from memory
                inspect_df = st.session_state["icrop2_detailed_scenarios"][selected_inspect_run]
                
                # Retrieve metadata from the current crop profile row
                active_produce_type = inspect_df["crop_produce_type"].iloc[0] if "crop_produce_type" in inspect_df.columns else "Fruit/Seed"
                
                # Determine label naming variables dynamically
                if active_produce_type == "Tuber/Root":
                    yield_label = "🍠 Final Tuber/Root Yield"
                    yield_column = "WROOT"  # Map to structural root/tuber pool variable
                elif active_produce_type == "Vegetative Foliage":
                    yield_label = "🥬 Final Foliage/Leaf Yield"
                    yield_column = "WLF"    # Map directly to accumulated green leaf mass pool
                else:
                    yield_label = "🌾 Final Grain/Fruit/Seed Yield"
                    yield_column = "WGRN"   # Default standard grain seed storage pool
                
                # Dynamic Metric KPI Card Rendering
                final_yield_raw = inspect_df.iloc[-1].get(yield_column, 0.0)
                final_biomass_raw = inspect_df.iloc[-1].get("WTOP", 0.0)
                
                # Normalization scaling conversion to Ton/ha
                yield_ton = final_yield_raw / 100.0 if final_yield_raw > 100 else final_yield_raw
                biomass_ton = final_biomass_raw / 100.0 if final_biomass_raw > 100 else final_biomass_raw
                
                m_col1, m_col2, m_col3 = st.columns(3)
                with m_col1:
                    st.metric(label=yield_label, value=f"{yield_ton:.2f} Ton/ha")
                with m_col2:
                    st.metric(label="🌿 Total Above-Ground Biomass", value=f"{biomass_ton:.2f} Ton/ha")
                with m_col3:
                    max_lai = inspect_df["LAI"].max() if "LAI" in inspect_df.columns else 0.0
                    st.metric(label="🍀 Peak Leaf Area Index (LAI)", value=f"{max_lai:.2f}")
                
                # Provide a clean CSV download button for academic reporting or Excel extraction
                st.download_button(
                    label=f"📥 Export '{selected_inspect_run}' Data to CSV",
                    data=inspect_df.to_csv(index=False).encode('utf-8'),
                    file_name=f"{selected_inspect_run.replace(' ', '_')}_daily_output.csv",
                    mime='text/csv'
                )
                
                # Display the full interactive data frame spreadsheet matrix
                st.dataframe(inspect_df, use_container_width=True)
            else:
                st.info("No simulation runs recorded in the active workspace session ledger yet. Run a scenario to populate the detailed inspector.")
            
            st.markdown("---")
            
            # Expander for exporting results
            with st.expander("📥 Export Results & Simulation Data Logs", expanded=False):
                st.markdown("##### Export Ingested Growth Scenarios")
                
                # Display a brief data layout summary overview table
                st.write("Summary overview of the compiled multi-scenario history matrix:")
                summary_data = []
                for label, df in st.session_state["icrop2_sim_history"].items():
                    summary_data.append({
                        "Scenario Label": label,
                        "Days Count": len(df),
                        "Max LAI": f"{df['LAI'].max():.2f}",
                        "Max Biomass (kg/ha)": f"{df['BIOMASS'].max():.0f}"
                    })
                st.dataframe(pd.DataFrame(summary_data), width='stretch')
                
                # Dual column button layout
                col_csv, col_xlsx = st.columns(2)
                
                with col_csv:
                    # CSV generation
                    csv_data = export_history_to_csv(st.session_state["icrop2_sim_history"])
                    st.download_button(
                        label="Download Complete Data Matrix (.CSV)",
                        data=csv_data,
                        file_name="ssm_icrop_simulation_export.csv",
                        mime="text/csv",
                        width='stretch'
                    )
                    
                with col_xlsx:
                    # Excel generation
                    active_soil_config = {
                        "depth_mm": st.session_state.get("icrop2_depth_key", 1200),
                        "initial_water_percent": st.session_state.get("icrop2_initial_water_key", 25.0),
                        "pawc_mm_m": st.session_state.get("icrop2_pawc_key", 150.0),
                        "som_percent": st.session_state.get("icrop2_som_key", 2.5)
                    }
                    xlsx_data = export_history_to_xlsx(
                        sim_history=st.session_state["icrop2_sim_history"],
                        soil_config=active_soil_config,
                        latitude=st.session_state.get("icrop2_lat_key", 21.0285),
                        longitude=st.session_state.get("icrop2_lon_key", 105.8542),
                        crop_name=st.session_state.get("icrop2_selected_crop_profile", "Default Crop")
                    )
                    st.download_button(
                        label="Download Formatted Research Workbook (.XLSX)",
                        data=xlsx_data,
                        file_name="ssm_icrop_simulation_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width='stretch'
                    )
            
            st.markdown("---")
            if st.button("🗑️ Clear History Logs", width='stretch'):
                st.session_state["icrop2_sim_history"] = {}
                st.toast("🧹 Simulation history cleared successfully!")
                st.rerun()

    with tab_workspace:
        st.subheader("👤 My Research Workspace & Sandbox")
        
        # 1. Professional Biography Panel
        st.markdown("### 📋 Professional Research Biography")
        bio_data = db.get_user_biography(st.session_state.icrop2_user_id)
        
        with st.form("update_biography_form"):
            bio_name = st.text_input("Professional Name", value=bio_data.get("bio_name") or st.session_state.icrop2_name or "")
            bio_org = st.text_input("Affiliated Institution / Organization", value=bio_data.get("bio_organization") or st.session_state.icrop2_workplace or "")
            bio_text = st.text_area("Research Summary & Focus", value=bio_data.get("bio_text") or "")
            
            if st.form_submit_button("Update Biography Details"):
                if db.update_user_biography(st.session_state.icrop2_user_id, bio_name, bio_org, bio_text):
                    # Also sync profile detail updates
                    update_user_profile(st.session_state.icrop2_user_id, bio_name, bio_org)
                    st.session_state.icrop2_name = bio_name
                    st.session_state.icrop2_workplace = bio_org
                    st.success("✅ Biography and profile details updated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to update biography details.")
                    
        # 2. Storage Quota Status Card
        st.markdown("### 📊 Account Quota Status")
        current_saved_runs = len(db.get_simulation_runs(st.session_state.icrop2_user_id))
        limit_color = "#10B981" if current_saved_runs < st.session_state.icrop2_run_limit else "#EF4444"
        
        st.markdown(f"""
        <div style="padding: 1rem; background-color: #F9FAFB; border-radius: 8px; border: 1px solid #E5E7EB; margin-bottom: 1.5rem;">
            <p style="margin: 0;"><strong>User Tier:</strong> <span style="color: #3B82F6;">{st.session_state.icrop2_user_tier}</span></p>
            <p style="margin: 0;"><strong>Simulation Storage Cap:</strong> <span style="color: {limit_color}; font-weight: bold;">{current_saved_runs} / {st.session_state.icrop2_run_limit} runs</span></p>
        </div>
        """, unsafe_allow_html=True)
        
        # 3. Saved Simulations Ledger
        st.markdown("### 💾 Saved Simulations Ledger")
        saved_runs = db.get_simulation_runs(st.session_state.icrop2_user_id)
        if not saved_runs:
            st.info("ℹ️ No saved simulations found in your workspace sandbox. Run a simulation and save it to persist results here.")
        else:
            for idx, run in enumerate(saved_runs):
                with st.expander(f"📁 {run['run_name']} (Saved: {run['timestamp']})", expanded=False):
                    m_c1, m_c2, m_c3 = st.columns(3)
                    m_c1.metric("Max LAI", f"{run['summary_metrics'].get('max_lai', 0.0):.2f}")
                    m_c2.metric("Biomass (t/ha)", f"{run['summary_metrics'].get('biomass_tha', 0.0):.2f}")
                    m_c3.metric("Grain Yield (t/ha)", f"{run['summary_metrics'].get('yield_tha', 0.0):.2f}")
                    
                    st.markdown("##### 📥 Export / Download Data")
                    try:
                        run_df = pd.DataFrame(run["raw_data"])
                        col_exp_csv, col_exp_xlsx, col_exp_del = st.columns(3)
                        
                        # Generate CSV
                        csv_data_run = run_df.to_csv(index=False).encode('utf-8')
                        col_exp_csv.download_button(
                            label="Download CSV",
                            data=csv_data_run,
                            file_name=f"{run['run_name'].replace(' ', '_')}_simulation.csv",
                            mime="text/csv",
                            key=f"csv_run_dl_{run['id']}"
                        )
                        
                        # Generate Excel
                        import io
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                            run_df.to_excel(writer, sheet_name="Timeline", index=False)
                        xlsx_data_run = output.getvalue()
                        
                        col_exp_xlsx.download_button(
                            label="Download Formatted Excel",
                            data=xlsx_data_run,
                            file_name=f"{run['run_name'].replace(' ', '_')}_simulation.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"xlsx_run_dl_{run['id']}"
                        )
                    except Exception as e_run:
                        st.error(f"Failed to generate download archives: {e_run}")
                        
                    # Delete saved run
                    if col_exp_del.button("🗑️ Delete Simulation Run", key=f"del_run_btn_{run['id']}"):
                        db.delete_simulation_run(run["id"], st.session_state.icrop2_user_id)
                        st.toast(f"🧹 Deleted simulation run '{run['run_name']}'!")
                        st.rerun()

        # 4. Standard Profile and Password management (under expanders)
        with st.expander("🔐 Security & Credentials Settings", expanded=False):
            st.subheader("Profile Account Details")
            with st.form("update_profile_form_workspace"):
                prof_name = st.text_input("Full Name", value=st.session_state.icrop2_name)
                prof_work = st.text_input("Workplace / Institution", value=st.session_state.icrop2_workplace)
                
                if st.form_submit_button("Update Account Details"):
                    success, msg = update_user_profile(st.session_state.icrop2_user_id, prof_name, prof_work)
                    if success:
                        st.session_state.icrop2_name = prof_name
                        st.session_state.icrop2_workplace = prof_work
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            
            st.subheader("Change Password")
            with st.form("change_password_form_workspace"):
                st.write("To change your account password, type your credentials to request a secure link:")
                curr_pass = st.text_input("Current Password", type="password", key="chg_pwd_current_ws")
                new_pass = st.text_input("New Password (Min 6 chars)", type="password", key="chg_pwd_new_ws")
                confirm_pass = st.text_input("Confirm New Password", type="password", key="chg_pwd_confirm_ws")
                
                if st.form_submit_button("Request Password Change Token"):
                    if new_pass != confirm_pass:
                        st.error("Passwords do not match!")
                    elif len(new_pass) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        # Validate current password
                        success, msg, payload = authenticate_secure_user(st.session_state.icrop2_username, curr_pass)
                        if success:
                            # Password correct, dispatch reset/verification email link
                            req_success, req_msg = request_password_reset(st.session_state.icrop2_email)
                            st.info("A secure password reset link has been dispatched to your email address. Verify the email link to apply changes.")
                        else:
                            st.error("Current password verification failed. Please try again.")
                            
            # Local debug reset link display for password changes
            my_emails_reset = [m for m in LOCAL_MAILBOX_SIMULATOR if m["to"] == st.session_state.icrop2_email and "Reset" in m["subject"]]
            if my_emails_reset and not is_smtp_configured():
                st.info("Confirmation email links found in local memory cache:")
                for m in my_emails_reset:
                    st.write(f"**To:** {m['to']} | **Subject:** {m['subject']}")
                    lnks = re.findall(r'href="(.*?)"', m["body_html"])
                    if lnks:
                        st.markdown(f"[🔗 Complete Password Reset]({lnks[0]})")

    with tab_calibration:
        st.subheader("🔬 Crop Parameter Calibration Wizard")
        st.markdown(
            "Welcome to the high-flexibility SSM-iCrop calibration wizard. "
            "You can enter historical harvest observations (Yield & LAI) and select crop physiological coefficients "
            "for the optimization search engine to fine-tune to your local region."
        )
        
        # 1. Weather Data Source Selection
        st.markdown("### ☁️ Step 1: Bind Weather Data Source")
        cal_weather_src = st.radio(
            "Select Weather Dataset for Calibration:",
            ["📂 Use Current Uploaded Weather File", "🌐 Auto-Fetch Satellite Weather for Coordinates"],
            key="cal_weather_src_select"
        )
        
        effective_cal_weather_df = None
        if "📂 Use Current Uploaded Weather" in cal_weather_src:
            if 'weather_df' in locals() and weather_df is not None:
                effective_cal_weather_df = weather_df.copy()
            elif st.session_state.get("icrop2_last_results_df") is not None:
                res_df = st.session_state.icrop2_last_results_df
                if "YEAR" in res_df.columns and "DOY" in res_df.columns:
                    cols_needed = ["YEAR", "DOY", "SRAD", "TMAX", "TMIN", "RAIN", "TMP", "VP"]
                    effective_cal_weather_df = pd.DataFrame()
                    for c in cols_needed:
                        if c in res_df.columns:
                            effective_cal_weather_df[c] = res_df[c]
                        elif c == "TMP" and "TMAX" in res_df.columns:
                            effective_cal_weather_df["TMP"] = (res_df["TMAX"] + res_df["TMIN"]) / 2.0
                        elif c == "VP" and "VPD" in res_df.columns:
                            effective_cal_weather_df["VP"] = 1.0
            
            if effective_cal_weather_df is None:
                st.warning("⚠️ No custom weather file uploaded yet. Please upload a weather file in the sidebar first, or choose '🌐 Auto-Fetch' to download satellite records.")
        else:
            st.info(f"📍 Will auto-fetch satellite weather at coordinate center: Lat = {st.session_state.latitude:.4f}, Lon = {st.session_state.longitude:.4f}")
            
        # 2. Soil Data Source Selection
        st.markdown("### ⛰️ Step 2: Bind Soil Data Source")
        cal_soil_src = st.radio(
            "Select Soil Profile Dataset for Calibration:",
            ["🌐 Use Active ISRIC Grid API Profile", "⛰️ Use BOKU Regional Dataset", "✍️ Use My Manually Typed Soil Layer Values"],
            key="cal_soil_src_select"
        )
        
        effective_cal_soil_params = None
        effective_cal_soil_profile = None
        
        if "ISRIC Grid API Profile" in cal_soil_src:
            if 'soil_profile' in locals() and soil_profile is not None:
                effective_cal_soil_profile = soil_profile
                effective_cal_soil_params = map_soil_profile_to_params(soil_profile)
            else:
                try:
                    from utils.soil_handler import fetch_isric_soil_data_with_failover
                    effective_cal_soil_profile = fetch_isric_soil_data_with_failover(st.session_state.latitude, st.session_state.longitude)
                    effective_cal_soil_params = map_soil_profile_to_params(effective_cal_soil_profile)
                except Exception as isric_e:
                    st.warning(f"ISRIC API failed ({isric_e}). Reverting to regional default.")
                    from utils.soil_handler import load_boku_fallback_soil
                    effective_cal_soil_profile = load_boku_fallback_soil(st.session_state.latitude, st.session_state.longitude)
                    effective_cal_soil_params = map_soil_profile_to_params(effective_cal_soil_profile)
        elif "BOKU Regional Dataset" in cal_soil_src:
            from utils.soil_handler import load_boku_fallback_soil
            effective_cal_soil_profile = load_boku_fallback_soil(st.session_state.latitude, st.session_state.longitude)
            effective_cal_soil_params = map_soil_profile_to_params(effective_cal_soil_profile)
        else:
            dlyers = [float(st.session_state.get(f"override_dlyer_{i}", 150.0)) for i in range(5)]
            duls = [float(st.session_state.get(f"override_dul_{i}", 0.28)) for i in range(5)]
            pwps = [float(st.session_state.get(f"override_pwp_{i}", 0.12)) for i in range(5)]
            
            sat = [round(min(0.50, d + 0.05), 3) for d in duls]
            extr = [round(max(0.05, d - p), 3) for d, p in zip(duls, pwps)]
            
            effective_cal_soil_params = {
                "NLYER": 5,
                "LDRAIN": 4,
                "SALB": 0.13,
                "U": 6.0,
                "CN": 75.0,
                "DLYER": dlyers,
                "SAT": sat,
                "DUL": duls,
                "EXTR": extr,
                "DRAINF": [0.4, 0.4, 0.4, 0.4, 0.4],
                "MAI": [1.0, 1.0, 1.0, 1.0, 1.0]
            }
            effective_cal_soil_profile = {
                "Max_Root_Depth": int(sum(dlyers)),
                "Soil_Water_Capacity": round(sum(d * e for d, e in zip(dlyers, extr)), 1),
                "clay_fraction": 0.25,
                "sand_fraction": 0.35,
                "organic_matter": float(st.session_state.get("icrop2_som_key", 2.5)) / 100.0,
                "bulk_density": 1.35,
                "source": "Manual Soil Core Measurements"
            }
            
        if effective_cal_soil_profile is not None:
            st.success(f"✅ Bound Soil Profile Capacity: {effective_cal_soil_profile.get('Soil_Water_Capacity')} mm ({effective_cal_soil_profile.get('source', 'Resolved')})")
            
        # 3. Observed Data Ledger
        st.markdown("### 🌾 Step 3: Enter Historical Observed Records")
        if "calibration_grid" not in st.session_state:
            st.session_state["calibration_grid"] = pd.DataFrame([
                {"Year": 2020, "Observed Yield (t/ha)": 7.8, "Observed Peak LAI (Optional)": 4.2}
            ])
            
        with st.form("observed_yields_entry_form"):
            st.markdown("### ✍️ Input Real Historical Observations")
            updated_data = st.data_editor(
                st.session_state["calibration_grid"],
                use_container_width=True,
                num_rows="dynamic",
                key="cal_obs_editor_grid",
                column_config={
                    "Year": st.column_config.NumberColumn("Year", min_value=1940, max_value=2026, format="%d"),
                    "Observed Yield (t/ha)": st.column_config.NumberColumn("Observed Yield (t/ha)", min_value=0.1, max_value=40.0, step=0.1),
                    "Observed Peak LAI (Optional)": st.column_config.NumberColumn("Observed Peak LAI (Optional)", min_value=0.0, max_value=15.0, step=0.1)
                }
            )
            submit_lock = st.form_submit_button("🔒 Lock & Validate Fields")
            
        if submit_lock:
            st.session_state["calibration_grid"] = updated_data
            st.success("Target observations (Yield/LAI) securely locked in memory!")
            
        obs_df = st.session_state["calibration_grid"]
        if isinstance(obs_df, pd.DataFrame):
            edited_obs = obs_df.to_dict(orient="records")
        else:
            edited_obs = obs_df
        
        # 4. Parameter Selection Checkboxes
        st.markdown("### ⚙️ Step 4: Select crop variables to estimate")
        col_sel1, col_sel2 = st.columns(2)
        c_rue = col_sel1.checkbox("Radiation Use Efficiency (RUE_MAX) [Bounds: 1.0 to 5.0 g/MJ]", value=True)
        c_sla = col_sel1.checkbox("Specific Leaf Area (SLA) [Bounds: 0.005 to 0.05 m²/g]", value=False)
        c_tbd = col_sel1.checkbox("Base Temperature (TBD) [Bounds: 0.0 to 15.0 °C]", value=False)
        c_phyl = col_sel2.checkbox("Phyllochron (PHYL) [Bounds: 20.0 to 100.0 °C/leaf]", value=False)
        c_sow = col_sel2.checkbox("Sowing-Emergence Days (bdSOWEMR) [Bounds: 1.0 to 10.0]", value=False)
        c_eju = col_sel2.checkbox("Emergence-Juvenile Days (bdEMREJU) [Bounds: 5.0 to 25.0]", value=False)
        c_sil = col_sel2.checkbox("Silking-Maturity Days (bdSILPM) [Bounds: 10.0 to 60.0]", value=False)
        
        cal_bounds = {}
        if c_rue:
            cal_bounds["RUE_MAX"] = (1.0, 5.0)
            cal_bounds["IRUE"] = (1.0, 5.0)
        if c_sla:
            cal_bounds["SLA"] = (0.005, 0.05)
        if c_tbd:
            cal_bounds["TBD"] = (0.0, 15.0)
        if c_phyl:
            cal_bounds["PHYL"] = (20.0, 100.0)
        if c_sow:
            cal_bounds["bdSOWEMR"] = (1.0, 10.0)
        if c_eju:
            cal_bounds["bdEMREJU"] = (5.0, 25.0)
        if c_sil:
            cal_bounds["bdSILPM"] = (10.0, 60.0)
            
        # 5. Run Search Button
        if st.button("🚀 Run Calibration Optimization Search", width='stretch', key="cal_run_opt_search_btn"):
            valid_obs = [o for o in edited_obs if o.get("Year") is not None and o.get("Observed Yield (t/ha)") is not None]
            if not valid_obs:
                st.error("❌ Observed records matrix is empty. Please enter at least 1 valid Year and Observed Yield row.")
            elif not cal_bounds:
                st.error("❌ Please select at least 1 crop physiological coefficient to calibrate.")
            else:
                cal_weather_ok = True
                if "📂 Use Current Uploaded Weather" in cal_weather_src:
                    if effective_cal_weather_df is None:
                        st.error("❌ No weather file uploaded. Please upload a weather file or choose the coordinates satellite auto-fetch.")
                        cal_weather_ok = False
                else:
                    years_list = sorted(list({int(o["Year"]) for o in valid_obs}))
                    start_y_val = f"{years_list[0]}-01-01"
                    end_y_val = f"{years_list[-1]}-12-31"
                    
                    with st.spinner("⏳ Querying Open-Meteo satellite weather API for observed timeframe..."):
                        try:
                            effective_cal_weather_df = fetch_openmeteo_weather(
                                lat=st.session_state.latitude,
                                lon=st.session_state.longitude,
                                start_date=start_y_val,
                                end_date=end_y_val
                            )
                            if effective_cal_weather_df is None:
                                raise ConnectionError("Open-Meteo API returned empty dataset.")
                            st.success(f"✅ Ingested weather matrix from satellite coordinates reanalysis.")
                        except Exception as w_err:
                            st.error("📡 Satellite Weather API Query Failed!")
                            st.info("⚠️ Error Details: " + str(w_err))
                            st.warning("👉 The automated cloud weather stream is currently unreachable. Please switch your data source to 'Upload Local Weather File' and drop your station (.csv/.xlsx) timeline sheet below to proceed with the simulation.")
                            effective_cal_weather_df = get_fallback_weather(start_y_val, end_y_val)
                            
                if cal_weather_ok and effective_cal_weather_df is not None:
                    with st.spinner("⚙️ Executing crop physiological optimization algorithms safely..."):
                        weather_sorted = effective_cal_weather_df.copy()
                        weather_sorted.columns = [str(c).upper() for c in weather_sorted.columns]
                        weather_sorted = weather_sorted.sort_values(by=['YEAR', 'DOY']).reset_index(drop=True)
                        
                        progress_element = st.progress(0)
                        def progress_cb(current, total):
                            pct = int((current / total) * 100)
                            progress_element.progress(min(100, pct))
                            
                        c_type = "Maize"
                        if "Sorghum" in st.session_state.get("icrop2_selected_crop_profile", "Maize"):
                            c_type = "Sorghum"
                            
                        soil_config = {
                            "depth_mm": st.session_state.get("icrop2_depth_key", 1200),
                            "initial_water_percent": st.session_state.get("icrop2_initial_water_key", 25.0),
                            "pawc_mm_m": st.session_state.get("icrop2_pawc_key", 150.0),
                            "som_percent": st.session_state.get("icrop2_som_key", 2.5)
                        }
                        
                        try:
                            opt_params, orig_rmse, best_rmse = run_calibration_search(
                                observed_data=valid_obs,
                                weather_target_df=weather_sorted,
                                soil_target_profile=effective_cal_soil_params,
                                parameter_bounds=cal_bounds,
                                crop_type=c_type,
                                latitude=st.session_state.latitude,
                                soil_config=soil_config,
                                fertilizer_schedule=st.session_state.icrop2_fertilizer_rounds,
                                water_management={"auto_irrigation": "Automatic" in st.session_state.get("icrop2_auto_irrigation_key", "Rainfed")},
                                engine_mode="Advanced",
                                advanced_options={"use_moisture": True, "use_nitrogen": True},
                                progress_callback=progress_cb
                            )
                            
                            st.session_state["calibration_results"] = {
                                "optimized_params": opt_params,
                                "initial_rmse": orig_rmse,
                                "final_rmse": best_rmse,
                                "has_run": True
                            }
                            st.success("🎉 Crop optimization completed successfully!")
                            progress_element.empty()
                            st.rerun()
                        except Exception as e_cal:
                            st.error(f"Calibration optimization failed: {e_cal}")
                            
        # 6. Report Calibration View & Save to SQLite
        if st.session_state.get("calibration_results", {}).get("has_run"):
            st.success("🎉 Calibration Search Complete!")
            st.markdown("### 📊 Calibration Optimization Report")
            cal_res = st.session_state["calibration_results"]
            best_params = cal_res["optimized_params"]
            orig_rmse = cal_res["initial_rmse"]
            best_rmse = cal_res["final_rmse"]
            
            c_type = "Maize"
            if "Sorghum" in st.session_state.get("icrop2_selected_crop_profile", "Maize"):
                c_type = "Sorghum"
                
            col_rm1, col_rm2, col_rm3 = st.columns(3)
            col_rm1.metric("Original Model RMSE", f"{orig_rmse:.3f} t/ha")
            col_rm2.metric("Optimized Model RMSE", f"{best_rmse:.3f} t/ha")
            pct_imp = ((orig_rmse - best_rmse) / max(0.01, orig_rmse)) * 100.0 if orig_rmse != float('inf') else 100.0
            col_rm3.metric("Error Reduction", f"{pct_imp:.1f}%")
            
            st.markdown("##### ⚙️ Comparative Parameter Grid")
            comp_rows = []
            for p_name in best_params.keys():
                if p_name == "IRUE" and "RUE_MAX" in best_params:
                    continue
                orig_val = DEFAULT_CROP_PARAMETERS[c_type].get(p_name, 0.0)
                opt_val = best_params[p_name]
                comp_rows.append({
                    "Parameter Name": p_name,
                    "Original Value": round(orig_val, 4),
                    "Calibrated Value": round(opt_val, 4),
                    "Absolute Change": round(opt_val - orig_val, 4)
                })
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True)
            
            st.markdown("##### 💾 Persist Calibrated Variety to Database")
            with st.form("save_calibrated_variety_form"):
                new_cal_name = st.text_input("Calibrated Cultivar Name", placeholder="e.g. Maize-Hybrid-Ohio-2026")
                new_cal_public = st.checkbox("🌐 Share with the community library", value=False)
                
                if st.form_submit_button("💾 Save as Custom Calibrated Variety"):
                    if not new_cal_name.strip():
                        st.error("Name field cannot be blank!")
                    else:
                        new_params = DEFAULT_CROP_PARAMETERS[c_type].copy()
                        new_params.update(best_params)
                        if "RUE_MAX" in best_params:
                            new_params["IRUE"] = best_params["RUE_MAX"]
                            
                        is_pub = 1 if new_cal_public else 0
                        created_by_user = st.session_state.icrop2_user_id
                        
                        try:
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter, is_public, created_by_user_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (new_cal_name.strip(), "Calibrated", json.dumps(new_params), new_params.get("crop_produce_type", "Fruit/Seed"), new_params.get("lifecycle_strategy", "Annual (Single-Season)"), new_params.get("t_dormancy_trigger", 5.0), new_params.get("t_base_winter", 0.0), is_pub, created_by_user))
                                conn.commit()
                            st.success(f"🎉 Persisted custom calibrated cultivar '{new_cal_name}' successfully!")
                            
                            if is_pub:
                                st.session_state["icrop2_selected_crop_profile"] = f"🌐 Public Custom: {new_cal_name.strip()} (Calibrated)"
                            else:
                                st.session_state["icrop2_selected_crop_profile"] = f"🔒 Private Custom: {new_cal_name.strip()} (Calibrated)"
                            
                            del st.session_state["calibration_results"]
                            st.rerun()
                        except Exception as e_save:
                            st.error(f"Failed to persist variety: {e_save}")

    if st.session_state.get("icrop2_user_tier") == "Admin":
        with tab_admin:
            st.subheader("🛡️ Administrative Control Panel")
            
            # Sub-tab 1: User limits and storage allocations
            st.markdown("### 👥 User Storage Limits & Account Adjustments")
            all_users = db.get_all_users()
            
            # Display a nice administrative table grid
            for usr in all_users:
                with st.container():
                    st.markdown(f"**User:** {usr['name']} (`{usr['username']}`) — *{usr['user_tier']}*")
                    col_usr1, col_usr2, col_usr3 = st.columns([2, 1, 1])
                    col_usr1.write(f"📧 Email: {usr['email']} | 🏫 Organization: {usr['bio_organization'] or usr['workplace']}")
                    
                    new_lim = col_usr2.number_input(
                        "Storage Run Limit",
                        min_value=5,
                        max_value=1000,
                        value=int(usr["run_limit"]),
                        key=f"admin_usr_lim_{usr['id']}"
                    )
                    
                    # Update database if limit is changed
                    if new_lim != usr["run_limit"]:
                        if db.update_user_run_limit(usr["id"], new_lim):
                            st.toast(f"✅ Run storage limit for '{usr['username']}' updated to {new_lim}!")
                            st.rerun()
                            
                    st.markdown("---")
                    
            # Sub-tab 2: Master Crop CRUD Manager
            st.markdown("### 🌾 Master Crop Preset CRUD Manager")
            
            master_crops = db.get_seeded_crops(st.session_state.icrop2_user_id) # Seeded master crops inside 'crops' table
            
            st.write("Below are the pre-seeded public crop cultivars from the database. Administrators can edit parameters or delete cultivars.")
            
            for m_crop in master_crops:
                # Only CRUD actual master presets or admin seeded crops (is_public = 1)
                if m_crop.get("is_public", 1) == 1:
                    with st.expander(f"📦 Master Cultivar: {m_crop['crop_name']} ({m_crop['cultivar']})", expanded=False):
                        m_params = m_crop["parameters"]
                        
                        # Expose key parameters for editing
                        col_e1, col_e2, col_e3 = st.columns(3)
                        e_tbd = col_e1.number_input("Base Temp (TBD)", value=float(m_params.get("TBD", 8.0)), key=f"edit_tbd_{m_crop['id']}")
                        e_rue = col_e2.number_input("Max RUE", value=float(m_params.get("RUE_MAX", 3.5)), key=f"edit_rue_{m_crop['id']}")
                        e_sla = col_e3.number_input("SLA (m²/g)", value=float(m_params.get("SLA", 0.022)), format="%.4f", key=f"edit_sla_{m_crop['id']}")
                        
                        col_btn1, col_btn2 = st.columns(2)
                        if col_btn1.button("💾 Save Parameters Overwrite", key=f"save_m_crop_{m_crop['id']}"):
                            # Construct parameters dictionary
                            updated_params = m_params.copy()
                            updated_params["TBD"] = e_tbd
                            updated_params["RUE_MAX"] = e_rue
                            updated_params["IRUE"] = e_rue
                            updated_params["SLA"] = e_sla
                            
                            # Save back to 'crops' table
                            with db.get_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute("UPDATE crops SET parameters_json = ? WHERE id = ?", (json.dumps(updated_params), m_crop["id"]))
                                conn.commit()
                            st.success(f"✅ Overwrote parameters for master crop variety '{m_crop['crop_name']}'!")
                            st.rerun()
                            
                        if col_btn2.button("🗑️ Delete Master Cultivar", key=f"del_m_crop_{m_crop['id']}"):
                            db.delete_master_crop(m_crop["id"])
                            st.toast(f"❌ Deleted master crop variety '{m_crop['crop_name']}'!")
                            st.rerun()
                        
            # Register a New Master Preset
            st.markdown("#### ➕ Add New Master Crop Preset")
            with st.form("new_master_crop_form"):
                new_m_name = st.text_input("Master Crop Name (e.g. Rice)")
                new_m_cultivar = st.text_input("Master Cultivar (e.g. IR64)")
                new_m_tbd = st.number_input("Base Temp (TBD)", value=8.0)
                new_m_rue = st.number_input("Max RUE", value=3.0)
                new_m_sla = st.number_input("SLA", value=0.022, format="%.4f")
                
                if st.form_submit_button("Register Master Crop"):
                    if not new_m_name.strip() or not new_m_cultivar.strip():
                        st.error("Name and Cultivar fields cannot be blank!")
                    else:
                        m_params = DEFAULT_CROP_PARAMETERS["Maize"].copy()
                        m_params["TBD"] = new_m_tbd
                        m_params["RUE_MAX"] = new_m_rue
                        m_params["IRUE"] = new_m_rue
                        m_params["SLA"] = new_m_sla
                        
                        with db.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT OR REPLACE INTO crops (crop_name, cultivar, parameters_json, crop_produce_type, lifecycle_strategy, t_dormancy_trigger, t_base_winter, is_public)
                                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                            """, (new_m_name.strip(), new_m_cultivar.strip(), json.dumps(m_params), "Fruit/Seed", "Annual (Single-Season)", 5.0, 0.0))
                            conn.commit()
                        st.success(f"🎉 Registered new master crop variety '{new_m_name} ({new_m_cultivar})'!")
                        st.rerun()
