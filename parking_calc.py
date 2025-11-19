import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon
from shapely.geometry import box, Point
from shapely.affinity import rotate, translate
import math
import numpy as np
import pydeck as pdk
import pandas as pd
import requests
import urllib3
import urllib.parse
import logging
from datetime import datetime

st.set_page_config(page_title="Parking Space Estimator", layout="wide", initial_sidebar_state="expanded")

# Custom CSS to make sidebar wider and handle collapse properly
st.markdown("""
    <style>
        /* Sidebar width when expanded */
        section[data-testid="stSidebar"]:not([aria-expanded="false"]) {
            width: 400px !important;
            min-width: 400px !important;
        }
        section[data-testid="stSidebar"]:not([aria-expanded="false"]) > div {
            width: 400px !important;
        }
        
        /* Prevent overflow when collapsed */
        section[data-testid="stSidebar"] {
            overflow-x: hidden !important;
        }
        section[data-testid="stSidebar"] > div {
            overflow-x: hidden !important;
        }
        
        /* Hide content properly when collapsed */
        section[data-testid="stSidebar"][aria-expanded="false"] > div {
            display: none !important;
        }
    </style>
""", unsafe_allow_html=True)
st.title("🅿️ Parking Space Estimator")
st.markdown("Draw a polygon on the map to estimate how many parking spaces could fit in the area.")

# Initialize app logs in session state
if 'app_logs' not in st.session_state:
    st.session_state.app_logs = []

