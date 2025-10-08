import streamlit as st
import folium
from streamlit_folium import st_folium
from shapely.geometry import Polygon
import math

st.set_page_config(page_title="Parking Space Estimator", layout="wide")

st.title("🅿️ Parking Space Estimator")
st.markdown("Draw a polygon on the map to estimate how many parking spaces could fit in the area.")

# Sidebar for parameters
st.sidebar.header("Parking Configuration")

# Basemap selection
basemap = st.sidebar.selectbox(
    "Basemap Layer",
    [
        "Esri World Imagery",
        "Google Satellite",
        "Esri Clarity (High-Res)",
        "USDA NAIP (via Esri)",
        "OpenStreetMap"
    ]
)

# Basemap information
basemap_info = {
    "Esri World Imagery": "**Update Frequency:** Quarterly to annually\n\n**Resolution:** 30cm-1m in urban areas, varies globally\n\n**Coverage:** Global\n\n**Notes:** Composite from multiple sources including DigitalGlobe, GeoEye, and others. Urban areas typically more recent.",
    "Google Satellite": "**Update Frequency:** Monthly to annually\n\n**Resolution:** 15cm-1m depending on location\n\n**Coverage:** Global\n\n**Notes:** More frequent updates in populated areas. Check Google Earth for specific imagery dates.",
    "Esri Clarity (High-Res)": "**Update Frequency:** Annually\n\n**Resolution:** 30-50cm\n\n**Coverage:** Global population centers\n\n**Notes:** Vivid natural color imagery with excellent clarity for urban planning.",
    "USDA NAIP (via Esri)": "**Update Frequency:** Every 2-3 years per state\n\n**Resolution:** 60cm-1m\n\n**Coverage:** Continental US only\n\n**Notes:** High-quality USDA aerial imagery served through Esri's reliable infrastructure.",
    "OpenStreetMap": "**Update Frequency:** Real-time (map data)\n\n**Resolution:** Vector data\n\n**Coverage:** Global\n\n**Notes:** Community-maintained street map. Not satellite imagery but useful for reference."
}

st.sidebar.info(basemap_info[basemap])

parking_type = st.sidebar.selectbox(
    "Parking Type",
    ["Standard Perpendicular (90°)", "Angled (45°)", "Parallel", "Compact"]
)

# Parking space dimensions (in meters)
if parking_type == "Standard Perpendicular (90°)":
    space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
    space_length = st.sidebar.number_input("Space Length (m)", value=5.0, min_value=4.5, max_value=6.0, step=0.1)
    aisle_width = st.sidebar.number_input("Aisle Width (m)", value=6.0, min_value=5.0, max_value=8.0, step=0.5)
    efficiency = 0.85  # 85% efficiency for perpendicular
elif parking_type == "Angled (45°)":
    space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.5, step=0.1)
    space_length = st.sidebar.number_input("Space Length (m)", value=5.5, min_value=5.0, max_value=6.5, step=0.1)
    aisle_width = st.sidebar.number_input("Aisle Width (m)", value=4.0, min_value=3.5, max_value=6.0, step=0.5)
    efficiency = 0.80  # 80% efficiency for angled
elif parking_type == "Parallel":
    space_width = st.sidebar.number_input("Space Width (m)", value=2.5, min_value=2.0, max_value=3.0, step=0.1)
    space_length = st.sidebar.number_input("Space Length (m)", value=6.5, min_value=6.0, max_value=8.0, step=0.1)
    aisle_width = st.sidebar.number_input("Aisle Width (m)", value=3.5, min_value=3.0, max_value=5.0, step=0.5)
    efficiency = 0.65  # 65% efficiency for parallel
