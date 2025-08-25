
const map = L.map('map', {
    zoomControl: true,
    attributionControl: true
}).setView([30.3753, 69.3451], 6);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 18,
    tileSize: 256
}).addTo(map);

const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles © Esri'
});

const baseMaps = {
    "Street Map": L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'),
    "Satellite": satelliteLayer
};

L.control.layers(baseMaps).addTo(map);

const pakistanProvinces = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": { "name": "Punjab" },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [69.33, 27.72], [75.85, 27.72], [75.85, 34.02], [73.16, 34.02],
                    [72.20, 33.48], [71.78, 32.06], [69.33, 32.06], [69.33, 27.72]
                ]]
            }
        },
        {
            "type": "Feature",
            "properties": { "name": "Sindh" },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [66.50, 23.69], [71.78, 23.69], [71.78, 28.55], [69.33, 28.55],
                    [68.84, 27.22], [66.50, 27.22], [66.50, 23.69]
                ]]
            }
        },
        {
            "type": "Feature",
            "properties": { "name": "KPK" },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [69.33, 31.91], [73.16, 31.91], [73.16, 36.98], [69.33, 36.98], [69.33, 31.91]
                ]]
            }
        },
        {
            "type": "Feature",
            "properties": { "name": "Balochistan" },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [60.87, 23.69], [69.33, 23.69], [69.33, 31.91], [61.92, 31.91],
                    [61.92, 29.40], [60.87, 29.40], [60.87, 23.69]
                ]]
            }
        }
    ]
};

const provinceStyle = {
    color: '#ffffff',
    weight: 2,
    opacity: 0.8,
    fillColor: 'transparent',
    fillOpacity: 0.1,
    dashArray: '5, 5'
};

L.geoJSON(pakistanProvinces, {
    style: provinceStyle,
    onEachFeature: function (feature, layer) {
        layer.bindTooltip(feature.properties.name, {
            permanent: false,
            direction: 'center',
            className: 'province-tooltip'
        });

        layer.on('mouseover', function () {
            layer.setStyle({
                fillOpacity: 0.3,
                fillColor: '#3498db'
            });
        });

        layer.on('mouseout', function () {
            layer.setStyle(provinceStyle);
        });
    }
}).addTo(map);

const majorCities = [
    { name: "Karachi", lat: 24.8607, lon: 67.0011, province: "Sindh" },
    { name: "Lahore", lat: 31.5804, lon: 74.3587, province: "Punjab" },
    { name: "Faisalabad", lat: 31.4504, lon: 73.1350, province: "Punjab" },
    { name: "Rawalpindi", lat: 33.5651, lon: 73.0169, province: "Punjab" },
    { name: "Multan", lat: 30.1575, lon: 71.5249, province: "Punjab" },
    { name: "Hyderabad", lat: 25.3960, lon: 68.3578, province: "Sindh" },
    { name: "Peshawar", lat: 34.0151, lon: 71.5249, province: "KPK" },
    { name: "Quetta", lat: 30.1798, lon: 66.9750, province: "Balochistan" }
];

majorCities.forEach(city => {
    const marker = L.circleMarker([city.lat, city.lon], {
        color: '#e74c3c',
        fillColor: '#e74c3c',
        fillOpacity: 0.8,
        radius: 8
    }).addTo(map);

    marker.bindTooltip(`${city.name}<br><small>${city.province}</small>`, {
        permanent: false,
        direction: 'top'
    });

    setInterval(() => {
        marker.setRadius(marker.getRadius() === 8 ? 12 : 8);
    }, 2000 + Math.random() * 1000);
});

const coordinatesDisplay = document.getElementById('coordinatesDisplay');

map.on('mousemove', function (e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    coordinatesDisplay.innerHTML = `Lat: ${lat}, Lon: ${lon}`;
});

