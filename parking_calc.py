import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon
import math
import numpy as np
import pydeck as pdk
import pandas as pd

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

# Set up logging
import logging
from datetime import datetime

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
        import requests
        import urllib3
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
    # Test both the service endpoint AND an actual tile
    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # First test the service metadata
        service_url = "https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer?f=json"
        logging.info(f"Testing NAIP service endpoint: {service_url}")
        add_app_log(f"Testing NAIP service endpoint", "INFO")
        
        response = requests.get(service_url, verify=False, timeout=5)
        
        if response.status_code != 200:
            logging.error(f"NAIP service FAILED - Status: {response.status_code}")
            add_app_log(f"NAIP service FAILED - Status: {response.status_code}", "ERROR")
            return False
        
        # Now test an actual tile to verify imagery is available
        # Test a tile over continental US (zoom 10, somewhere in middle of country)
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
    # Convert from meters to feet
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

# Basemap selection - include NAIP if available
basemap_options = [
    "Esri World Imagery",
    "Google Satellite",
    "Esri Clarity (High-Res)",
]

if st.session_state.naip_available:
    basemap_options.insert(3, "USDA NAIP (via Esri)")
else:
    st.sidebar.warning("⚠️ USDA NAIP imagery currently unavailable (possibly due to gov shutdown)")

basemap = st.sidebar.selectbox(
    "Basemap Layer",
    basemap_options
)

# Add refresh button for NAIP status
if not st.session_state.naip_available:
    if st.sidebar.button("🔄 Test NAIP Connection"):
        with st.spinner("Testing NAIP endpoint..."):
            st.session_state.naip_available = test_naip_availability()
            if st.session_state.naip_available:
                st.sidebar.success("✓ NAIP is now available!")
                st.rerun()
            else:
                st.sidebar.error("✗ NAIP still unavailable")

# Add button to test all basemap connections
if st.sidebar.button("🔄 Test All Basemaps"):
    with st.spinner("Testing all endpoints..."):
        st.session_state.basemap_status = test_all_basemaps()
        st.session_state.naip_available = test_naip_availability()
        
        # Show status summary
        all_working = all(st.session_state.basemap_status.values())
        if all_working and st.session_state.naip_available:
            st.sidebar.success("✓ All basemaps available!")
        else:
            failed = [name for name, status in st.session_state.basemap_status.items() if not status]
            if not st.session_state.naip_available:
                failed.append("NAIP")
            st.sidebar.warning(f"⚠️ Issues with: {', '.join(failed)}")

# Show basemap status if any are failing
if 'basemap_status' in st.session_state:
    failed_basemaps = [name for name, status in st.session_state.basemap_status.items() if not status]
    if failed_basemaps:
        st.sidebar.warning(f"⚠️ Currently unavailable: {', '.join(failed_basemaps)}")

basemap_options.append("OpenStreetMap")

# Basemap information
basemap_info = {
    "Esri World Imagery": "**Update Frequency:** Quarterly to annually\n\n**Resolution:** 30cm-1m in urban areas, varies globally\n\n**Coverage:** Global\n\n**Notes:** Composite from multiple sources including DigitalGlobe, GeoEye, and others. Urban areas typically more recent.",
    "Google Satellite": "**Update Frequency:** Monthly to annually\n\n**Resolution:** 15cm-1m depending on location\n\n**Coverage:** Global\n\n**Notes:** More frequent updates in populated areas. Check Google Earth for specific imagery dates.",
    "Esri Clarity (High-Res)": "**Update Frequency:** Annually\n\n**Resolution:** 30-50cm\n\n**Coverage:** Global population centers\n\n**Coverage:** Global\n\n**Notes:** Vivid natural color imagery with excellent clarity for urban planning.",
    "USDA NAIP (via Esri)": "**Update Frequency:** Every 2-3 years per state\n\n**Resolution:** 60cm-1m\n\n**Coverage:** Continental US only\n\n**Notes:** High-quality USDA aerial imagery served through Esri's reliable infrastructure.",
    "OpenStreetMap": "**Update Frequency:** Real-time (map data)\n\n**Resolution:** Vector data\n\n**Coverage:** Global\n\n**Notes:** Community-maintained street map. Not satellite imagery but useful for reference."
}

