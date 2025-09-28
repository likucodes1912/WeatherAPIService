Weather Aggregator API 🌤️
A robust Flask-based weather service that aggregates data from multiple weather providers to deliver accurate and reliable weather information. Features caching, rate limiting, and comprehensive API documentation.
This Project is done by LIKULEASH +91 94892 84767 

🌟 Features
1. Multi-Provider Aggregation: Combines data from OpenWeatherMap and WeatherAPI for enhanced accuracy
2. Smart Caching: TTL-based caching to reduce external API calls and improve performance
3. Rate Limiting: Built-in protection against API abuse with configurable limits
4. RESTful API: Clean, well-documented endpoints following REST principles
5. Swagger Documentation: Interactive API documentation with automatic UI generation
6. Geocoding Support: Location search and validation
7. Error Handling: Comprehensive error handling with meaningful response codes
8. Production Ready: Environment-based configuration and logging

🚀 Quick Start
Prerequisites
Python 3.8+

API keys from OpenWeatherMap and/or WeatherAPI
Installation
Clone the repository

bash
git clone https://github.com/yourusername/weather-aggregator-api.git
cd weather-aggregator-api
Create virtual environment

bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
Install dependencies

bash
pip install -r requirements.txt
Configure environment variables

bash
cp .env.example .env
# Edit .env with your API keys
env
OPENWEATHER_API_KEY=your_openweather_api_key_here
WEATHERAPI_KEY=your_weatherapi_key_here
CACHE_TTL_SECONDS=300
CACHE_MAXSIZE=1000
FLASK_DEBUG=0
PORT=5000
Run the application

bash
python app.py
The API will be available at http://localhost:5000

📚 API Endpoints
🔍 Current Weather
GET /weather/current?location={city}

Get aggregated current weather data for a location.

Example:
bash
curl "http://localhost:5000/weather/current?location=London"
Response:

json
{
  "location": {
    "name": "London, GB",
    "lat": 51.5074,
    "lon": -0.1278
  },
  "temperature_c": 15.5,
  "feels_like_c": 14.8,
  "humidity": 72,
  "condition": "Partly cloudy",
  "sources": {
    "openweathermap": { ... },
    "weatherapi": { ... }
  }
}
📅 Weather Forecast
GET /weather/forecast?location={city}&days={n}

Get weather forecast for 1-7 days.
Example:

bash
curl "http://localhost:5000/weather/forecast?location=Paris&days=3"
Response:

json
{
  "location": { ... },
  "forecast": [
    {
      "date": "2024-01-15",
      "min_c": 8.5,
      "max_c": 15.2,
      "avg_c": 12.1,
      "condition": "Sunny"
    }
  ]
}
🔎 Location Search
GET /locations/search?q={query}

Search for locations by name.

Example:
bash
curl "http://localhost:5000/locations/search?q=New York"
Response:

json
{
  "results": [
    {
      "name": "New York, US",
      "lat": 40.7128,
      "lon": -74.0060
    }
  ]
}
❤️ Health Check
GET /health

Check API status and uptime.

Response:

json
{
  "status": "ok",
  "uptime_seconds": 12345
}
🔧 Configuration
Environment Variables
Variable	Description	Default
OPENWEATHER_API_KEY	OpenWeatherMap API key	Required
WEATHERAPI_KEY	WeatherAPI key	Required
CACHE_TTL_SECONDS	Cache time-to-live in seconds	300
CACHE_MAXSIZE	Maximum cache entries	1000
FLASK_DEBUG	Enable debug mode	0
PORT	Server port	5000
Rate Limiting
Default: 60 requests per minute per IP

Search Endpoint: 30 requests per minute per IP

Configurable via environment variables

🏗️ Architecture

Provider Aggregation
The service intelligently combines data from multiple providers:
Numeric values (temperature, humidity): Averaged across providers
Weather conditions: Most frequent condition is selected
Fallback handling: Continues working if one provider fails

🚀 Deployment
Development

bash
python app.py
Production with Gunicorn
bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
Docker Deployment
dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]

📊 Monitoring & Logging
The application includes comprehensive logging:
Request/response logging
Error tracking
Cache performance metrics
Provider availability monitoring
View logs in real-time:

bash
tail -f /var/log/weather-api.log
🤝 Contributing

1. Fork the repository
2. Create a feature branch (git checkout -b feature/amazing-feature)
3. Commit your changes (git commit -m 'Add amazing feature')
4. Push to the branch (git push origin feature/amazing-feature)
5. Open a Pull Request


🙏 Acknowledgments
OpenWeatherMap for their free weather API tier

WeatherAPI for additional weather data

Flask community for excellent documentation and examples

📞 Support
For support, please open an issue in the GitHub repository or contact the development team.