// ✅ Click Handler with Caching Support
map.on('click', async function (e) {
    e.originalEvent.preventDefault();
    e.originalEvent.stopPropagation();

    const lat = e.latlng.lat;
    const lon = e.latlng.lng;

    if (lat < 23.69 || lat > 36.98 || lon < 60.87 || lon > 75.85) {
        alert('Please click within Pakistan boundaries!');
        return;
    }

    const loadingPopup = L.popup()
        .setLatLng(e.latlng)
        .setContent('<div class="loading"><div class="spinner"></div>Loading agricultural data...</div>')
        .openOn(map);

    try {
        const response = await fetch(`http://localhost:8000/api/v1/analysis/${lat}/${lon}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            cache: 'no-cache'
        });

        if (!response.ok) {
            throw new Error('Failed to fetch data');
        }

        const result = await response.json();
        const isCached = result.cached;
        const data = result.data;

        const popupContent = createPopupContent(data, isCached);
        loadingPopup.setContent(popupContent);

    } catch (error) {
        console.error('Error fetching data:', error);
        const demoData = createDemoData(lat, lon);
        const popupContent = createPopupContent(demoData, false);
        loadingPopup.setContent(popupContent);
    }
});

function searchLocation() {
    event.preventDefault();
    const query = document.getElementById('searchInput').value.trim();

    if (!query) return false;

    const coordMatch = query.match(/(-?\d+\.?\d*),\s*(-?\d+\.?\d*)/);

    if (coordMatch) {
        const lat = parseFloat(coordMatch[1]);
        const lon = parseFloat(coordMatch[2]);

        if (lat >= 23.69 && lat <= 36.98 && lon >= 60.87 && lon <= 75.85) {
            map.setView([lat, lon], 12);
            L.marker([lat, lon]).addTo(map)
                .bindPopup(`Coordinates: ${lat.toFixed(4)}, ${lon.toFixed(4)}`)
                .openPopup();
        } else {
            alert('Coordinates outside Pakistan boundaries!');
        }
    } else {
        const city = majorCities.find(c =>
            c.name.toLowerCase().includes(query.toLowerCase())
        );

        if (city) {
            map.setView([city.lat, city.lon], 10);
            L.marker([city.lat, city.lon]).addTo(map)
                .bindPopup(`${city.name}, ${city.province}`)
                .openPopup();
        } else {
            alert('City not found! Try: Karachi, Lahore, Islamabad, etc.');
        }
    }

    document.getElementById('searchInput').value = '';
    return false;
}

document.getElementById('searchInput').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        searchLocation();
        return false;
    }
});

// ✅ Create Popup Content with Cached Badge
function createPopupContent(data, isCached = false) {
    const weather = data.weather;
    const soil = data.soil;
    const recommendations = data.crop_recommendations;
    const location = data.location;

    const cacheBadge = isCached
        ? `<span class="cached-badge" title="Data served from cache">⚡ Cached</span>`
        : '';

    let cropsHtml = '';
    if (recommendations && recommendations.length > 0) {
        cropsHtml = recommendations.map(crop => `
                <div class="crop-recommendation">
                    <h5>🌾 ${crop.crop_name}</h5>
                    <div class="crop-score">Suitability: ${crop.suitability_score}/10</div>
                    <div style="font-size: 0.85rem;">
                        💧 Water: ${crop.irrigation_need}mm<br>
                        🧪 NPK: ${crop.fertilizer_npk}<br>
                        📅 Season: ${crop.season}<br>
                        🗓️ Plant: ${crop.planting_months ? crop.planting_months.join(', ') : 'N/A'}
                    </div>
                </div>
            `).join('');
    } else {
        cropsHtml = '<div class="crop-recommendation">No suitable crops found for this location.</div>';
    }

    return `
            <div class="popup-content-wrapper">
                <div class="popup-title">🇵🇰 Agricultural Analysis ${cacheBadge}</div>
                
                <div class="popup-section">
                    <h4>📍 Location</h4>
                    <p><strong>Region:</strong> ${location.region || 'Pakistan'}<br>
                    <strong>Coordinates:</strong> ${location.latitude.toFixed(4)}, ${location.longitude.toFixed(4)}</p>
                </div>

                <div class="popup-section">
                    <h4>🌤️ Current Weather</h4>
                    <div class="weather-grid">
                        <div class="weather-item">🌡️<br><strong>${weather.temperature}°C</strong></div>
                        <div class="weather-item">💧<br><strong>${weather.humidity}%</strong></div>
                        <div class="weather-item">🌧️<br><strong>${weather.rainfall}mm</strong></div>
                        <div class="weather-item">💨<br><strong>${weather.wind_speed} km/h</strong></div>
                    </div>
                </div>

                <div class="popup-section">
                    <h4>🌱 Soil Analysis</h4>
                    <div class="soil-grid">
                        <div class="soil-item">pH: ${soil.ph}</div>
                        <div class="soil-item">Type: ${soil.soil_type}</div>
                        <div class="soil-item">N: ${soil.nitrogen}%</div>
                        <div class="soil-item">P: ${soil.phosphorus} ppm</div>
                        <div class="soil-item">K: ${soil.potassium} ppm</div>
                        <div class="soil-item">OM: ${soil.organic_matter}%</div>
                    </div>
                </div>

                <div class="popup-section">
                    <h4>🌾 Crop Recommendations</h4>
                    <div class="crop-recommendations-container">
                        ${cropsHtml}
                    </div>
                </div>
            </div>
        `;
}

function createDemoData(lat, lon) {
    return {
        location: {
            latitude: lat,
            longitude: lon,
            region: lat > 31 ? "Punjab" : lat > 27 ? "Sindh" : "Balochistan"
        },
        weather: {
            temperature: 25 + Math.random() * 15,
            humidity: 40 + Math.random() * 40,
            rainfall: Math.random() * 10,
            wind_speed: 5 + Math.random() * 15,
            date: new Date().toISOString()
        },
        soil: {
            ph: 6.5 + Math.random() * 2,
            organic_matter: 1 + Math.random() * 2,
            nitrogen: 0.02 + Math.random() * 0.05,
            phosphorus: 8 + Math.random() * 15,
            potassium: 100 + Math.random() * 150,
            soil_type: "Alluvial"
        },
        crop_recommendations: [
            {
                crop_name: "Wheat",
                suitability_score: 7 + Math.random() * 2,
                irrigation_need: 450,
                fertilizer_npk: "120-60-60",
                season: "Rabi",
                planting_months: ["November", "December"]
            },
            {
                crop_name: "Rice",
                suitability_score: 6 + Math.random() * 2,
                irrigation_need: 1200,
                fertilizer_npk: "120-90-60",
                season: "Kharif",
                planting_months: ["May", "June"]
            }
        ]
    };
}

setTimeout(() => {
    map.flyTo([30.3753, 69.3451], 6, {
        animate: true,
        duration: 2
    });
}, 1000);
