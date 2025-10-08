# 🅿️ Parking Space Estimator

A Streamlit web application that allows users to estimate parking capacity for any location by drawing polygons on satellite imagery maps. Check it out here - https://parkingcalc.streamlit.app/

![Parking Space Estimator](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?style=flat-square&logo=streamlit)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python)

## Features

### 🗺️ Interactive Mapping
- **Multiple Basemap Options**: Choose from Esri World Imagery, Google Satellite, Esri Clarity, and OpenStreetMap
- **Draw Tools**: Create polygons or rectangles directly on the map to define parking areas
- **Address Search**: Search for any address worldwide with automatic map centering
- **Real-time Calculations**: Instant parking capacity estimates as you draw

### 🚗 Parking Configuration
- **Multiple Parking Types**:
  - Standard Perpendicular (90°)
  - Angled (45°)
  - Parallel
  - Compact
- **Customizable Dimensions**: Adjust space width, length, and aisle width
- **Efficiency Factors**: Realistic calculations accounting for circulation, landscaping, and access routes

### 🔍 Monitoring & Diagnostics
- **Endpoint Testing**: Automatic testing of all basemap services on startup
- **Error Logging**: Comprehensive logging of all endpoint failures to `parking_estimator_errors.log`
- **Manual Testing**: Test individual or all basemap connections with built-in buttons
- **Automatic Fallback**: Falls back to OpenStreetMap if selected basemap fails

### 📊 Results
- Area calculations in both m² and ft²
- Estimated parking space count
- Parking density metrics
- Detailed breakdown of calculations

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Required Packages

```bash
pip install streamlit folium streamlit-folium shapely requests urllib3
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
```

### requirements.txt
```
streamlit>=1.28.0
folium>=0.14.0
streamlit-folium>=0.15.0
shapely>=2.0.0
requests>=2.31.0
urllib3>=2.0.0
```

## Usage

### Running the Application

1. Clone the repository:
```bash
git clone https://github.com/yourusername/parking-space-estimator.git
cd parking-space-estimator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the Streamlit app:
```bash
streamlit run parking_estimator.py
```

4. Open your browser to `http://localhost:8501`

### Using the Application

1. **Select a Basemap**: Choose your preferred satellite imagery from the sidebar
2. **Search for Location** (optional): Enter an address to jump to a specific location
3. **Configure Parking Type**: Select parking style and adjust dimensions in the sidebar
4. **Draw Your Area**: Use the drawing tools on the map to outline your parking area
5. **View Results**: Parking capacity estimates appear automatically in the right panel

## Configuration

### Parking Space Standards

The app uses industry-standard dimensions:

- **Standard Perpendicular**: 2.5m × 5.0m (8.2' × 16.4')
- **Angled (45°)**: 2.5m × 5.5m with narrower aisles
- **Parallel**: 2.5m × 6.5m (8.2' × 21.3')
- **Compact**: 2.3m × 4.5m (7.5' × 14.8')

All dimensions are customizable through the sidebar controls.

### Efficiency Factors

Built-in efficiency factors account for:
- Driving aisles and circulation
- Access routes and entrances
- Landscape buffers and islands
- Pedestrian walkways
- ADA accessible spaces

## Network Configuration

### Corporate Networks

If you're behind a corporate firewall or proxy:

1. The app disables SSL verification for geocoding requests
2. Endpoint testing uses `verify=False` for corporate network compatibility
3. All external requests include proper timeout handling

### Troubleshooting

If basemaps aren't loading:
1. Check the error log file: `parking_estimator_errors.log`
2. Click "Test All Basemaps" in the sidebar
3. Try switching to a different basemap
4. Ensure your network allows HTTPS connections to tile services

## Error Logging

All endpoint failures are logged to `parking_estimator_errors.log` with:
- Timestamp
- Endpoint name and URL
- Error type (timeout, connection error, HTTP status)
- Detailed error messages

Example log entries:
```
2025-10-08 14:32:15 - INFO - Testing Esri World Imagery endpoint
2025-10-08 14:32:16 - INFO - Esri World Imagery endpoint SUCCESS - Status: 200
2025-10-08 14:32:20 - ERROR - NAIP endpoint TIMEOUT - Connection timeout after 5s
2025-10-08 14:35:42 - INFO - Geocoding request for address: 123 Main St
```

## Basemap Information

### Imagery Update Frequencies

| Basemap | Update Frequency | Resolution | Coverage |
|---------|-----------------|------------|----------|
| Esri World Imagery | Quarterly-Annually | 30cm-1m | Global |
| Google Satellite | Monthly-Annually | 15cm-1m | Global |
| Esri Clarity | Annually | 30-50cm | Global Urban |
| USDA NAIP | 2-3 years/state | 60cm-1m | US Only |

### Government Shutdowns

During US government shutdowns, USDA NAIP imagery may be unavailable. The app will:
- Detect NAIP unavailability on startup
- Show a warning in the sidebar
- Provide a manual retest button
- Automatically hide NAIP from basemap options until available

## Technical Details

### Coordinate System
- Uses WGS84 (EPSG:4326) for all geographic coordinates
- Converts to meters using approximate scaling factors for area calculations
- Latitude: ~111,000m per degree
- Longitude: ~82,000m per degree at 42°N (varies by latitude)

### Calculation Method
```
Estimated Spaces = (Total Area × Efficiency Factor) / Space Area
```

Where:
- Total Area = Polygon area in m²
- Efficiency Factor = 0.65-0.87 (depending on parking type)
- Space Area = Width × Length of individual parking space

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Known Issues

- USDA NAIP imagery may be unavailable during government shutdowns
- Geocoding requires internet connectivity
- Some corporate networks may block tile service requests
- Area calculations are approximate due to coordinate system simplifications

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **Esri** for World Imagery and Clarity basemaps
- **Google** for satellite imagery
- **USDA** for NAIP aerial imagery
- **OpenStreetMap** contributors for map data
- **Nominatim** for geocoding services
- **Streamlit** for the web framework
- **Folium** for mapping capabilities

## Contact

Your Name - [@yourhandle](https://twitter.com/yourhandle)

Project Link: [https://github.com/yourusername/parking-space-estimator](https://github.com/yourusername/parking-space-estimator)

## Changelog

### Version 1.0.0 (2025-10-08)
- Initial release
- Multiple basemap support
- Address search functionality
- Configurable parking types
- Comprehensive error logging
- Endpoint monitoring and testing
- Automatic fallback for failed basemaps