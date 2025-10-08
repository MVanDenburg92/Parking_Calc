import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon
import math
import numpy as np

st.set_page_config(page_title="Parking Space Estimator", layout="wide", initial_sidebar_state="expanded")

# Custom CSS to make sidebar wider
st.markdown("""
    <style>
        section[data-testid="stSidebar"] {
            width: 400px !important;
        }
        section[data-testid="stSidebar"] > div {
            width: 400px !important;
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
    test_url = "https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer?f=json"
    return test_endpoint_availability("NAIP", test_url)

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

# Calculation method toggle
calculation_method = st.sidebar.radio(
    "Calculation Method",
    ["Efficiency Factor", "Area per Space (ITE Standard)"],
    help="Choose between efficiency factor method or industry-standard area per space"
)

st.sidebar.markdown("---")

if calculation_method == "Efficiency Factor":
    # Parking space dimensions (in meters)
    if parking_type == "Standard Perpendicular (90°)":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
        default_efficiency = 0.85
    elif parking_type == "Angled (45°)":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
        default_efficiency = 0.80
    elif parking_type == "Parallel":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
        default_efficiency = 0.65
    else:  # Compact
        space_width = st.sidebar.number_input("Space Width (m)", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
        default_efficiency = 0.87
    
    # User-adjustable efficiency factor
    efficiency = st.sidebar.slider(
        "Efficiency Factor",
        min_value=0.50,
        max_value=0.95,
        value=default_efficiency,
        step=0.05,
        help="Accounts for circulation, landscaping, and access. Adjust based on site constraints."
    )
    
    st.sidebar.info(f"**Efficiency Factor:** {efficiency*100}%\n\n⚠️ **Note:** Efficiency factors are practical estimates, not official standards.\n\nThis accounts for:\n- Driving aisles\n- Access routes\n- Landscape areas\n- Pedestrian walkways")

else:  # Area per Space method
    if parking_type == "Standard Perpendicular (90°)":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
        default_area_per_space = 32.5  # ~350 sq ft
    elif parking_type == "Angled (45°)":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
        default_area_per_space = 37.2  # ~400 sq ft
    elif parking_type == "Parallel":
        space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
        default_area_per_space = 46.5  # ~500 sq ft
    else:  # Compact
        space_width = st.sidebar.number_input("Space Width (m)", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
        space_length = st.sidebar.number_input("Space Length (m)", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
        aisle_width = st.sidebar.number_input("Aisle Width (m)", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
        default_area_per_space = 27.9  # ~300 sq ft
    
    # User-adjustable area per space
    area_per_space = st.sidebar.number_input(
        "Area per Space (m²)",
        min_value=20.0,
        max_value=60.0,
        value=default_area_per_space,
        step=1.0,
        help="Total area including space + share of aisle. Based on ITE standards."
    )
    
    # Calculate implied efficiency for internal use
    space_area = space_width * space_length
    efficiency = space_area / area_per_space if area_per_space > 0 else 0.85
    
    st.sidebar.info(f"**ITE Standard Method**\n\n📚 Based on Institute of Transportation Engineers (ITE) *Parking Generation* guidelines.\n\n**Typical ranges:**\n- 90° parking: 28-37 m² (300-400 sf)\n- Angled: 33-42 m² (350-450 sf)\n- Parallel: 42-56 m² (450-600 sf)\n\nIncludes space + circulation.")

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
    - Standard: 2.4-2.7m × 4.9-5.5m
    - Compact: 2.3-2.4m × 4.3-4.9m
    - Accessible: 3.7m × 5.5m (min)
    
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

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Draw Your Parking Area")
    
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
        parking_spaces = []
        
        if "Perpendicular" in p_type:
            # Generate perpendicular parking layout
            # Start from bottom left, create rows going up
            current_y = bounds[1]
            row_num = 0
            
            while current_y < bounds[3]:
                # Create a row of spaces
                current_x = bounds[0]
                
                # Alternate sides for double-loaded aisles
                if row_num % 2 == 0:
                    space_direction = 1  # Spaces on bottom of aisle
                else:
                    space_direction = -1  # Spaces on top of aisle
                
                while current_x < bounds[2]:
                    # Create individual parking space
                    space_w_deg = space_w / lon_to_m
                    space_l_deg = space_l / lat_to_m
                    
                    if space_direction == 1:
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg, current_y + space_l_deg),
                            (current_x, current_y + space_l_deg),
                            (current_x, current_y)
                        ]
                    else:
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg, current_y - space_l_deg),
                            (current_x, current_y - space_l_deg),
                            (current_x, current_y)
                        ]
                    
                    # Check if space is within the drawn polygon
                    space_poly = Polygon(space_coords)
                    if poly_latlon.contains(space_poly.centroid):
                        display_coords = [[(lon, lat) for lon, lat in space_coords]]
                        parking_spaces.append(display_coords)
                    
                    current_x += space_w_deg
                
                # Move to next row (including aisle)
                aisle_w_deg = aisle_w / lat_to_m
                if space_direction == 1:
                    current_y += space_l_deg + aisle_w_deg
                else:
                    current_y += aisle_w_deg
                row_num += 1
                
        elif "Angled" in p_type:
            # Generate 45-degree angled parking layout
            current_y = bounds[1]
            row_num = 0
            angle_rad = np.radians(45)
            
            while current_y < bounds[3]:
                current_x = bounds[0]
                
                # Alternate direction for double-loaded aisles
                if row_num % 2 == 0:
                    angle_direction = 1  # Right-leaning
                else:
                    angle_direction = -1  # Left-leaning
                
                while current_x < bounds[2]:
                    space_w_deg = space_w / lon_to_m
                    space_l_deg = space_l / lat_to_m
                    
                    # Create angled rectangle
                    if angle_direction == 1:
                        # 45-degree angle, spaces lean right
                        offset = space_l_deg * np.sin(angle_rad)
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg + offset, current_y + space_l_deg * np.cos(angle_rad)),
                            (current_x + offset, current_y + space_l_deg * np.cos(angle_rad)),
                            (current_x, current_y)
                        ]
                    else:
                        # Spaces lean left
                        offset = space_l_deg * np.sin(angle_rad)
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg - offset, current_y - space_l_deg * np.cos(angle_rad)),
                            (current_x - offset, current_y - space_l_deg * np.cos(angle_rad)),
                            (current_x, current_y)
                        ]
                    
                    space_poly = Polygon(space_coords)
                    if poly_latlon.contains(space_poly.centroid):
                        display_coords = [[(lon, lat) for lon, lat in space_coords]]
                        parking_spaces.append(display_coords)
                    
                    current_x += space_w_deg
                
                # Move to next row
                aisle_w_deg = aisle_w / lat_to_m
                if angle_direction == 1:
                    current_y += (space_l_deg * np.cos(angle_rad)) + aisle_w_deg
                else:
                    current_y += aisle_w_deg
                row_num += 1
                
        elif "Parallel" in p_type:
            # Generate parallel parking layout (along the perimeter)
            # For parallel, spaces go along the length
            current_x = bounds[0]
            
            while current_x < bounds[2]:
                space_w_deg = space_w / lon_to_m
                space_l_deg = space_l / lat_to_m
                
                # Bottom edge - spaces facing up
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
                
                # Top edge - spaces facing down
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
                
                # Left edge - spaces facing right
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
                
                # Right edge - spaces facing left
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
                
        elif "Compact" in p_type:
            # Compact uses same perpendicular layout, just smaller spaces
            current_y = bounds[1]
            row_num = 0
            
            while current_y < bounds[3]:
                current_x = bounds[0]
                
                if row_num % 2 == 0:
                    space_direction = 1
                else:
                    space_direction = -1
                
                while current_x < bounds[2]:
                    space_w_deg = space_w / lon_to_m
                    space_l_deg = space_l / lat_to_m
                    
                    if space_direction == 1:
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg, current_y + space_l_deg),
                            (current_x, current_y + space_l_deg),
                            (current_x, current_y)
                        ]
                    else:
                        space_coords = [
                            (current_x, current_y),
                            (current_x + space_w_deg, current_y),
                            (current_x + space_w_deg, current_y - space_l_deg),
                            (current_x, current_y - space_l_deg),
                            (current_x, current_y)
                        ]
                    
                    space_poly = Polygon(space_coords)
                    if poly_latlon.contains(space_poly.centroid):
                        display_coords = [[(lon, lat) for lon, lat in space_coords]]
                        parking_spaces.append(display_coords)
                    
                    current_x += space_w_deg
                
                aisle_w_deg = aisle_w / lat_to_m
                if space_direction == 1:
                    current_y += space_l_deg + aisle_w_deg
                else:
                    current_y += aisle_w_deg
                row_num += 1
        
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
                    estimated_spaces = int(area_m2 / area_per_space)
                    calc_method_stored = "Area per Space (ITE Standard)"
                    area_per_space_stored = area_per_space
                else:
                    estimated_spaces = int((area_m2 * efficiency) / space_area)
                    calc_method_stored = "Efficiency Factor"
                    area_per_space_stored = None
                
                add_app_log(f"Estimated parking spaces: {estimated_spaces} (Method: {calc_method_stored})", "INFO")
                
                # Store calculation results
                st.session_state.calculation_results = {
                    'area_m2': area_m2,
                    'space_area': space_area,
                    'estimated_spaces': estimated_spaces,
                    'efficiency': efficiency,
                    'space_width': space_width,
                    'space_length': space_length,
                    'aisle_width': aisle_width,
                    'calculation_method': calc_method_stored,
                    'area_per_space': area_per_space_stored
                }
    
    # Always display results if they exist in session state
    if st.session_state.calculation_results:
        results = st.session_state.calculation_results
        
        st.metric("Total Area", f"{results['area_m2']:,.1f} m²")
        st.metric("Total Area", f"{results['area_m2'] * 10.764:,.1f} ft²")
        
        # Always show estimated spaces
        st.metric("Estimated Parking Spaces", f"{results['estimated_spaces']:,}")
        
        # Show actual drawn spaces if layout is displayed
        if st.session_state.get('show_layout') and st.session_state.get('actual_spaces_drawn'):
            st.metric("Actual Parking Spaces", f"{st.session_state.actual_spaces_drawn:,}", 
                     delta=f"{st.session_state.actual_spaces_drawn - results['estimated_spaces']} vs estimate")
        
        st.markdown("---")
        st.markdown("**Breakdown:**")
        st.write(f"• Space size: {results['space_width']}m × {results['space_length']}m")
        st.write(f"• Space area: {results['space_area']:.1f} m²")
        st.write(f"• Aisle width: {results['aisle_width']}m")
        
        if 'calculation_method' in results and results['calculation_method'] == "Area per Space (ITE Standard)":
            st.write(f"• Area per space: {results.get('area_per_space', 'N/A'):.1f} m² ({results.get('area_per_space', 0) * 10.764:.1f} sf)")
            st.write(f"• Method: ITE Standard")
        else:
            st.write(f"• Efficiency: {results['efficiency']*100}%")
            st.write(f"• Method: Efficiency Factor")
        
        spaces_per_sqm = results['estimated_spaces'] / results['area_m2']
        st.markdown(f"**Density:** {spaces_per_sqm*100:.2f} spaces per 100m²")
        
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

# Add expandable log viewer at the bottom
with st.expander("📋 Activity Logs", expanded=False):
    st.markdown("**Real-time application activity:**")
    
    # Display logs in reverse chronological order
    if st.session_state.app_logs:
        log_text = "\n".join(reversed(st.session_state.app_logs[-50:]))  # Show last 50 logs
        st.text_area("Activity Log", value=log_text, height=200, disabled=True, key="log_display")
        
        # Add buttons to manage logs
        col_log1, col_log2 = st.columns(2)
        with col_log1:
            if st.button("🔄 Refresh Logs"):
                st.rerun()
        with col_log2:
            if st.button("🗑️ Clear Logs"):
                st.session_state.app_logs = []
                st.rerun()
    else:
        st.info("No activity logged yet. Start by drawing a polygon or testing endpoints.")

# Additional info
st.markdown("---")
st.markdown("""
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