def add_app_log(message, level="INFO"):
    """Add a log entry to the session state for display"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {level}: {message}"
    st.session_state.app_logs.append(log_entry)

# Set up file logging
logging.basicConfig(
    filename='parking_estimator_errors.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Test endpoint availability with logging
def test_endpoint_availability(name, url):
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        logging.info(f"Testing {name} endpoint: {url}")
        add_app_log(f"Testing {name} endpoint", "INFO")
        
        response = requests.get(url, verify=False, timeout=5)
        
        if response.status_code == 200:
            logging.info(f"{name} endpoint SUCCESS - Status: {response.status_code}")
            add_app_log(f"{name} endpoint SUCCESS", "INFO")
            return True
        else:
            logging.error(f"{name} endpoint FAILED - Status: {response.status_code}, Response: {response.text[:200]}")
            add_app_log(f"{name} endpoint FAILED - Status: {response.status_code}", "ERROR")
            return False
            
    except requests.exceptions.Timeout as e:
        logging.error(f"{name} endpoint TIMEOUT - {str(e)}")
        add_app_log(f"{name} endpoint TIMEOUT", "ERROR")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"{name} endpoint CONNECTION ERROR - {str(e)}")
        add_app_log(f"{name} endpoint CONNECTION ERROR", "ERROR")
        return False
    except Exception as e:
        logging.error(f"{name} endpoint UNKNOWN ERROR - {type(e).__name__}: {str(e)}")
        add_app_log(f"{name} endpoint ERROR: {type(e).__name__}", "ERROR")
        return False

# Test NAIP endpoint availability
def test_naip_availability():
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        service_url = "https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer?f=json"
        logging.info(f"Testing NAIP service endpoint: {service_url}")
        add_app_log(f"Testing NAIP service endpoint", "INFO")
        
        response = requests.get(service_url, verify=False, timeout=5)
        
        if response.status_code != 200:
            logging.error(f"NAIP service FAILED - Status: {response.status_code}")
            add_app_log(f"NAIP service FAILED - Status: {response.status_code}", "ERROR")
            return False
        
        tile_url = "https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer/tile/10/200/400"
        logging.info(f"Testing NAIP tile availability: {tile_url}")
        add_app_log(f"Testing NAIP tile availability", "INFO")
        
        tile_response = requests.get(tile_url, verify=False, timeout=5)
        
        if tile_response.status_code == 200 and len(tile_response.content) > 1000:
            logging.info(f"NAIP tiles available - Status: {tile_response.status_code}")
            add_app_log(f"NAIP tiles AVAILABLE", "INFO")
            return True
        else:
            logging.error(f"NAIP tiles unavailable - Status: {tile_response.status_code}, Size: {len(tile_response.content)}")
            add_app_log(f"NAIP tiles UNAVAILABLE (service running but no imagery)", "ERROR")
            return False
            
    except requests.exceptions.Timeout as e:
        logging.error(f"NAIP endpoint TIMEOUT - {str(e)}")
        add_app_log(f"NAIP endpoint TIMEOUT", "ERROR")
        return False
    except requests.exceptions.ConnectionError as e:
        logging.error(f"NAIP endpoint CONNECTION ERROR - {str(e)}")
        add_app_log(f"NAIP endpoint CONNECTION ERROR", "ERROR")
        return False
    except Exception as e:
        logging.error(f"NAIP endpoint UNKNOWN ERROR - {type(e).__name__}: {str(e)}")
        add_app_log(f"NAIP endpoint ERROR: {type(e).__name__}", "ERROR")
        return False

# Test all basemap endpoints on startup
def test_all_basemaps():
    basemap_urls = {
        "Esri World Imagery": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer?f=json",
        "Google Satellite": "https://mt1.google.com/vt/lyrs=s&x=0&y=0&z=0",
        "Esri Clarity": "https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer?f=json",
    }
    
    results = {}
    for name, url in basemap_urls.items():
        results[name] = test_endpoint_availability(name, url)
    
    return results

# Check NAIP availability on startup
if 'naip_available' not in st.session_state:
    st.session_state.naip_available = test_naip_availability()

# Check all basemaps on first load
if 'basemap_status' not in st.session_state:
    with st.spinner("Testing basemap connections..."):
        st.session_state.basemap_status = test_all_basemaps()

# Initialize session state
if 'polygon_coords' not in st.session_state:
    st.session_state.polygon_coords = None
if 'polygon_center' not in st.session_state:
    st.session_state.polygon_center = None
if 'polygon_zoom' not in st.session_state:
    st.session_state.polygon_zoom = None
if 'map_center' not in st.session_state:
    st.session_state.map_center = [41.8781, -87.6298]  # Chicago
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 18
if 'show_layout' not in st.session_state:
    st.session_state.show_layout = False
if 'layout_params' not in st.session_state:
    st.session_state.layout_params = None
if 'calculation_results' not in st.session_state:
    st.session_state.calculation_results = None

# Sidebar for parameters
st.sidebar.header("Parking Configuration")

# Unit system toggle
unit_system = st.sidebar.radio(
    "Unit System",
    ["Imperial", "Metric"],
    horizontal=True,
    help="Choose between metric (meters) or imperial (feet) measurements"
)

# Conversion factors
if unit_system == "Imperial":
    length_conversion = 3.28084
    area_conversion = 10.764
    length_unit = "ft"
    area_unit = "sf"
else:
    length_conversion = 1.0
    area_conversion = 1.0
    length_unit = "m"
    area_unit = "m²"

st.sidebar.markdown("---")

# Basemap selection
basemap_options = [
    "Esri World Imagery",
    "Google Satellite",
    "Esri Clarity (High-Res)",
]

if st.session_state.naip_available:
    basemap_options.insert(3, "USDA NAIP (via Esri)")
else:
    st.sidebar.warning("⚠️ USDA NAIP imagery currently unavailable")

basemap = st.sidebar.selectbox("Basemap Layer", basemap_options)

if not st.session_state.naip_available:
    if st.sidebar.button("🔄 Test NAIP Connection"):
        with st.spinner("Testing NAIP endpoint..."):
            st.session_state.naip_available = test_naip_availability()
            if st.session_state.naip_available:
                st.sidebar.success("✓ NAIP is now available!")
                st.rerun()
            else:
                st.sidebar.error("✗ NAIP still unavailable")

if st.sidebar.button("🔄 Test All Basemaps"):
    with st.spinner("Testing all endpoints..."):
        st.session_state.basemap_status = test_all_basemaps()
        st.session_state.naip_available = test_naip_availability()
        
        all_working = all(st.session_state.basemap_status.values())
        if all_working and st.session_state.naip_available:
            st.sidebar.success("✓ All basemaps available!")
        else:
            failed = [name for name, status in st.session_state.basemap_status.items() if not status]
            if not st.session_state.naip_available:
                failed.append("NAIP")
            st.sidebar.warning(f"⚠️ Issues with: {', '.join(failed)}")

if 'basemap_status' in st.session_state:
    failed_basemaps = [name for name, status in st.session_state.basemap_status.items() if not status]
    if failed_basemaps:
        st.sidebar.warning(f"⚠️ Currently unavailable: {', '.join(failed_basemaps)}")

basemap_options.append("OpenStreetMap")

# Basemap information
basemap_info = {
    "Esri World Imagery": "**Update Frequency:** Quarterly to annually\n\n**Resolution:** 30cm-1m in urban areas\n\n**Coverage:** Global",
    "Google Satellite": "**Update Frequency:** Monthly to annually\n\n**Resolution:** 15cm-1m\n\n**Coverage:** Global",
    "Esri Clarity (High-Res)": "**Update Frequency:** Annually\n\n**Resolution:** 30-50cm\n\n**Coverage:** Global",
    "USDA NAIP (via Esri)": "**Update Frequency:** Every 2-3 years\n\n**Resolution:** 60cm-1m\n\n**Coverage:** Continental US only",
    "OpenStreetMap": "**Update Frequency:** Real-time\n\n**Resolution:** Vector data\n\n**Coverage:** Global"
}

st.sidebar.info(basemap_info[basemap])

parking_type = st.sidebar.selectbox(
    "Parking Type",
    ["Standard Perpendicular (90°)", "Angled (45°)", "Parallel", "Compact"]
)

layout_orientation = st.sidebar.selectbox(
    "Layout Orientation",
    [
        "Auto (Best Fit)", 
        "Row-Based (Horizontal)", 
        "Column-Based (Vertical)",
        "Perimeter + Center (High Efficiency)"
    ],
    help="Choose parking layout style"
)

# Configuration for Perimeter + Center layout
if layout_orientation == "Perimeter + Center (High Efficiency)":
    st.sidebar.markdown("### Perimeter + Center Configuration")
    
    include_corner_islands = st.sidebar.checkbox(
        "Include Corner Islands",
        value=True,
        help="Add landscaped islands in corners"
    )
    
    # Calculate required corner size based on mode
    if st.session_state.get('show_conservative', False):
        # Conservative: needs space depth + aisle = 19 + 26 = 45 ft
        required_corner_size = 45.0
    else:
        # Optimized: needs space depth + aisle = 16.4 + 19.7 = 36.1 ft  
        required_corner_size = 36.1
    
    if unit_system == "Imperial":
        corner_island_size_display = st.sidebar.number_input(
            f"Corner Island Size ({length_unit})",
            min_value=10.0,
            max_value=80.0,  # Increased max
            value=required_corner_size,  # Dynamic default!
            step=5.0,
            help=f"Recommended: {required_corner_size:.0f}ft for current settings"
        )
        corner_island_size = corner_island_size_display / length_conversion
    else:
        required_corner_size_m = required_corner_size / 3.28084
        corner_island_size = st.sidebar.number_input(
            f"Corner Island Size ({length_unit})",
            min_value=3.0,
            max_value=24.0,  # Increased max
            value=required_corner_size_m,
            step=1.0,
            help=f"Recommended: {required_corner_size_m:.1f}m for current settings"
        )
    
    center_aisle_count = st.sidebar.slider(
        "Center Parking Rows",
        min_value=1,
        max_value=3,
        value=1,
        help="Number of double-loaded parking rows in center"
    )

# Structure type selection
structure_type = st.sidebar.selectbox(
    "Structure Type",
    ["Surface Lot (2D)", "Parking Structure (3D)", "Underground Parking (3D)"],
    help="Choose surface lot for traditional 2D view, or structure/underground for multi-level 3D analysis"
)

# Multi-level settings for 3D structures
if structure_type != "Surface Lot (2D)":
    st.sidebar.markdown("### 🏢 Multi-Level Settings")
    
    if structure_type == "Parking Structure (3D)":
        num_levels = st.sidebar.number_input(
            "Number of Levels",
            min_value=1,
            max_value=10,
            value=3,
            help="Number of parking levels in the structure"
        )
        if unit_system == "Imperial":
            floor_height_display = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=8.0,
                max_value=16.0,
                value=11.5,
                step=0.5,
                help="Height between floors"
            )
            floor_height = floor_height_display / length_conversion
        else:
            floor_height = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=2.5,
                max_value=5.0,
                value=3.5,
                step=0.5,
                help="Height between floors"
            )
        ground_level = 0
    else:  # Underground
        num_levels = st.sidebar.number_input(
            "Number of Underground Levels",
            min_value=1,
            max_value=5,
            value=2,
            help="Number of underground parking levels"
        )
        if unit_system == "Imperial":
            floor_height_display = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=8.0,
                max_value=13.0,
                value=10.0,
                step=0.5,
                help="Height between underground floors"
            )
            floor_height = floor_height_display / length_conversion
        else:
            floor_height = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=2.5,
                max_value=4.0,
                value=3.0,
                step=0.5,
                help="Height between underground floors"
            )
        ground_level = 0
else:
    num_levels = 1
    floor_height = 0
    ground_level = 0

# Calculation method toggle
calculation_method = st.sidebar.radio(
    "Calculation Method",
    ["Efficiency Factor", "Area per Space (ITE Standard)"],
    help="Choose between efficiency factor method or industry-standard area per space"
)

st.sidebar.markdown("---")

with st.sidebar.expander("🅿️ Space Settings", expanded=True):
    if calculation_method == "Efficiency Factor":
        if parking_type == "Standard Perpendicular (90°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=16.4, min_value=14.8, max_value=19.7, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=19.7, min_value=16.4, max_value=26.2, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
            default_efficiency = 0.85
        elif parking_type == "Angled (45°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=18.0, min_value=16.4, max_value=21.3, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=13.1, min_value=11.5, max_value=19.7, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
            default_efficiency = 0.80
        elif parking_type == "Parallel":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=9.8, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=21.3, min_value=19.7, max_value=26.2, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=11.5, min_value=9.8, max_value=16.4, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
            default_efficiency = 0.65
        else:  # Compact
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=7.5, min_value=6.5, max_value=9.2, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=14.8, min_value=13.1, max_value=18.0, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=18.0, min_value=16.4, max_value=23.0, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
            default_efficiency = 0.87
        
        efficiency = st.slider(
            "Efficiency Factor",
            min_value=0.50,
            max_value=0.95,
            value=default_efficiency,
            step=0.05,
            help="Accounts for circulation, landscaping, and access"
        )
        
        st.info(f"**Efficiency Factor:** {efficiency*100}%\n\n⚠️ Practical estimates accounting for aisles, access routes, and pedestrian areas")

    else:  # Area per Space method
        if parking_type == "Standard Perpendicular (90°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=16.4, min_value=14.8, max_value=19.7, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=19.7, min_value=16.4, max_value=26.2, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 350
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
                default_area_per_space = 32.5
        elif parking_type == "Angled (45°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=18.0, min_value=16.4, max_value=21.3, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=13.1, min_value=11.5, max_value=19.7, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 400
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
                default_area_per_space = 37.2
        elif parking_type == "Parallel":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=9.8, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=21.3, min_value=19.7, max_value=26.2, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=11.5, min_value=9.8, max_value=16.4, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 500
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
                default_area_per_space = 46.5
        else:  # Compact
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=7.5, min_value=6.5, max_value=9.2, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=14.8, min_value=13.1, max_value=18.0, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=18.0, min_value=16.4, max_value=23.0, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 300
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
                default_area_per_space = 27.9
        
        if unit_system == "Imperial":
            area_per_space_display = st.number_input(
                f"Area per Space ({area_unit})",
                min_value=200.0,
                max_value=650.0,
                value=float(default_area_per_space),
                step=10.0,
                help="Total area including space + share of aisle. Based on ITE standards."
            )
            area_per_space = area_per_space_display / area_conversion
        else:
            area_per_space = st.number_input(
                f"Area per Space ({area_unit})",
                min_value=20.0,
                max_value=60.0,
                value=default_area_per_space,
                step=1.0,
                help="Total area including space + share of aisle. Based on ITE standards."
            )
        
        space_area = space_width * space_length
        efficiency = space_area / area_per_space if area_per_space > 0 else 0.85

st.sidebar.markdown("---")

with st.sidebar.expander("📚 Industry References"):
    st.markdown("""
    **Standards & Guidelines:**
    
    - **ITE (Institute of Transportation Engineers)**
      - *Parking Generation Manual* (5th Ed.)
      - *Trip Generation Manual* (11th Ed.)
    
    - **ULI (Urban Land Institute)**
      - *Dimensions of Parking* (6th Ed.)
    
    - **Local Standards:**
      - Check your local zoning code
      - Municipal parking requirements
      - ADA/accessibility standards
    
    **Space Dimensions (Typical):**
    - Standard: 2.4-2.7m × 4.9-5.5m (8-9' × 16-18')
    - Compact: 2.3-2.4m × 4.3-4.9m (7.5-8' × 14-16')
    - Accessible: 3.7m × 5.5m (12' × 18') (min)
    
    **Note:** Requirements vary by jurisdiction.
    Always verify with local codes.
    """)

# Address search
st.subheader("📍 Location Search")
search_col1, search_col2 = st.columns([3, 1])

with search_col1:
    address = st.text_input("Enter an address or place name", placeholder="e.g., 123 Main St, Chicago, IL")

with search_col2:
    st.write("")
    search_button = st.button("Search", type="primary")

if search_button and address:
    try:
        encoded_address = urllib.parse.quote(address)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded_address}&format=json&limit=1"
        
        logging.info(f"Geocoding request for address: {address}")
        add_app_log(f"Geocoding address: {address}", "INFO")
        
        response = requests.get(
            url, 
            verify=False,
            headers={'User-Agent': 'parking_estimator_app_v1'},
            timeout=10
        )
        
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        if response.status_code == 200:
            results = response.json()
            if results:
                location = results[0]
                st.session_state.map_center = [float(location['lat']), float(location['lon'])]
                st.session_state.map_zoom = 18
                st.success(f"✓ Found: {location.get('display_name', address)}")
                logging.info(f"Geocoding SUCCESS - Found: {location.get('display_name', address)}")
                add_app_log(f"Geocoding SUCCESS - Found location", "INFO")
            else:
                st.error("Address not found. Please try a different search term.")
                logging.warning(f"Geocoding returned no results for: {address}")
                add_app_log(f"Geocoding returned no results", "WARNING")
        else:
            st.error(f"Search failed with status code: {response.status_code}")
            logging.error(f"Geocoding FAILED - Status: {response.status_code}, Response: {response.text[:200]}")
            add_app_log(f"Geocoding FAILED - Status: {response.status_code}", "ERROR")
    except requests.exceptions.Timeout as e:
        st.error("Search timed out. Please try again.")
        logging.error(f"Geocoding TIMEOUT - {str(e)}")
        add_app_log(f"Geocoding TIMEOUT", "ERROR")
    except requests.exceptions.ConnectionError as e:
        st.error("Connection error. Please check your network.")
        logging.error(f"Geocoding CONNECTION ERROR - {str(e)}")
        add_app_log(f"Geocoding CONNECTION ERROR", "ERROR")
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        logging.error(f"Geocoding UNKNOWN ERROR - {type(e).__name__}: {str(e)}")
        add_app_log(f"Geocoding ERROR: {type(e).__name__}", "ERROR")

st.markdown("---")

# Add view mode selector
view_mode = st.radio(
    "View Mode",
    ["2D Map View", "3D Structure View"],
    horizontal=True,
    disabled=(structure_type == "Surface Lot (2D)")
)

if structure_type == "Surface Lot (2D)":
    st.info("💡 Select 'Parking Structure' or 'Underground Parking' in the sidebar to enable 3D view")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Draw Your Parking Area")
    
    # Show 3D view if enabled
    if view_mode == "3D Structure View" and structure_type != "Surface Lot (2D)" and st.session_state.get('show_layout'):
        st.markdown("### 🏗️ 3D Structure Visualization")
        
        if st.session_state.get('layout_params') and st.session_state.get('actual_spaces_drawn'):
            params = st.session_state.layout_params
            polygon_coords = params['polygon']
            
            col_3d1, col_3d2 = st.columns([2, 1])
            with col_3d1:
                view_style = st.selectbox(
                    "3D View Style",
                    ["Stacked (Compact)", "Exploded (All Levels)", "Exploded (Focus Mode)"],
                    help="Focus mode shows one level clearly with others transparent"
                )
            
            if view_style == "Exploded (Focus Mode)":
                with col_3d2:
                    if structure_type == "Underground Parking (3D)":
                        level_options = [f"B{i+1}" for i in range(num_levels)]
                    else:
                        level_options = [f"Level {i+1}" for i in range(num_levels)]
                    
                    focused_level = st.selectbox(
                        "Focus on Level",
                        level_options,
                        help="Selected level will be solid, others transparent"
                    )
                    if "B" in focused_level:
                        focused_level_num = int(focused_level.replace("B", "")) - 1
                    else:
                        focused_level_num = int(focused_level.replace("Level ", "")) - 1
            else:
                focused_level_num = None
            
            if 'parking_spaces_3d' in st.session_state:
                all_spaces_3d = []
                
                lats = [coord[1] for coord in polygon_coords]
                lons = [coord[0] for coord in polygon_coords]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                
                lat_range = max(lats) - min(lats)
                lon_range = max(lons) - min(lons)
                max_range = max(lat_range, lon_range)
                
                for level in range(num_levels):
                    if structure_type == "Underground Parking (3D)":
                        elevation = -floor_height * (level + 1)
                        level_name = f"B{level + 1}"
                    else:
                        elevation = floor_height * level
                        level_name = f"Level {level + 1}"
                    
                    if structure_type == "Underground Parking (3D)":
                        underground_colors = [
                            [0, 150, 255, 230],
                            [0, 200, 255, 230],
                            [100, 220, 255, 230],
                            [150, 240, 255, 230],
                            [200, 250, 255, 230],
                        ]
                        base_color = underground_colors[min(level, 4)]
                    else:
                        aboveground_colors = [
                            [0, 200, 0, 230],
                            [255, 230, 0, 230],
                            [255, 165, 0, 230],
                            [255, 50, 50, 230],
                            [200, 0, 255, 230],
                            [255, 20, 147, 230],
                            [0, 255, 255, 230],
                            [255, 100, 0, 230],
                            [220, 100, 255, 230],
                            [50, 255, 150, 230],
                        ]
                        base_color = aboveground_colors[min(level, 9)]
                    
                    if view_style == "Exploded (Focus Mode)" and focused_level_num is not None:
                        if level == focused_level_num:
                            color = base_color
                        else:
                            color = [base_color[0], base_color[1], base_color[2], 40]
                    else:
                        color = base_color
                    
                    if view_style in ["Exploded (All Levels)", "Exploded (Focus Mode)"]:
                        offset_multiplier = 1.5
                        horizontal_offset_lon = (level - num_levels/2) * max_range * offset_multiplier
                        horizontal_offset_lat = 0
                    else:
                        horizontal_offset_lon = 0
                        horizontal_offset_lat = 0
                    
                    for idx, space in enumerate(st.session_state.parking_spaces_3d):
                        offset_coords = [
                            (coord[0] + horizontal_offset_lon, coord[1] + horizontal_offset_lat) 
                            for coord in space['coords']
                        ]
                        
                        space_3d = {
                            'polygon': offset_coords,
                            'elevation': elevation,
                            'height': 2.5,
                            'color': color,
                            'level': level_name,
                            'space_id': f"{level_name}-{idx+1}",
                            'level_number': level + 1
                        }
                        all_spaces_3d.append(space_3d)
                
                layers = []
                
                polygon_layer = pdk.Layer(
                    "PolygonLayer",
                    all_spaces_3d,
                    get_polygon="polygon",
                    get_elevation="elevation",
                    elevation_scale=1,
                    extruded=True,
                    get_fill_color="color",
                    get_line_color=[255, 255, 255, 255],
                    line_width_min_pixels=2,
                    pickable=True,
                    wireframe=True,
                    auto_highlight=True,
                    get_elevation_weight="height",
                    material=True,
                    filled=True,
                )
                layers.append(polygon_layer)
                
                if view_style in ["Exploded (All Levels)", "Exploded (Focus Mode)"]:
                    zoom_level = 17
                else:
                    zoom_level = 18
                
                view_state = pdk.ViewState(
                    latitude=center_lat,
                    longitude=center_lon,
                    zoom=zoom_level,
                    pitch=45,
                    bearing=0,
                )
                
                deck = pdk.Deck(
                    layers=layers,
                    initial_view_state=view_state,
                    map_style="satellite",
                    tooltip={
                        "html": "<b>Level:</b> {level}<br/><b>Elevation:</b> {elevation}m<br/><b>Space:</b> {space_id}",
                        "style": {
                            "backgroundColor": "steelblue",
                            "color": "white",
                            "fontSize": "14px",
                            "padding": "10px"
                        }
                    },
                )
                
                st.pydeck_chart(deck, use_container_width=True, height=600)
                
                st.markdown("### Level Legend")
                legend_cols = st.columns(min(num_levels, 5))
                
                for level in range(num_levels):
                    if structure_type == "Underground Parking (3D)":
                        level_name = f"B{level + 1}"
                        underground_colors = [
                            [0, 150, 255],
                            [0, 200, 255],
                            [100, 220, 255],
                            [150, 240, 255],
                            [200, 250, 255],
                        ]
                        color = underground_colors[min(level, 4)]
                    else:
                        level_name = f"Level {level + 1}"
                        aboveground_colors = [
                            [0, 200, 0],
                            [255, 230, 0],
                            [255, 165, 0],
                            [255, 50, 50],
                            [200, 0, 255],
                            [255, 20, 147],
                            [0, 255, 255],
                            [255, 100, 0],
                            [220, 100, 255],
                            [50, 255, 150],
                        ]
                        color = aboveground_colors[min(level, 9)]
                    
                    col_idx = level % 5
                    with legend_cols[col_idx]:
                        st.markdown(
                            f'<div style="background-color: rgb({color[0]}, {color[1]}, {color[2]}); '
                            f'padding: 10px; border-radius: 5px; text-align: center; color: white; '
                            f'font-weight: bold; margin: 5px; border: 2px solid rgba(255,255,255,0.3);">{level_name}</div>',
                            unsafe_allow_html=True
                        )
                
                total_spaces_all_levels = st.session_state.actual_spaces_drawn * num_levels
                st.success(f"🏢 Total Spaces Across {num_levels} Level(s): **{total_spaces_all_levels:,}**")
            else:
                st.warning("Generate parking layout first to see 3D visualization")
        else:
            st.info("Draw a polygon and generate parking layout to see 3D structure")
    else:
        st.markdown("### 🗺️ 2D Map View" if structure_type != "Surface Lot (2D)" else "")
    
    basemap_endpoints = {
        "Esri World Imagery": {
            'url': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            'attr': 'Esri'
        },
        "Google Satellite": {
            'url': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
            'attr': 'Google'
        },
        "Esri Clarity (High-Res)": {
            'url': 'https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            'attr': 'Esri Clarity'
        },
        "USDA NAIP (via Esri)": {
            'url': 'https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer/tile/{z}/{y}/{x}',
            'attr': 'USDA NAIP'
        },
        "OpenStreetMap": {
            'url': 'OpenStreetMap',
            'attr': 'OpenStreetMap'
        }
    }
    
    selected = basemap_endpoints.get(basemap, basemap_endpoints["Esri World Imagery"])
    tiles = selected['url']
    attr = selected['attr']
    
    logging.info(f"Loading basemap: {basemap}")
    add_app_log(f"Loading basemap: {basemap}", "INFO")
    
    if st.session_state.get('polygon_center') and st.session_state.get('show_layout'):
        map_center = st.session_state.polygon_center
        map_zoom = st.session_state.polygon_zoom
        add_app_log(f"Using polygon center for map view", "INFO")
    elif st.session_state.get('polygon_center'):
        map_center = st.session_state.polygon_center
        map_zoom = st.session_state.polygon_zoom
    else:
        map_center = st.session_state.map_center
        map_zoom = st.session_state.map_zoom
    
    try:
        m = folium.Map(
            location=map_center,
            zoom_start=map_zoom,
            tiles=tiles,
            attr=attr
        )
        logging.info(f"Basemap {basemap} loaded successfully at {map_center}")
        add_app_log(f"Basemap {basemap} loaded successfully", "INFO")
    except Exception as e:
        logging.error(f"Failed to load basemap {basemap} - {type(e).__name__}: {str(e)}")
        add_app_log(f"Failed to load basemap {basemap}", "ERROR")
        map_center = st.session_state.get('polygon_center') or st.session_state.map_center
        map_zoom = st.session_state.get('polygon_zoom') or st.session_state.map_zoom
        
        m = folium.Map(
            location=map_center,
            zoom_start=map_zoom,
            tiles='OpenStreetMap',
            attr='OpenStreetMap'
        )
        st.warning(f"⚠️ Failed to load {basemap}, using OpenStreetMap instead")
        add_app_log(f"Fallback to OpenStreetMap", "WARNING")
    
    folium.plugins.Draw(
        export=False,
        position='topleft',
        draw_options={
            'polyline': False,
            'rectangle': True,
            'polygon': True,
            'circle': False,
            'marker': False,
            'circlemarker': False,
        },
        edit_options={'edit': True}
    ).add_to(m)
    
    # Add parking space layout if requested
    if st.session_state.get('show_layout', False) and st.session_state.get('layout_params'):
        params = st.session_state.layout_params
        polygon_coords = params['polygon']
        p_type = params['parking_type']
        
        # CONSERVATIVE VS OPTIMIZED LAYOUT MODE
        if st.session_state.get('show_conservative', False):
            # CONSERVATIVE MODE: Apply industry-standard conservative dimensions
            st.info("📐 **Conservative Layout Mode**: Using industry-standard conservative dimensions (larger spaces, wider aisles, landscaping buffers)")
            add_app_log(f"Conservative layout mode: applying conservative dimensions", "INFO")
            
            # Apply conservative dimension adjustments based on ULI & ITE standards
            if "Perpendicular" in p_type or "Compact" in p_type:
                # Conservative perpendicular: 9' x 19' spaces, 26' aisles
                space_w = 9.0 / length_conversion  # 9 ft (2.74m)
                space_l = 19.0 / length_conversion  # 19 ft (5.79m)
                aisle_w = 26.0 / length_conversion  # 26 ft (7.92m)
            elif "Angled" in p_type:
                # Conservative angled: 9' x 20' spaces, 16' aisles
                space_w = 9.0 / length_conversion
                space_l = 20.0 / length_conversion
                aisle_w = 16.0 / length_conversion
            else:  # Parallel
                # Conservative parallel: 9' x 24' spaces, 14' aisles
                space_w = 9.0 / length_conversion
                space_l = 24.0 / length_conversion
                aisle_w = 14.0 / length_conversion
            
            # Add perimeter buffer (landscaping requirement: 10 ft)
            perimeter_buffer = 10.0 / length_conversion  # 10 ft (3.05m)
                        
        else:
            # OPTIMIZED MODE: Use user's specified dimensions from params
            add_app_log(f"Optimized layout mode: using user dimensions", "INFO")
            perimeter_buffer = 0  # No buffer for optimized
            
            # Use params dimensions (already set)
            space_w = params['space_width']
            space_l = params['space_length']
            aisle_w = params['aisle_width']
        
        # Convert polygon to Shapely polygon (in lat/lon)
        poly_latlon = Polygon([(lon, lat) for lon, lat in polygon_coords])
        bounds = poly_latlon.bounds  # (minx, miny, maxx, maxy)
        
        # Calculate approximate meters per degree at this latitude
        center_lat = (bounds[1] + bounds[3]) / 2
        lon_to_m = 111320 * np.cos(np.radians(center_lat))
        lat_to_m = 110540
        
        # Apply perimeter buffer for conservative mode
        original_bounds = bounds  # Store for buffer visualization
        if st.session_state.get('show_conservative', False) and perimeter_buffer > 0:
            buffer_deg_lon = perimeter_buffer / lon_to_m
            buffer_deg_lat = perimeter_buffer / lat_to_m
            
            # Shrink the usable area by buffer
            bounds = (
                bounds[0] + buffer_deg_lon,  # minx
                bounds[1] + buffer_deg_lat,  # miny
                bounds[2] - buffer_deg_lon,  # maxx
                bounds[3] - buffer_deg_lat   # maxy
            )
            
            # Draw landscaping buffer zone (visual indicator)
            outer_buffer_coords = [
                (original_bounds[0], original_bounds[1]),
                (original_bounds[2], original_bounds[1]),
                (original_bounds[2], original_bounds[3]),
                (original_bounds[0], original_bounds[3]),
                (original_bounds[0], original_bounds[1])
            ]
            
            inner_buffer_coords = [
                (bounds[0], bounds[1]),
                (bounds[2], bounds[1]),
                (bounds[2], bounds[3]),
                (bounds[0], bounds[3]),
                (bounds[0], bounds[1])
            ]
            
            # Draw outer boundary
            folium.Polygon(
                locations=[(lat, lon) for lon, lat in outer_buffer_coords],
                color='#2d5016',
                weight=3,
                fill=False,
                popup='Landscaping Buffer Zone (Conservative Mode)'
            ).add_to(m)
            
            # Draw inner usable boundary
            folium.Polygon(
                locations=[(lat, lon) for lon, lat in inner_buffer_coords],
                color='#4a7c28',
                weight=2,
                fill=False,
                dash_array='5, 5',
                popup='Usable Parking Area'
            ).add_to(m)
        
        # Generate parking spaces
        parking_spaces = []

        # Analyze polygon dimensions
        poly_width = bounds[2] - bounds[0]
        poly_height = bounds[3] - bounds[1]
        aspect_ratio = poly_width / poly_height if poly_height > 0 else 1

        # Determine layout orientation
        if layout_orientation == "Auto (Best Fit)":
            if aspect_ratio > 1.2:
                use_rows = True
                use_columns = False
                use_perimeter_center = False
            elif aspect_ratio < 0.8:
                use_rows = False
                use_columns = True
                use_perimeter_center = False
            else:
                use_rows = True
                use_columns = False
                use_perimeter_center = False
        elif layout_orientation == "Row-Based (Horizontal)":
            use_rows = True
            use_columns = False
            use_perimeter_center = False
        elif layout_orientation == "Column-Based (Vertical)":
            use_rows = False
            use_columns = True
            use_perimeter_center = False
        elif layout_orientation == "Perimeter + Center (High Efficiency)":
            use_rows = False
            use_columns = False
            use_perimeter_center = True
        else:
            use_rows = True
            use_columns = False
            use_perimeter_center = False

        def create_space_coords(x, y, width_deg, length_deg, orientation='horizontal', direction=1, angle_rad=0):
            """Create parking space coordinates"""
            if orientation == 'horizontal':
                if angle_rad == 0:  # Perpendicular
                    if direction == 1:
                        return [
                            (x, y),
                            (x + width_deg, y),
                            (x + width_deg, y + length_deg),
                            (x, y + length_deg),
                            (x, y)
                        ]
                    else:
                        return [
                            (x, y),
                            (x + width_deg, y),
                            (x + width_deg, y - length_deg),
                            (x, y - length_deg),
                            (x, y)
                        ]
                else:  # Angled
                    offset = length_deg * np.sin(angle_rad)
                    if direction == 1:
                        return [
                            (x, y),
                            (x + width_deg, y),
                            (x + width_deg + offset, y + length_deg * np.cos(angle_rad)),
                            (x + offset, y + length_deg * np.cos(angle_rad)),
                            (x, y)
                        ]
                    else:
                        return [
                            (x, y),
                            (x + width_deg, y),
                            (x + width_deg - offset, y - length_deg * np.cos(angle_rad)),
                            (x - offset, y - length_deg * np.cos(angle_rad)),
                            (x, y)
                        ]
            else:  # vertical orientation
                if angle_rad == 0:  # Perpendicular
                    if direction == 1:
                        return [
                            (x, y),
                            (x + length_deg, y),
                            (x + length_deg, y + width_deg),
                            (x, y + width_deg),
                            (x, y)
                        ]
                    else:
                        return [
                            (x, y),
                            (x - length_deg, y),
                            (x - length_deg, y + width_deg),
                            (x, y + width_deg),
                            (x, y)
                        ]
                else:  # Angled vertical
                    offset = length_deg * np.sin(angle_rad)
                    if direction == 1:
                        return [
                            (x, y),
                            (x + length_deg * np.cos(angle_rad), y),
                            (x + length_deg * np.cos(angle_rad), y + width_deg + offset),
                            (x, y + width_deg + offset),
                            (x, y)
                        ]
                    else:
                        return [
                            (x, y),
                            (x - length_deg * np.cos(angle_rad), y),
                            (x - length_deg * np.cos(angle_rad), y + width_deg - offset),
                            (x, y + width_deg - offset),
                            (x, y)
                        ]

        # PERIMETER + CENTER LAYOUT
        # PERIMETER + CENTER LAYOUT (CORRECTED - NO OVERLAPS)
        if use_perimeter_center:
            space_w_deg = space_w / lon_to_m
            space_l_deg = space_l / lat_to_m
            aisle_w_deg = aisle_w / lat_to_m
            aisle_w_deg_lon = aisle_w / lon_to_m
            
            # ALWAYS define corner exclusion zones
            corner_size_deg_lon = corner_island_size / lon_to_m
            corner_size_deg_lat = corner_island_size / lat_to_m

            corner_exclusion_zones = [
                Polygon([
                    (bounds[0], bounds[3] - corner_size_deg_lat),
                    (bounds[0] + corner_size_deg_lon, bounds[3] - corner_size_deg_lat),
                    (bounds[0] + corner_size_deg_lon, bounds[3]),
                    (bounds[0], bounds[3])
                ]),
                Polygon([
                    (bounds[2] - corner_size_deg_lon, bounds[3] - corner_size_deg_lat),
                    (bounds[2], bounds[3] - corner_size_deg_lat),
                    (bounds[2], bounds[3]),
                    (bounds[2] - corner_size_deg_lon, bounds[3])
                ]),
                Polygon([
                    (bounds[0], bounds[1]),
                    (bounds[0] + corner_size_deg_lon, bounds[1]),
                    (bounds[0] + corner_size_deg_lon, bounds[1] + corner_size_deg_lat),
                    (bounds[0], bounds[1] + corner_size_deg_lat)
                ]),
                Polygon([
                    (bounds[2] - corner_size_deg_lon, bounds[1]),
                    (bounds[2], bounds[1]),
                    (bounds[2], bounds[1] + corner_size_deg_lat),
                    (bounds[2] - corner_size_deg_lon, bounds[1] + corner_size_deg_lat)
                ])
            ]

            def conflicts_with_corners(space_poly):
                """Check if parking space conflicts with corner exclusion zones"""
                for corner_zone in corner_exclusion_zones:
                    if space_poly.intersects(corner_zone) or corner_zone.contains(space_poly.centroid):
                        return True
                return False

            # Only DRAW corner islands if checkbox enabled
            if include_corner_islands:
                for corner_zone in corner_exclusion_zones:
                    corner_coords = list(corner_zone.exterior.coords)
                    folium.Polygon(
                        locations=[(lat, lon) for lon, lat in corner_coords],
                        color='#2d5016',
                        weight=2,
                        fill=True,
                        fillColor='#4a7c28',
                        fillOpacity=0.7,
                        popup='Corner Landscape Island'
                    ).add_to(m)
            
            # ===== CRITICAL: Calculate boundaries with NO OVERLAP =====
            # Perimeter spaces need: space_depth + aisle
            # Center needs to start AFTER perimeter spaces + another circulation aisle
            
            # For TOP perimeter:
            # - Spaces face DOWN (into lot)
            # - Space bottoms are at: bounds[3] - aisle_w_deg - space_l_deg
            # - Space tops are at: bounds[3] - aisle_w_deg
            # - Aisle is from: bounds[3] - aisle_w_deg to bounds[3]
            
            # For BOTTOM perimeter:
            # - Spaces face UP (into lot)
            # - Space bottoms are at: bounds[1]
            # - Space tops are at: bounds[1] + space_l_deg
            # - Aisle is from: bounds[1] + space_l_deg to bounds[1] + space_l_deg + aisle_w_deg
            
            # For LEFT perimeter:
            # - Spaces face RIGHT
            # - Left edge: bounds[0]
            # - Right edge of spaces: bounds[0] + space_l_deg
            # - Aisle: bounds[0] + space_l_deg to bounds[0] + space_l_deg + aisle_w_deg_lon
            
            # For RIGHT perimeter:
            # - Spaces face LEFT
            # - Right edge: bounds[2]
            # - Left edge of spaces: bounds[2] - space_l_deg
            # - Aisle: bounds[2] - space_l_deg - aisle_w_deg_lon to bounds[2] - space_l_deg
            
            # Center area must start AFTER perimeter + perimeter aisle + circulation aisle
            center_bounds = {
                'left': bounds[0] + space_l_deg + (aisle_w_deg_lon * 2),      # LEFT perimeter + 2 aisles
                'right': bounds[2] - space_l_deg - (aisle_w_deg_lon * 2),     # RIGHT perimeter + 2 aisles
                'bottom': bounds[1] + space_l_deg + (aisle_w_deg * 2),        # BOTTOM perimeter + 2 aisles
                'top': bounds[3] - space_l_deg - (aisle_w_deg * 2)            # TOP perimeter + 2 aisles
            }
            
            # 1. TOP PERIMETER - Spaces facing DOWN (into lot)
            current_x = bounds[0]
            # Spaces bottom at bounds[3] - aisle - space_depth, top at bounds[3] - aisle
            top_space_bottom = bounds[3] - aisle_w_deg - space_l_deg
            
            while current_x < bounds[2]:
                space_coords = [
                    (current_x, top_space_bottom),                      # Bottom-left
                    (current_x + space_w_deg, top_space_bottom),        # Bottom-right
                    (current_x + space_w_deg, top_space_bottom + space_l_deg),  # Top-right
                    (current_x, top_space_bottom + space_l_deg),        # Top-left
                    (current_x, top_space_bottom)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_x += space_w_deg
            
            # 2. BOTTOM PERIMETER - Spaces facing UP (into lot)
            current_x = bounds[0]
            # Spaces from bounds[1] to bounds[1] + space_depth
            bottom_space_bottom = bounds[1] + aisle_w_deg
            
            while current_x < bounds[2]:
                space_coords = [
                    (current_x, bottom_space_bottom),
                    (current_x + space_w_deg, bottom_space_bottom),
                    (current_x + space_w_deg, bottom_space_bottom + space_l_deg),
                    (current_x, bottom_space_bottom + space_l_deg),
                    (current_x, bottom_space_bottom)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_x += space_w_deg
            
            # 3. LEFT PERIMETER - Spaces facing RIGHT (into lot)
            current_y = bounds[1]
            # Spaces from bounds[0] to bounds[0] + space_depth
            left_space_left = bounds[0] + aisle_w_deg_lon
            
            while current_y < bounds[3]:
                space_coords = [
                    (left_space_left, current_y),
                    (left_space_left + space_l_deg, current_y),
                    (left_space_left + space_l_deg, current_y + space_w_deg),
                    (left_space_left, current_y + space_w_deg),
                    (left_space_left, current_y)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_y += space_w_deg
            
            # 4. RIGHT PERIMETER - Spaces facing LEFT (into lot)
            current_y = bounds[1]
            # Spaces from bounds[2] - space_depth to bounds[2]
            right_space_left = bounds[2] - space_l_deg - aisle_w_deg_lon
            
            while current_y < bounds[3]:
                space_coords = [
                    (right_space_left, current_y),
                    (right_space_left + space_l_deg, current_y),
                    (right_space_left + space_l_deg, current_y + space_w_deg),
                    (right_space_left, current_y + space_w_deg),
                    (right_space_left, current_y)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_y += space_w_deg
            
            # 5. CENTER DOUBLE-LOADED ROWS (with proper clearance)
            center_height = center_bounds['top'] - center_bounds['bottom']
            center_width = center_bounds['right'] - center_bounds['left']

            row_height = (2 * space_l_deg) + aisle_w_deg
            total_height_needed = (center_aisle_count * row_height) + ((center_aisle_count - 1) * aisle_w_deg)

            if center_height > total_height_needed and center_width > space_w_deg:
                center_y = (center_bounds['bottom'] + center_bounds['top']) / 2
                
                if center_aisle_count == 1:
                    row_positions = [center_y]
                else:
                    row_spacing = row_height + aisle_w_deg
                    total_group_height = (center_aisle_count - 1) * row_spacing
                    first_row_y = center_y - (total_group_height / 2)
                    row_positions = [first_row_y + (i * row_spacing) for i in range(center_aisle_count)]
                
                for row_idx, row_center_y in enumerate(row_positions):
                    # Spaces on top of aisle (facing down)
                    current_x = center_bounds['left']
                    aisle_top_y = row_center_y + (aisle_w_deg / 2)
                    
                    while current_x < center_bounds['right']:
                        space_coords = [
                            (current_x, aisle_top_y),
                            (current_x + space_w_deg, aisle_top_y),
                            (current_x + space_w_deg, aisle_top_y + space_l_deg),
                            (current_x, aisle_top_y + space_l_deg),
                            (current_x, aisle_top_y)
                        ]
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_x += space_w_deg
                    
                    # Spaces on bottom of aisle (facing up)
                    current_x = center_bounds['left']
                    aisle_bottom_y = row_center_y - (aisle_w_deg / 2)
                    
                    while current_x < center_bounds['right']:
                        space_coords = [
                            (current_x, aisle_bottom_y - space_l_deg),
                            (current_x + space_w_deg, aisle_bottom_y - space_l_deg),
                            (current_x + space_w_deg, aisle_bottom_y),
                            (current_x, aisle_bottom_y),
                            (current_x, aisle_bottom_y - space_l_deg)
                        ]
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid) and not conflicts_with_corners(space_poly):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_x += space_w_deg
            else:
                if center_aisle_count > 1:
                    add_app_log(f"Lot too small for {center_aisle_count} center rows", "WARNING")

        # ROW-BASED AND COLUMN-BASED LAYOUTS
        elif "Perpendicular" in p_type or "Compact" in p_type:
            if use_rows:
                current_y = bounds[1]
                row_num = 0
                
                while current_y < bounds[3]:
                    current_x = bounds[0]
                    space_direction = 1 if row_num % 2 == 0 else -1
                    
                    while current_x < bounds[2]:
                        space_w_deg = space_w / lon_to_m
                        space_l_deg = space_l / lat_to_m
                        
                        space_coords = create_space_coords(
                            current_x, current_y, space_w_deg, space_l_deg,
                            orientation='horizontal', direction=space_direction
                        )
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_x += space_w_deg
                    
                    aisle_w_deg = aisle_w / lat_to_m
                    current_y += (space_l_deg if space_direction == 1 else 0) + aisle_w_deg
                    row_num += 1
            
            if use_columns:
                current_x = bounds[0]
                col_num = 0
                
                while current_x < bounds[2]:
                    current_y = bounds[1]
                    space_direction = 1 if col_num % 2 == 0 else -1
                    
                    while current_y < bounds[3]:
                        space_w_deg = space_w / lon_to_m
                        space_l_deg = space_l / lat_to_m
                        
                        space_coords = create_space_coords(
                            current_x, current_y, space_w_deg, space_l_deg,
                            orientation='vertical', direction=space_direction
                        )
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_y += space_w_deg
                    
                    aisle_w_deg = aisle_w / lon_to_m
                    current_x += (space_l_deg if space_direction == 1 else 0) + aisle_w_deg
                    col_num += 1

        elif "Angled" in p_type:
            angle_rad = np.radians(45)
            
            if use_rows:
                current_y = bounds[1]
                row_num = 0
                
                while current_y < bounds[3]:
                    current_x = bounds[0]
                    angle_direction = 1 if row_num % 2 == 0 else -1
                    
                    while current_x < bounds[2]:
                        space_w_deg = space_w / lon_to_m
                        space_l_deg = space_l / lat_to_m
                        
                        space_coords = create_space_coords(
                            current_x, current_y, space_w_deg, space_l_deg,
                            orientation='horizontal', direction=angle_direction, angle_rad=angle_rad
                        )
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_x += space_w_deg
                    
                    aisle_w_deg = aisle_w / lat_to_m
                    current_y += (space_l_deg * np.cos(angle_rad) if angle_direction == 1 else 0) + aisle_w_deg
                    row_num += 1
            
            if use_columns:
                current_x = bounds[0]
                col_num = 0
                
                while current_x < bounds[2]:
                    current_y = bounds[1]
                    angle_direction = 1 if col_num % 2 == 0 else -1
                    
                    while current_y < bounds[3]:
                        space_w_deg = space_w / lon_to_m
                        space_l_deg = space_l / lat_to_m
                        
                        space_coords = create_space_coords(
                            current_x, current_y, space_w_deg, space_l_deg,
                            orientation='vertical', direction=angle_direction, angle_rad=angle_rad
                        )
                        
                        space_poly = Polygon(space_coords)
                        if poly_latlon.contains(space_poly.centroid):
                            display_coords = [[(lon, lat) for lon, lat in space_coords]]
                            parking_spaces.append(display_coords)
                        
                        current_y += space_w_deg
                    
                    aisle_w_deg = aisle_w / lon_to_m
                    current_x += (space_l_deg * np.cos(angle_rad) if angle_direction == 1 else 0) + aisle_w_deg
                    col_num += 1

        elif "Parallel" in p_type:
            current_x = bounds[0]
            
            while current_x < bounds[2]:
                space_w_deg = space_w / lon_to_m
                space_l_deg = space_l / lat_to_m
                
                # Bottom edge
                space_coords = [
                    (current_x, bounds[1]),
                    (current_x + space_l_deg, bounds[1]),
                    (current_x + space_l_deg, bounds[1] + space_w_deg),
                    (current_x, bounds[1] + space_w_deg),
                    (current_x, bounds[1])
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                # Top edge
                space_coords = [
                    (current_x, bounds[3] - space_w_deg),
                    (current_x + space_l_deg, bounds[3] - space_w_deg),
                    (current_x + space_l_deg, bounds[3]),
                    (current_x, bounds[3]),
                    (current_x, bounds[3] - space_w_deg)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_x += space_l_deg
            
            current_y = bounds[1]
            
            while current_y < bounds[3]:
                space_w_deg = space_w / lon_to_m
                space_l_deg = space_l / lat_to_m
                
                # Left edge
                space_coords = [
                    (bounds[0], current_y),
                    (bounds[0] + space_w_deg, current_y),
                    (bounds[0] + space_w_deg, current_y + space_l_deg),
                    (bounds[0], current_y + space_l_deg),
                    (bounds[0], current_y)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                # Right edge
                space_coords = [
                    (bounds[2] - space_w_deg, current_y),
                    (bounds[2], current_y),
                    (bounds[2], current_y + space_l_deg),
                    (bounds[2] - space_w_deg, current_y + space_l_deg),
                    (bounds[2] - space_w_deg, current_y)
                ]
                
                space_poly = Polygon(space_coords)
                if poly_latlon.contains(space_poly.centroid):
                    display_coords = [[(lon, lat) for lon, lat in space_coords]]
                    parking_spaces.append(display_coords)
                
                current_y += space_l_deg
        
        # Add parking spaces to map
        for space_coords in parking_spaces:
            folium.Polygon(
                locations=[(lat, lon) for lon, lat in space_coords[0]],
                color='#FFA500',
                weight=2,
                fill=True,
                fillColor='#FFD700',
                fillOpacity=0.3,
                popup='Parking Space'
            ).add_to(m)
        
        # Store actual number of spaces drawn WITH layout type
        st.session_state.actual_spaces_drawn = len(parking_spaces)
        st.session_state.current_layout_type = "conservative" if st.session_state.get('show_conservative', False) else "optimized"

        # Store both values separately for comparison
        if st.session_state.get('show_conservative', False):
            st.session_state.conservative_spaces = len(parking_spaces)
        else:
            st.session_state.optimized_spaces = len(parking_spaces)
        
        # Store parking spaces for 3D visualization
        parking_spaces_3d = []
        for space in parking_spaces:
            parking_spaces_3d.append({
                'coords': space[0],
                'type': 'parking'
            })
        st.session_state.parking_spaces_3d = parking_spaces_3d
        
        add_app_log(f"Drew {len(parking_spaces)} parking spaces on map", "INFO")
        
        # Add legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 180px; height: 90px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <p style="margin: 0; color: black;"><strong>Legend</strong></p>
        <p style="margin: 5px 0; color: black;"><span style="color: #FFA500;">■</span> Parking Space</p>
        <p style="margin: 5px 0; font-size: 12px; color: black;">Total: ''' + str(len(parking_spaces)) + ''' spaces</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
    
    # Display map
    map_data = st_folium(m, width=800, height=600, key="map")

with col2:
    st.subheader("Results")
    
    # Process drawn polygon
    if map_data and map_data.get('all_drawings'):
        drawings = map_data['all_drawings']
        
        if len(drawings) > 0:
            last_drawing = drawings[-1]
            
            if last_drawing['geometry']['type'] in ['Polygon', 'Rectangle']:
                coords = last_drawing['geometry']['coordinates'][0]
                st.session_state.polygon_coords = coords
                
                lats = [coord[1] for coord in coords]
                lons = [coord[0] for coord in coords]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                st.session_state.polygon_center = [center_lat, center_lon]
                st.session_state.polygon_zoom = 19
                
                add_app_log(f"Captured polygon center: [{center_lat:.6f}, {center_lon:.6f}]", "INFO")
                
                lat_to_m = 111000
                lon_to_m = 82000
                
                add_app_log(f"Polygon drawn with {len(coords)} vertices", "INFO")
                
                coords_m = [(lon * lon_to_m, lat * lat_to_m) for lon, lat in coords]
                poly = Polygon(coords_m)
                area_m2 = poly.area
                
                add_app_log(f"Calculated area: {area_m2:,.1f} m²", "INFO")
                
                space_area = space_width * space_length
                
                if calculation_method == "Area per Space (ITE Standard)":
                    estimated_spaces_per_level = int(area_m2 / area_per_space)
                    calc_method_stored = "Area per Space (ITE Standard)"
                    area_per_space_stored = area_per_space
                else:
                    estimated_spaces_per_level = int((area_m2 * efficiency) / space_area)
                    calc_method_stored = "Efficiency Factor"
                    area_per_space_stored = area_m2 / estimated_spaces_per_level if estimated_spaces_per_level > 0 else space_area / efficiency
                
                estimated_spaces = estimated_spaces_per_level * num_levels
                
                add_app_log(f"Estimated parking spaces: {estimated_spaces} ({estimated_spaces_per_level}/level × {num_levels} levels)", "INFO")
                
                st.session_state.calculation_results = {
                    'area_m2': area_m2,
                    'space_area': space_area,
                    'estimated_spaces': estimated_spaces,
                    'estimated_spaces_per_level': estimated_spaces_per_level,
                    'num_levels': num_levels,
                    'efficiency': efficiency,
                    'space_width': space_width,
                    'space_length': space_length,
                    'aisle_width': aisle_width,
                    'calculation_method': calc_method_stored,
                    'area_per_space': area_per_space_stored,
                    'structure_type': structure_type
                }
    
    # Display results
    if st.session_state.calculation_results:
        results = st.session_state.calculation_results
        
        if results.get('structure_type') != "Surface Lot (2D)":
            st.info(f"🏢 **{results.get('structure_type')}**\n\n{results.get('num_levels', 1)} Level(s)")
        
        st.markdown("### 📏 Lot Dimensions")
        if unit_system == "Imperial":
            st.metric("Total Lot Area (per level)", f"{results['area_m2'] * area_conversion:,.1f} {area_unit}")
        else:
            st.metric("Total Lot Area (per level)", f"{results['area_m2']:,.1f} {area_unit}")
            st.caption(f"= {results['area_m2'] * 10.764:,.1f} ft²")
        
        st.markdown("---")
        st.markdown("### 📊 Capacity Comparison")
        
        display_area_per_space = results.get('area_per_space', 0)
        if display_area_per_space is None or display_area_per_space == 0:
            display_area_per_space = results['area_m2'] / results['estimated_spaces'] if results['estimated_spaces'] > 0 else 350 / area_conversion
        
        # Show planning estimate - DIFFERENT BASED ON METHOD
        if results.get('calculation_method') == "Area per Space (ITE Standard)":
            if unit_system == "Imperial":
                area_per_space_display = display_area_per_space * area_conversion
            else:
                area_per_space_display = display_area_per_space
            
            if results.get('num_levels', 1) > 1:
                st.markdown(f"**📐 Planning Estimate** (ITE Standard: {area_per_space_display:.0f} {area_unit}/space)")
                st.metric("Conservative Estimate (per level)", f"{results.get('estimated_spaces_per_level', 0):,}")
                st.metric("Conservative Total", f"{results['estimated_spaces']:,}", 
                         help=f"Based on ITE standard: {area_per_space_display:.0f} {area_unit} per space")
            else:
                st.markdown(f"**📐 Planning Estimate** (ITE Standard: {area_per_space_display:.0f} {area_unit}/space)")
                st.metric("Conservative Estimate", f"{results['estimated_spaces']:,}",
                         help=f"Based on ITE standard: {area_per_space_display:.0f} {area_unit} per space")
        else:
            # EFFICIENCY FACTOR METHOD
            efficiency_pct = results.get('efficiency', 0.85) * 100
            
            if results.get('num_levels', 1) > 1:
                st.markdown(f"**📐 Planning Estimate** (Based on {efficiency_pct:.0f}% efficiency factor)")
                st.metric("Conservative Estimate (per level)", f"{results.get('estimated_spaces_per_level', 0):,}")
                st.metric("Conservative Total", f"{results['estimated_spaces']:,}", 
                         help=f"Calculated using {efficiency_pct:.0f}% efficiency factor")
            else:
                st.markdown(f"**📐 Planning Estimate** (Based on {efficiency_pct:.0f}% efficiency factor)")
                st.metric("Conservative Estimate", f"{results['estimated_spaces']:,}",
                         help=f"Calculated using {efficiency_pct:.0f}% efficiency factor")
        
        st.caption("⚠️ This is a conservative planning estimate that includes aisles, circulation, landscaping, and buffer areas.")
        
        # Show actual drawn spaces
        if st.session_state.get('show_layout') and st.session_state.get('actual_spaces_drawn'):
            actual_per_level = st.session_state.actual_spaces_drawn
            actual_total = actual_per_level * results.get('num_levels', 1)
            
            actual_area_per_space = results['area_m2'] / actual_per_level if actual_per_level > 0 else 0
            
            current_layout = st.session_state.get('current_layout_type', 'optimized')
            
            st.markdown("---")
            
            if current_layout == "conservative":
                st.markdown("**📐 Conservative Layout** (Currently displayed)")
            else:
                st.markdown("**🎯 Optimized Layout** (Currently displayed)")
            
            if results.get('num_levels', 1) > 1:
                st.metric("Actual Spaces (per level)", f"{actual_per_level:,}")
                st.metric("Actual Total Spaces", f"{actual_total:,}",
                         delta=f"{actual_total - results['estimated_spaces']:+,} vs estimate",
                         delta_color="normal")
            else:
                st.metric("Actual Parking Spaces", f"{actual_per_level:,}", 
                         delta=f"{actual_per_level - results['estimated_spaces']:+,} vs estimate",
                         delta_color="normal")
            
            if unit_system == "Imperial":
                st.caption(f"✅ Achieved: {actual_area_per_space * area_conversion:.0f} {area_unit}/space")
            else:
                st.caption(f"✅ Achieved: {actual_area_per_space:.1f} {area_unit}/space")
            
            # Show comparison if both layouts generated
            # Show comparison if both layouts generated
            if 'optimized_spaces' in st.session_state and 'conservative_spaces' in st.session_state:
                # ADD SAFETY CHECK: Make sure values exist and aren't None
                opt_val = st.session_state.optimized_spaces
                cons_val = st.session_state.conservative_spaces
                
                if opt_val is not None and cons_val is not None:
                    st.markdown("---")
                    st.markdown("**📊 Layout Comparison:**")
                    
                    opt_spaces = opt_val * results.get('num_levels', 1)
                    cons_spaces = cons_val * results.get('num_levels', 1)
                    
                    col_comp1, col_comp2 = st.columns(2)
                    with col_comp1:
                        st.metric("Optimized Total", f"{opt_spaces:,}")
                    with col_comp2:
                        st.metric("Conservative Total", f"{cons_spaces:,}")
                    
                    difference = opt_spaces - cons_spaces
                    if difference > 0:
                        st.caption(f"💡 Optimized layout fits **{difference:,} more spaces** (+{(difference/cons_spaces*100):.1f}%)")
                    else:
                        st.caption(f"ℹ️ Layouts have similar capacity")
        
        st.markdown("---")
        st.markdown("**📋 Configuration Details:**")
        
        if unit_system == "Imperial":
            st.write(f"• Space size: {results['space_width'] * length_conversion:.1f}{length_unit} × {results['space_length'] * length_conversion:.1f}{length_unit}")
            st.write(f"• Space area: {results['space_area'] * area_conversion:.1f} {area_unit}")
            st.write(f"• Aisle width: {results['aisle_width'] * length_conversion:.1f}{length_unit}")
        else:
            st.write(f"• Space size: {results['space_width']:.1f}{length_unit} × {results['space_length']:.1f}{length_unit}")
            st.write(f"• Space area: {results['space_area']:.1f} {area_unit}")
            st.write(f"• Aisle width: {results['aisle_width']:.1f}{length_unit}")
        
        if 'calculation_method' in results:
            if results['calculation_method'] == "Area per Space (ITE Standard)":
                if unit_system == "Imperial":
                    st.write(f"• Planning ratio: {display_area_per_space * area_conversion:.1f} {area_unit}/space")
                else:
                    st.write(f"• Planning ratio: {display_area_per_space:.1f} {area_unit}/space")
                st.write(f"• Method: ITE Planning Standard")
            else:
                st.write(f"• Efficiency: {results['efficiency']*100}%")
                st.write(f"• Method: Efficiency Factor")
        
        st.markdown("---")
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("🎯 Optimized Layout", key="generate_layout_btn", type="primary"):
                if st.session_state.polygon_coords:
                    st.session_state.show_layout = True
                    st.session_state.show_conservative = False
                    st.session_state.layout_params = {
                        'polygon': st.session_state.polygon_coords,
                        'space_width': space_width,
                        'space_length': space_length,
                        'aisle_width': aisle_width,
                        'parking_type': parking_type,
                        'estimated_spaces': results['estimated_spaces']
                    }
                    add_app_log(f"User requested optimized parking layout", "INFO")
                    st.rerun()
        
        with col_btn2:
            if st.button("📐 Conservative Layout", key="generate_conservative_btn"):
                if st.session_state.polygon_coords:
                    st.session_state.show_layout = True
                    st.session_state.show_conservative = True
                    st.session_state.layout_params = {
                        'polygon': st.session_state.polygon_coords,
                        'space_width': space_width,
                        'space_length': space_length,
                        'aisle_width': aisle_width,
                        'parking_type': parking_type,
                        'estimated_spaces': results['estimated_spaces']
                    }
                    add_app_log(f"User requested conservative parking layout", "INFO")
                    st.rerun()
        
        with col_btn3:
            if st.session_state.get('show_layout', False):
                if st.button("🗑️ Clear Layout", key="clear_layout_btn"):
                    st.session_state.show_layout = False
                    st.session_state.show_conservative = False
                    st.session_state.actual_spaces_drawn = None
                    st.session_state.layout_params = None
                    st.session_state.calculation_results = None  # ← ADD THIS LINE
                    st.session_state.optimized_spaces = None     # ← ADD THIS LINE
                    st.session_state.conservative_spaces = None  # ← ADD THIS LINE
                    st.session_state.current_layout_type = None  # ← ADD THIS LINE
                    st.session_state.parking_spaces_3d = None    # ← ADD THIS LINE
                    add_app_log(f"User cleared parking layout and results", "INFO")
                    st.rerun()
    else:
        st.info("👈 Draw a polygon on the map to calculate parking capacity")
        st.markdown("""
        **Instructions:**
        1. Use the drawing tools on the left side of the map
        2. Click the polygon or rectangle tool
        3. Draw your parking area
        4. Results will appear here automatically
        """)

st.markdown("---")

st.markdown("""
### About This Tool
This estimator calculates parking capacity based on:
- **Space dimensions** - Configurable per parking type
- **Aisle width** - Required driving lanes between rows
- **Layout optimization** - Optimized vs conservative industry standards

**Standard Parking Dimensions:**
- Standard: 2.5m × 5.0m (8.2' × 16.4')
- Compact: 2.3m × 4.5m (7.5' × 14.8')
- Accessible: 3.7m × 5.5m (12' × 16.4')

**Conservative Layout Standards (ULI/ITE):**
- Space: 2.7m × 5.8m (9' × 19')
- Aisle: 7.9m (26') for two-way traffic
- Perimeter buffer: 3.0m (10') for landscaping
""")