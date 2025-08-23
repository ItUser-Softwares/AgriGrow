#!/usr/bin/env python3
"""
Pakistan Agriculture Data API with FastAPI
Fetches free agricultural APIs and serves clean data for crop recommendations
"""

import requests
import json
import sqlite3
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import logging
import asyncio
import aiohttp
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Pakistan Agriculture API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 👈 or restrict to ["http://127.0.0.1:5500"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class WeatherData(BaseModel):
    temperature: float
    humidity: float
    rainfall: float
    wind_speed: float
    date: str

class SoilData(BaseModel):
    ph: float
    organic_matter: float
    nitrogen: float
    phosphorus: float
    potassium: float
    soil_type: str

class CropRecommendation(BaseModel):
    crop_name: str
    suitability_score: float
    irrigation_need: float
    fertilizer_npk: str
    season: str
    planting_months: List[str]

class LocationRequest(BaseModel):
    latitude: float
    longitude: float

class AgricultureResponse(BaseModel):
    location: Dict
    weather: WeatherData
    soil: SoilData
    crop_recommendations: List[CropRecommendation]

class DataCollector:
    """Collects data from various free APIs"""
    
    def __init__(self):
        self.db_path = 'agriculture_data.db'
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Weather data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                temperature REAL,
                humidity REAL,
                rainfall REAL,
                wind_speed REAL,
                date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Soil data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS soil_data (
                id INTEGER PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                ph REAL,
                organic_matter REAL,
                nitrogen REAL,
                phosphorus REAL,
                potassium REAL,
                soil_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Crop recommendations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crop_recommendations (
                id INTEGER PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                crop_name TEXT,
                suitability_score REAL,
                irrigation_need REAL,
                fertilizer_npk TEXT,
                season TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    async def fetch_weather_data(self, lat: float, lon: float) -> Optional[WeatherData]:
        """Fetch weather data from Open-Meteo (free API)"""
        try:
            url = f"https://api.open-meteo.com/v1/forecast"
            params = {
                'latitude': lat,
                'longitude': lon,
                'current': 'temperature_2m,relative_humidity_2m,rain,wind_speed_10m',
                'timezone': 'Asia/Karachi'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        current = data['current']
                        
                        weather = WeatherData(
                            temperature=current.get('temperature_2m', 0),
                            humidity=current.get('relative_humidity_2m', 0),
                            rainfall=current.get('rain', 0),
                            wind_speed=current.get('wind_speed_10m', 0),
                            date=current.get('time', '')
                        )
                        
                        # Save to database
                        self.save_weather_data(lat, lon, weather)
                        return weather
                        
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            return None
    
    async def fetch_nasa_power_data(self, lat: float, lon: float) -> Dict:
        """Fetch solar and climate data from NASA POWER API (free)"""
        try:
            url = "https://power.larc.nasa.gov/api/temporal/daily/point"
            params = {
                'parameters': 'T2M,PRECTOTCORR,RH2M,WS2M',
                'community': 'AG',
                'longitude': lon,
                'latitude': lat,
                'start': (datetime.now() - timedelta(days=30)).strftime('%Y%m%d'),
                'end': datetime.now().strftime('%Y%m%d'),
                'format': 'JSON'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('properties', {}).get('parameter', {})
                        
        except Exception as e:
            logger.error(f"Error fetching NASA POWER data: {e}")
            return {}
    
    def get_soil_data(self, lat: float, lon: float) -> SoilData:
        """Get soil data based on Pakistan regions"""
        # Pakistan soil data approximation by region
        soil_data = {
            # Punjab (fertile alluvial soil)
            'punjab': SoilData(
                ph=7.2, organic_matter=1.8, nitrogen=0.05, 
                phosphorus=12.5, potassium=180, soil_type='Alluvial'
            ),
            # Sindh (riverine and desert soil)
            'sindh': SoilData(
                ph=7.8, organic_matter=1.2, nitrogen=0.03, 
                phosphorus=8.5, potassium=120, soil_type='Riverine'
            ),
            # KPK (mountainous soil)
            'kpk': SoilData(
                ph=6.8, organic_matter=2.1, nitrogen=0.06, 
                phosphorus=15.0, potassium=200, soil_type='Mountain'
            ),
            # Balochistan (arid soil)
            'balochistan': SoilData(
                ph=8.1, organic_matter=0.8, nitrogen=0.02, 
                phosphorus=6.0, potassium=90, soil_type='Arid'
            )
        }
        
        # Determine region based on coordinates
        if 30.0 <= lat <= 33.0 and 70.0 <= lon <= 75.0:
            return soil_data['punjab']
        elif 24.0 <= lat <= 28.0 and 66.0 <= lon <= 71.0:
            return soil_data['sindh']
        elif 33.0 <= lat <= 37.0 and 69.0 <= lon <= 74.0:
            return soil_data['kpk']
        elif 24.0 <= lat <= 32.0 and 60.0 <= lon <= 70.0:
            return soil_data['balochistan']
        else:
            return soil_data['punjab']  # default
    
    def get_crop_recommendations(self, lat: float, lon: float, weather: WeatherData, soil: SoilData) -> List[CropRecommendation]:
        """Generate crop recommendations based on location, weather, and soil"""
        recommendations = []
        
        # Pakistan major crops with their requirements
        crops_data = {
            'wheat': {
                'temp_range': (15, 25),
                'ph_range': (6.0, 7.5),
                'season': 'Rabi',
                'months': ['November', 'December'],
                'water_need': 450,  # mm
                'npk': '120-60-60'
            },
            'rice': {
                'temp_range': (20, 35),
                'ph_range': (5.5, 7.0),
                'season': 'Kharif',
                'months': ['May', 'June', 'July'],
                'water_need': 1200,
                'npk': '120-90-60'
            },
            'cotton': {
                'temp_range': (21, 30),
                'ph_range': (5.8, 8.0),
                'season': 'Kharif',
                'months': ['April', 'May'],
                'water_need': 800,
                'npk': '150-75-75'
            },
            'sugarcane': {
                'temp_range': (20, 35),
                'ph_range': (6.0, 7.5),
                'season': 'Kharif',
                'months': ['February', 'March', 'April'],
                'water_need': 1500,
                'npk': '200-100-100'
            },
            'maize': {
                'temp_range': (15, 30),
                'ph_range': (6.0, 7.0),
                'season': 'Kharif',
                'months': ['June', 'July'],
                'water_need': 600,
                'npk': '120-80-60'
            }
        }
        
        for crop_name, crop_data in crops_data.items():
            # Calculate suitability score based on temperature and pH
            temp_score = self.calculate_temperature_score(weather.temperature, crop_data['temp_range'])
            ph_score = self.calculate_ph_score(soil.ph, crop_data['ph_range'])
            
            # Overall suitability (0-10 scale)
            suitability = (temp_score + ph_score) / 2
            
            if suitability >= 5.0:  # Only recommend if reasonably suitable
                recommendations.append(CropRecommendation(
                    crop_name=crop_name.title(),
                    suitability_score=round(suitability, 1),
                    irrigation_need=crop_data['water_need'],
                    fertilizer_npk=crop_data['npk'],
                    season=crop_data['season'],
                    planting_months=crop_data['months']
                ))
        
        # Sort by suitability score
        recommendations.sort(key=lambda x: x.suitability_score, reverse=True)
        return recommendations[:3]  # Top 3 recommendations
    
    def calculate_temperature_score(self, current_temp: float, optimal_range: tuple) -> float:
        """Calculate temperature suitability score (0-10)"""
        min_temp, max_temp = optimal_range
        if min_temp <= current_temp <= max_temp:
            return 10.0
        elif current_temp < min_temp:
            diff = min_temp - current_temp
            return max(0, 10 - (diff * 0.5))
        else:  # current_temp > max_temp
            diff = current_temp - max_temp
            return max(0, 10 - (diff * 0.5))
    
    def calculate_ph_score(self, current_ph: float, optimal_range: tuple) -> float:
        """Calculate pH suitability score (0-10)"""
        min_ph, max_ph = optimal_range
        if min_ph <= current_ph <= max_ph:
            return 10.0
        elif current_ph < min_ph:
            diff = min_ph - current_ph
            return max(0, 10 - (diff * 2))
        else:  # current_ph > max_ph
            diff = current_ph - max_ph
            return max(0, 10 - (diff * 2))
    
    def save_weather_data(self, lat: float, lon: float, weather: WeatherData):
        """Save weather data to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO weather_data (latitude, longitude, temperature, humidity, rainfall, wind_speed, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (lat, lon, weather.temperature, weather.humidity, weather.rainfall, weather.wind_speed, weather.date))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving weather data: {e}")

# Initialize data collector
data_collector = DataCollector()

@app.get("/")
async def root():
    return {"message": "Pakistan Agriculture Data API", "version": "1.0.0"}

@app.get("/api/v1/weather/{lat}/{lon}")
async def get_weather_data(lat: float, lon: float):
    """Get weather data for specific coordinates"""
    if not (23.0 <= lat <= 37.0 and 60.0 <= lon <= 77.0):
        raise HTTPException(status_code=400, detail="Coordinates outside Pakistan")
    
    weather = await data_collector.fetch_weather_data(lat, lon)
    if not weather:
        raise HTTPException(status_code=500, detail="Failed to fetch weather data")
    
    return weather

@app.get("/api/v1/soil/{lat}/{lon}")
async def get_soil_data(lat: float, lon: float):
    """Get soil data for specific coordinates"""
    if not (23.0 <= lat <= 37.0 and 60.0 <= lon <= 77.0):
        raise HTTPException(status_code=400, detail="Coordinates outside Pakistan")
    
    soil = data_collector.get_soil_data(lat, lon)
    return soil

@app.get("/api/v1/crops/{lat}/{lon}")
async def get_crop_recommendations(lat: float, lon: float):
    """Get crop recommendations for specific coordinates"""
    if not (23.0 <= lat <= 37.0 and 60.0 <= lon <= 77.0):
        raise HTTPException(status_code=400, detail="Coordinates outside Pakistan")
    
    weather = await data_collector.fetch_weather_data(lat, lon)
    if not weather:
        raise HTTPException(status_code=500, detail="Failed to fetch weather data")
    
    soil = data_collector.get_soil_data(lat, lon)
    recommendations = data_collector.get_crop_recommendations(lat, lon, weather, soil)
    
    return {
        "location": {"latitude": lat, "longitude": lon},
        "recommendations": recommendations
    }

@app.get("/api/v1/analysis/{lat}/{lon}")
async def get_complete_analysis(lat: float, lon: float):
    """Get complete agricultural analysis for specific coordinates"""
    if not (23.0 <= lat <= 37.0 and 60.0 <= lon <= 77.0):
        raise HTTPException(status_code=400, detail="Coordinates outside Pakistan")
    
    try:
        # Fetch weather data
        weather = await data_collector.fetch_weather_data(lat, lon)
        if not weather:
            raise HTTPException(status_code=500, detail="Failed to fetch weather data")
        
        # Get soil data
        soil = data_collector.get_soil_data(lat, lon)
        
        # Get crop recommendations
        recommendations = data_collector.get_crop_recommendations(lat, lon, weather, soil)
        
        # Determine region name
        region = "Unknown"
        if 30.0 <= lat <= 33.0 and 70.0 <= lon <= 75.0:
            region = "Punjab"
        elif 24.0 <= lat <= 28.0 and 66.0 <= lon <= 71.0:
            region = "Sindh"
        elif 33.0 <= lat <= 37.0 and 69.0 <= lon <= 74.0:
            region = "Khyber Pakhtunkhwa"
        elif 24.0 <= lat <= 32.0 and 60.0 <= lon <= 70.0:
            region = "Balochistan"
        
        return AgricultureResponse(
            location={
                "latitude": lat,
                "longitude": lon,
                "region": region,
                "country": "Pakistan"
            },
            weather=weather,
            soil=soil,
            crop_recommendations=recommendations
        )
        
    except Exception as e:
        logger.error(f"Error in complete analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/batch-analysis")
async def batch_analysis(locations: List[LocationRequest]):
    """Get analysis for multiple locations"""
    if len(locations) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 locations per request")
    
    results = []
    for loc in locations:
        if not (23.0 <= loc.latitude <= 37.0 and 60.0 <= loc.longitude <= 77.0):
            continue
            
        try:
            weather = await data_collector.fetch_weather_data(loc.latitude, loc.longitude)
            if weather:
                soil = data_collector.get_soil_data(loc.latitude, loc.longitude)
                recommendations = data_collector.get_crop_recommendations(loc.latitude, loc.longitude, weather, soil)
                
                results.append({
                    "location": {"latitude": loc.latitude, "longitude": loc.longitude},
                    "weather": weather,
                    "soil": soil,
                    "crop_recommendations": recommendations
                })
        except Exception as e:
            logger.error(f"Error processing location {loc.latitude}, {loc.longitude}: {e}")
            continue
    
    return {"results": results}

@app.get("/api/v1/districts")
async def get_districts():
    """Get list of major districts with coordinates"""
    districts = {
        "Punjab": [
            {"name": "Lahore", "lat": 31.5804, "lon": 74.3587},
            {"name": "Faisalabad", "lat": 31.4504, "lon": 73.1350},
            {"name": "Multan", "lat": 30.1575, "lon": 71.5249},
            {"name": "Rawalpindi", "lat": 33.5651, "lon": 73.0169}
        ],
        "Sindh": [
            {"name": "Karachi", "lat": 24.8607, "lon": 67.0011},
            {"name": "Hyderabad", "lat": 25.3960, "lon": 68.3578},
            {"name": "Sukkur", "lat": 27.7202, "lon": 68.8574}
        ],
        "KPK": [
            {"name": "Peshawar", "lat": 34.0151, "lon": 71.5249},
            {"name": "Mardan", "lat": 34.1989, "lon": 72.0408}
        ],
        "Balochistan": [
            {"name": "Quetta", "lat": 30.1798, "lon": 66.9750}
        ]
    }
    return districts

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)