else:  # Compact
    space_width = st.sidebar.number_input("Space Width (m)", value=2.3, min_value=2.0, max_value=2.8, step=0.1)
    space_length = st.sidebar.number_input("Space Length (m)", value=4.5, min_value=4.0, max_value=5.5, step=0.1)
    aisle_width = st.sidebar.number_input("Aisle Width (m)", value=5.5, min_value=5.0, max_value=7.0, step=0.5)
    efficiency = 0.87  # 87% efficiency for compact

st.sidebar.markdown("---")
st.sidebar.info(f"**Efficiency Factor:** {efficiency*100}%\n\nThis accounts for:\n- Driving aisles\n- Access routes\n- Landscape areas\n- Pedestrian walkways")

# Initialize session state
if 'polygon_coords' not in st.session_state:
    st.session_state.polygon_coords = None
if 'map_center' not in st.session_state:
    st.session_state.map_center = [41.8781, -87.6298]  # Chicago
if 'map_zoom' not in st.session_state:
    st.session_state.map_zoom = 18

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
        
        # Use requests directly with verify=False for corporate networks
        encoded_address = urllib.parse.quote(address)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded_address}&format=json&limit=1"
        
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
            else:
                st.error("Address not found. Please try a different search term.")
        else:
            st.error(f"Search failed with status code: {response.status_code}")
    except Exception as e:
        st.error(f"Search error: {str(e)}")

st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Draw Your Parking Area")
    
    # Define basemap tiles based on selection
    if basemap == "Esri World Imagery":
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
        attr = 'Esri'
    elif basemap == "Google Satellite":
        tiles = 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}'
        attr = 'Google'
    elif basemap == "Esri Clarity (High-Res)":
        tiles = 'https://clarity.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
        attr = 'Esri Clarity'
    elif basemap == "USDA NAIP (via Esri)":
        # Use Esri's NAIP Plus service which is more reliable
        tiles = 'https://naip.arcgis.com/arcgis/rest/services/NAIP/ImageServer/tile/{z}/{y}/{x}'
        attr = 'USDA NAIP'
    else:  # OpenStreetMap
        tiles = 'OpenStreetMap'
        attr = 'OpenStreetMap'
    
    # Create base map with current center and zoom
    m = folium.Map(
        location=st.session_state.map_center,
        zoom_start=st.session_state.map_zoom,
        tiles=tiles,
        attr=attr
    )
    
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
                
                # Calculate area using Shapely
                # Convert to meters using approximate conversion
                # At ~42°N latitude, 1 degree ≈ 111,000m (lat) and 82,000m (lon)
                lat_to_m = 111000
                lon_to_m = 82000
                
                coords_m = [(lon * lon_to_m, lat * lat_to_m) for lon, lat in coords]
                poly = Polygon(coords_m)
                area_m2 = poly.area
                
                # Calculate parking spaces
                space_area = space_width * space_length
                row_width = space_length + aisle_width
                
                # Estimate spaces with efficiency factor
                estimated_spaces = int((area_m2 * efficiency) / space_area)
                
                # Display results
                st.metric("Total Area", f"{area_m2:,.1f} m²")
                st.metric("Total Area", f"{area_m2 * 10.764:,.1f} ft²")
                st.metric("Estimated Parking Spaces", f"{estimated_spaces:,}")
                
                st.markdown("---")
                st.markdown("**Breakdown:**")
                st.write(f"• Space size: {space_width}m × {space_length}m")
                st.write(f"• Space area: {space_area:.1f} m²")
                st.write(f"• Aisle width: {aisle_width}m")
                st.write(f"• Efficiency: {efficiency*100}%")
                
                spaces_per_sqm = estimated_spaces / area_m2
                st.markdown(f"**Density:** {spaces_per_sqm*100:.2f} spaces per 100m²")
                
    else:
        st.info("👈 Draw a polygon on the map to calculate parking capacity")
        st.markdown("""
        **Instructions:**
        1. Use the drawing tools on the left side of the map
        2. Click the polygon or rectangle tool
        3. Draw your parking area
        4. Results will appear here automatically
        """)

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