st.sidebar.info(basemap_info[basemap])

parking_type = st.sidebar.selectbox(
    "Parking Type",
    ["Standard Perpendicular (90°)", "Angled (45°)", "Parallel", "Compact"]
)

# Add layout orientation selector
layout_orientation = st.sidebar.selectbox(
    "Layout Orientation",
    ["Auto (Optimize)", "Row-Based (Horizontal)", "Column-Based (Vertical)", "Mixed (Both)"],
    help="Choose how parking spaces are arranged"
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
        # Convert floor height based on unit system
        if unit_system == "Imperial":
            floor_height_display = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=8.0,
                max_value=16.0,
                value=11.5,
                step=0.5,
                help="Height between floors"
            )
            floor_height = floor_height_display / length_conversion  # Convert to meters
        else:
            floor_height = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=2.5,
                max_value=5.0,
                value=3.5,
                step=0.5,
                help="Height between floors"
            )
        ground_level = 0  # At grade
    else:  # Underground
        num_levels = st.sidebar.number_input(
            "Number of Underground Levels",
            min_value=1,
            max_value=5,
            value=2,
            help="Number of underground parking levels"
        )
        # Convert floor height based on unit system
        if unit_system == "Imperial":
            floor_height_display = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=8.0,
                max_value=13.0,
                value=10.0,
                step=0.5,
                help="Height between underground floors"
            )
            floor_height = floor_height_display / length_conversion  # Convert to meters
        else:
            floor_height = st.sidebar.number_input(
                f"Floor Height ({length_unit})",
                min_value=2.5,
                max_value=4.0,
                value=3.0,
                step=0.5,
                help="Height between underground floors"
            )
        ground_level = 0  # Underground starts below grade
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
        # Parking space dimensions
        if parking_type == "Standard Perpendicular (90°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=16.4, min_value=14.8, max_value=19.7, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=19.7, min_value=16.4, max_value=26.2, step=1.0)
                # Convert to meters for calculations
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
        
        # User-adjustable efficiency factor
        efficiency = st.slider(
            "Efficiency Factor",
            min_value=0.50,
            max_value=0.95,
            value=default_efficiency,
            step=0.05,
            help="Accounts for circulation, landscaping, and access. Adjust based on site constraints."
        )
        
        st.info(f"**Efficiency Factor:** {efficiency*100}%\n\n⚠️ **Note:** Efficiency factors are practical estimates, not official standards.\n\nThis accounts for:\n- Driving aisles\n- Access routes\n- Landscape areas\n- Pedestrian walkways")

    else:  # Area per Space method
        if parking_type == "Standard Perpendicular (90°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=16.4, min_value=14.8, max_value=19.7, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=19.7, min_value=16.4, max_value=26.2, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 350  # sq ft
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
                default_area_per_space = 32.5  # ~350 sq ft in m²
        elif parking_type == "Angled (45°)":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=11.5, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=18.0, min_value=16.4, max_value=21.3, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=13.1, min_value=11.5, max_value=19.7, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 400  # sq ft
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
                default_area_per_space = 37.2  # ~400 sq ft in m²
        elif parking_type == "Parallel":
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=8.2, min_value=6.5, max_value=9.8, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=21.3, min_value=19.7, max_value=26.2, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=11.5, min_value=9.8, max_value=16.4, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 500  # sq ft
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
                default_area_per_space = 46.5  # ~500 sq ft in m²
        else:  # Compact
            if unit_system == "Imperial":
                space_width_display = st.number_input(f"Space Width ({length_unit})", value=7.5, min_value=6.5, max_value=9.2, step=0.5)
                space_length_display = st.number_input(f"Space Length ({length_unit})", value=14.8, min_value=13.1, max_value=18.0, step=0.5)
                aisle_width_display = st.number_input(f"Aisle Width ({length_unit})", value=18.0, min_value=16.4, max_value=23.0, step=1.0)
                space_width = space_width_display / length_conversion
                space_length = space_length_display / length_conversion
                aisle_width = aisle_width_display / length_conversion
                default_area_per_space = 300  # sq ft
            else:
                space_width = st.number_input(f"Space Width ({length_unit})", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
                space_length = st.number_input(f"Space Length ({length_unit})", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
                aisle_width = st.number_input(f"Aisle Width ({length_unit})", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
                default_area_per_space = 27.9  # ~300 sq ft in m²
        
        # User-adjustable area per space (with unit conversion)
        if unit_system == "Imperial":
            area_per_space_display = st.number_input(
                f"Area per Space ({area_unit})",
                min_value=200.0,
                max_value=650.0,
                value=float(default_area_per_space),
                step=10.0,
                help="Total area including space + share of aisle. Based on ITE standards."
            )
            area_per_space = area_per_space_display / area_conversion  # Convert to m²
        else:
            area_per_space = st.number_input(
                f"Area per Space ({area_unit})",
                min_value=20.0,
                max_value=60.0,
                value=default_area_per_space,
                step=1.0,
                help="Total area including space + share of aisle. Based on ITE standards."
            )
        
        # Calculate implied efficiency for internal use
        space_area = space_width * space_length
        efficiency = space_area / area_per_space if area_per_space > 0 else 0.85
        
st.sidebar.markdown("---")

# Add reference section
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
    st.write("")  # Spacer
    search_button = st.button("Search", type="primary")

if search_button and address:
    try:
        import requests
        import urllib.parse
        import logging
        
        # Use requests directly with verify=False for corporate networks
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
        
        # Suppress SSL warnings
        import urllib3
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
    
    # Show 3D view if enabled and structure type is 3D
    if view_mode == "3D Structure View" and structure_type != "Surface Lot (2D)" and st.session_state.get('show_layout'):
        st.markdown("### 🏗️ 3D Structure Visualization")
        
        # Generate 3D parking data
        if st.session_state.get('layout_params') and st.session_state.get('actual_spaces_drawn'):
            params = st.session_state.layout_params
            polygon_coords = params['polygon']
            
            # Add viewing options
            col_3d1, col_3d2 = st.columns([2, 1])
            with col_3d1:
                view_style = st.selectbox(
                    "3D View Style",
                    ["Stacked (Compact)", "Exploded (All Levels)", "Exploded (Focus Mode)"],
                    help="Focus mode shows one level clearly with others transparent"
                )
            
            # Add level selector for focus mode
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
                    # Extract level number
                    if "B" in focused_level:
                        focused_level_num = int(focused_level.replace("B", "")) - 1
                    else:
                        focused_level_num = int(focused_level.replace("Level ", "")) - 1
            else:
                focused_level_num = None
            
            # Get parking spaces from session state
            if 'parking_spaces_3d' in st.session_state:
                all_spaces_3d = []
                
                # Calculate center for labels
                lats = [coord[1] for coord in polygon_coords]
                lons = [coord[0] for coord in polygon_coords]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                
                # Calculate bounds for exploded view offset
                lat_range = max(lats) - min(lats)
                lon_range = max(lons) - min(lons)
                max_range = max(lat_range, lon_range)
                
                for level in range(num_levels):
                    # Calculate elevation for this level
                    if structure_type == "Underground Parking (3D)":
                        elevation = -floor_height * (level + 1)  # Negative for underground
                        level_name = f"B{level + 1}"
                    else:
                        elevation = floor_height * level
                        level_name = f"Level {level + 1}"
                    
                    # Color gradient for levels - MORE VIBRANT
                    if structure_type == "Underground Parking (3D)":
                        # Distinct vibrant colors for underground levels
                        underground_colors = [
                            [0, 150, 255, 230],      # Bright electric blue - B1
                            [0, 200, 255, 230],      # Cyan blue - B2
                            [100, 220, 255, 230],    # Light cyan - B3
                            [150, 240, 255, 230],    # Very light cyan - B4
                            [200, 250, 255, 230],    # Pale cyan - B5
                        ]
                        base_color = underground_colors[min(level, 4)]
                    else:
                        # Distinct VIBRANT colors for above-ground levels
                        aboveground_colors = [
                            [0, 200, 0, 230],        # Vibrant green - Level 1
                            [255, 230, 0, 230],      # Bright yellow - Level 2
                            [255, 165, 0, 230],      # Bright orange - Level 3
                            [255, 50, 50, 230],      # Bright red - Level 4
                            [200, 0, 255, 230],      # Bright purple - Level 5
                            [255, 20, 147, 230],     # Vibrant pink - Level 6
                            [0, 255, 255, 230],      # Bright cyan - Level 7
                            [255, 100, 0, 230],      # Bright red-orange - Level 8
                            [220, 100, 255, 230],    # Bright orchid - Level 9
                            [50, 255, 150, 230],     # Bright mint green - Level 10
                        ]
                        base_color = aboveground_colors[min(level, 9)]
                    
                    # Apply transparency for focus mode
                    if view_style == "Exploded (Focus Mode)" and focused_level_num is not None:
                        if level == focused_level_num:
                            # Focused level - full opacity
                            color = base_color
                        else:
                            # Other levels - make transparent
                            color = [base_color[0], base_color[1], base_color[2], 40]
                    else:
                        color = base_color
                    
                    # Calculate horizontal offset for exploded view
                    if view_style in ["Exploded (All Levels)", "Exploded (Focus Mode)"]:
                        # Offset each level horizontally for better picking
                        offset_multiplier = 1.5
                        horizontal_offset_lon = (level - num_levels/2) * max_range * offset_multiplier
                        horizontal_offset_lat = 0
                    else:
                        horizontal_offset_lon = 0
                        horizontal_offset_lat = 0
                    
                    # Add each parking space at this level
                    for idx, space in enumerate(st.session_state.parking_spaces_3d):
                        # Apply horizontal offset to polygon coordinates
                        offset_coords = [
                            (coord[0] + horizontal_offset_lon, coord[1] + horizontal_offset_lat) 
                            for coord in space['coords']
                        ]
                        
                        space_3d = {
                            'polygon': offset_coords,
                            'elevation': elevation,
                            'height': 2.5,  # Car height
                            'color': color,
                            'level': level_name,
                            'space_id': f"{level_name}-{idx+1}",
                            'level_number': level + 1
                        }
                        all_spaces_3d.append(space_3d)
                
                # Create pydeck layers
                layers = []
                
                # Parking spaces layer with vibrant colors
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
                
                # Calculate view state
                if view_style in ["Exploded (All Levels)", "Exploded (Focus Mode)"]:
                    # Zoom out to see all levels
                    zoom_level = 17
                else:
                    zoom_level = 18
                
                # Set view state
                view_state = pdk.ViewState(
                    latitude=center_lat,
                    longitude=center_lon,
                    zoom=zoom_level,
                    pitch=45,
                    bearing=0,
                )
                
                # Create deck
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
                
                # Add legend showing level colors
                st.markdown("### Level Legend")
                legend_cols = st.columns(min(num_levels, 5))
                
                for level in range(num_levels):
                    if structure_type == "Underground Parking (3D)":
                        level_name = f"B{level + 1}"
                        underground_colors = [
                            [0, 150, 255],      # Bright electric blue
                            [0, 200, 255],      # Cyan blue
                            [100, 220, 255],    # Light cyan
                            [150, 240, 255],    # Very light cyan
                            [200, 250, 255],    # Pale cyan
                        ]
                        color = underground_colors[min(level, 4)]
                    else:
                        level_name = f"Level {level + 1}"
                        aboveground_colors = [
                            [0, 200, 0],        # Vibrant green
                            [255, 230, 0],      # Bright yellow
                            [255, 165, 0],      # Bright orange
                            [255, 50, 50],      # Bright red
                            [200, 0, 255],      # Bright purple
                            [255, 20, 147],     # Vibrant pink
                            [0, 255, 255],      # Bright cyan
                            [255, 100, 0],      # Bright red-orange
                            [220, 100, 255],    # Bright orchid
                            [50, 255, 150],     # Bright mint green
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
                
                # Add 3D stats
                total_spaces_all_levels = st.session_state.actual_spaces_drawn * num_levels
                st.success(f"🏢 Total Spaces Across {num_levels} Level(s): **{total_spaces_all_levels:,}**")
            else:
                st.warning("Generate parking layout first to see 3D visualization")
        else:
            st.info("Draw a polygon and generate parking layout to see 3D structure")
    else:
        # Show regular 2D map view
        st.markdown("### 🗺️ 2D Map View" if structure_type != "Surface Lot (2D)" else "")
    
    # Define basemap tiles based on selection
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
    
    # Log basemap loading attempt
    logging.info(f"Loading basemap: {basemap}")
    add_app_log(f"Loading basemap: {basemap}", "INFO")
    
    # Determine map center and zoom
    # If polygon exists and layout is being shown, use polygon center
    if st.session_state.get('polygon_center') and st.session_state.get('show_layout'):
        map_center = st.session_state.polygon_center
        map_zoom = st.session_state.polygon_zoom
        add_app_log(f"Using polygon center for map view", "INFO")
    # If polygon exists but no layout, still use polygon center
    elif st.session_state.get('polygon_center'):
        map_center = st.session_state.polygon_center
        map_zoom = st.session_state.polygon_zoom
    # Otherwise use default or search location
    else:
        map_center = st.session_state.map_center
        map_zoom = st.session_state.map_zoom
    
    # Create base map with current center and zoom
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
        # Fallback to OpenStreetMap
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
    
    # Add drawing controls
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
        
        # Generate parking space rectangles
        from shapely.geometry import box, Point
        from shapely.affinity import rotate, translate
        
        polygon_coords = params['polygon']
        space_w = params['space_width']
        space_l = params['space_length']
        aisle_w = params['aisle_width']
        p_type = params['parking_type']
        
        # Convert polygon to Shapely polygon (in lat/lon)
        poly_latlon = Polygon([(lon, lat) for lon, lat in polygon_coords])
        bounds = poly_latlon.bounds  # (minx, miny, maxx, maxy)
        
        # Calculate approximate meters per degree at this latitude
        center_lat = (bounds[1] + bounds[3]) / 2
        lon_to_m = 111320 * np.cos(np.radians(center_lat))
        lat_to_m = 110540
        
        # Generate parking spaces
        # Generate parking spaces with orientation support
        parking_spaces = []

        # Analyze polygon dimensions to determine best orientation
        poly_width = bounds[2] - bounds[0]  # longitude range
        poly_height = bounds[3] - bounds[1]  # latitude range
        aspect_ratio = poly_width / poly_height if poly_height > 0 else 1

        # Determine which orientations to use
        if layout_orientation == "Auto (Optimize)":
            # Choose based on aspect ratio
            if aspect_ratio > 1.3:  # Wide polygon
                use_rows = True
                use_columns = False
            elif aspect_ratio < 0.7:  # Tall polygon
                use_rows = False
                use_columns = True
            else:  # Square-ish polygon
                use_rows = True
                use_columns = True
        elif layout_orientation == "Row-Based (Horizontal)":
            use_rows = True
            use_columns = False
        elif layout_orientation == "Column-Based (Vertical)":
            use_rows = False
            use_columns = True
        else:  # Mixed
            use_rows = True
            use_columns = True

        def create_space_coords(x, y, width_deg, length_deg, orientation='horizontal', direction=1, angle_rad=0):
            """
            Create parking space coordinates
            orientation: 'horizontal' for row-based, 'vertical' for column-based
            direction: 1 or -1 for alternating sides
            angle_rad: for angled parking
            """
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

        if "Perpendicular" in p_type or "Compact" in p_type:
            # ROW-BASED LAYOUT (Horizontal rows)
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
            
            # COLUMN-BASED LAYOUT (Vertical columns)
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
            
            # ROW-BASED ANGLED
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
            
            # COLUMN-BASED ANGLED
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
            # Parallel parking remains perimeter-based (unchanged)
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
            
            # Left and right edges
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
        
        # Store actual number of spaces drawn
        st.session_state.actual_spaces_drawn = len(parking_spaces)
        
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
    
    # Process drawn polygon first to update calculations
    if map_data and map_data.get('all_drawings'):
        drawings = map_data['all_drawings']
        
        if len(drawings) > 0:
            last_drawing = drawings[-1]
            
            if last_drawing['geometry']['type'] in ['Polygon', 'Rectangle']:
                coords = last_drawing['geometry']['coordinates'][0]
                st.session_state.polygon_coords = coords
                
                # Capture the center point of the polygon for zoom persistence
                lats = [coord[1] for coord in coords]
                lons = [coord[0] for coord in coords]
                center_lat = sum(lats) / len(lats)
                center_lon = sum(lons) / len(lons)
                st.session_state.polygon_center = [center_lat, center_lon]
                st.session_state.polygon_zoom = 19  # Zoom in closer when polygon is drawn
                
                add_app_log(f"Captured polygon center: [{center_lat:.6f}, {center_lon:.6f}]", "INFO")
                
                # Calculate area using Shapely
                lat_to_m = 111000
                lon_to_m = 82000
                
                add_app_log(f"Polygon drawn with {len(coords)} vertices", "INFO")
                
                coords_m = [(lon * lon_to_m, lat * lat_to_m) for lon, lat in coords]
                poly = Polygon(coords_m)
                area_m2 = poly.area
                
                add_app_log(f"Calculated area: {area_m2:,.1f} m²", "INFO")
                
                # Calculate parking spaces
                space_area = space_width * space_length
                
                # Calculate based on method
                if calculation_method == "Area per Space (ITE Standard)":
                    estimated_spaces_per_level = int(area_m2 / area_per_space)
                    calc_method_stored = "Area per Space (ITE Standard)"
                    area_per_space_stored = area_per_space
                else:
                    estimated_spaces_per_level = int((area_m2 * efficiency) / space_area)
                    calc_method_stored = "Efficiency Factor"
                    area_per_space_stored = None
                
                # Multiply by number of levels for structures
                estimated_spaces = estimated_spaces_per_level * num_levels
                
                add_app_log(f"Estimated parking spaces: {estimated_spaces} ({estimated_spaces_per_level}/level × {num_levels} levels) (Method: {calc_method_stored})", "INFO")
                
                # Store calculation results
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
    
    # Always display results if they exist in session state
    if st.session_state.calculation_results:
        results = st.session_state.calculation_results
        
        # Show structure type if multi-level
        if results.get('structure_type') != "Surface Lot (2D)":
            st.info(f"🏢 **{results.get('structure_type')}**\n\n{results.get('num_levels', 1)} Level(s)")
        
        # Display area in selected unit system
        if unit_system == "Imperial":
            st.metric("Total Area (per level)", f"{results['area_m2'] * area_conversion:,.1f} {area_unit}")
        else:
            st.metric("Total Area (per level)", f"{results['area_m2']:,.1f} {area_unit}")
            st.metric("Total Area (per level)", f"{results['area_m2'] * 10.764:,.1f} ft²")
        
        # Show per-level and total estimates
        if results.get('num_levels', 1) > 1:
            st.metric("Estimated Spaces (per level)", f"{results.get('estimated_spaces_per_level', 0):,}")
            st.metric("Estimated Total Spaces", f"{results['estimated_spaces']:,}", 
                     help=f"{results.get('estimated_spaces_per_level', 0)} spaces × {results.get('num_levels', 1)} levels")
        else:
            st.metric("Estimated Parking Spaces", f"{results['estimated_spaces']:,}")
        
        # Show actual drawn spaces if layout is displayed
        if st.session_state.get('show_layout') and st.session_state.get('actual_spaces_drawn'):
            actual_per_level = st.session_state.actual_spaces_drawn
            actual_total = actual_per_level * results.get('num_levels', 1)
            
            if results.get('num_levels', 1) > 1:
                st.metric("Actual Spaces (per level)", f"{actual_per_level:,}")
                st.metric("Actual Total Spaces", f"{actual_total:,}",
                         delta=f"{actual_total - results['estimated_spaces']} vs estimate")
            else:
                st.metric("Actual Parking Spaces", f"{actual_per_level:,}", 
                         delta=f"{actual_per_level - results['estimated_spaces']} vs estimate")
        
        st.markdown("---")
        st.markdown("**Breakdown:**")
        
        # Display dimensions in selected unit system
        if unit_system == "Imperial":
            st.write(f"• Space size: {results['space_width'] * length_conversion:.1f}{length_unit} × {results['space_length'] * length_conversion:.1f}{length_unit}")
            st.write(f"• Space area: {results['space_area'] * area_conversion:.1f} {area_unit}")
            st.write(f"• Aisle width: {results['aisle_width'] * length_conversion:.1f}{length_unit}")
        else:
            st.write(f"• Space size: {results['space_width']:.1f}{length_unit} × {results['space_length']:.1f}{length_unit}")
            st.write(f"• Space area: {results['space_area']:.1f} {area_unit}")
            st.write(f"• Aisle width: {results['aisle_width']:.1f}{length_unit}")
        
        if 'calculation_method' in results and results['calculation_method'] == "Area per Space (ITE Standard)":
            if unit_system == "Imperial":
                st.write(f"• Area per space: {results.get('area_per_space', 0) * area_conversion:.1f} {area_unit}")
            else:
                st.write(f"• Area per space: {results.get('area_per_space', 'N/A'):.1f} {area_unit} ({results.get('area_per_space', 0) * 10.764:.1f} sf)")
            st.write(f"• Method: ITE Standard")
        else:
            st.write(f"• Efficiency: {results['efficiency']*100}%")
            st.write(f"• Method: Efficiency Factor")
        
        # Calculate density based on unit system
        if unit_system == "Imperial":
            spaces_per_unit = results['estimated_spaces'] / (results['area_m2'] * area_conversion) * 1000  # per 1000 sf
            st.markdown(f"**Density:** {spaces_per_unit:.2f} spaces per 1000{area_unit}")
        else:
            spaces_per_sqm = results['estimated_spaces'] / results['area_m2']
            st.markdown(f"**Density:** {spaces_per_sqm*100:.2f} spaces per 100{area_unit}")
        
        st.markdown("---")
        
        # Button to generate/toggle parking layout
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚗 Generate Layout", key="generate_layout_btn", type="primary"):
                if st.session_state.polygon_coords:
                    st.session_state.show_layout = True
                    st.session_state.layout_params = {
                        'polygon': st.session_state.polygon_coords,
                        'space_width': space_width,
                        'space_length': space_length,
                        'aisle_width': aisle_width,
                        'parking_type': parking_type,
                        'estimated_spaces': results['estimated_spaces']
                    }
                    add_app_log(f"User requested parking layout generation", "INFO")
                    st.rerun()
        
        with col_btn2:
            if st.session_state.get('show_layout', False):
                if st.button("🗑️ Clear Layout", key="clear_layout_btn"):
                    st.session_state.show_layout = False
                    st.session_state.actual_spaces_drawn = None
                    st.session_state.layout_params = None
                    add_app_log(f"User cleared parking layout", "INFO")
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

# Additional info
st.markdown(f"""
### About This Tool
This estimator calculates parking capacity based on:
- **Space dimensions** - Configurable per parking type
- **Aisle width** - Required driving lanes between rows
- **Efficiency factor** - Accounts for circulation, landscaping, and access

**Standard Parking Dimensions:**
- Standard: 2.5m × 5.0m (8.2' × 16.4')
- Compact: 2.3m × 4.5m (7.5' × 14.8')
- Accessible: 3.7m × 5.0m (12' × 16.4')
""")