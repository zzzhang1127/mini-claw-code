#!/usr/bin/env python3
"""API Integration MCP Server

A versatile MCP server that integrates with multiple external APIs:
- Weather API (OpenWeatherMap)
- HTTP Request tool (general purpose)
- URL shortening
- Exchange rates
"""

import os
import json
import asyncio
from urllib.parse import urlencode
from typing import Optional

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Create server instance
server = Server("api-integration-server")


# ============================================================================
# Tool: HTTP Request (General Purpose)
# ============================================================================

@server.tool()
async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[str] = None,
    body: Optional[str] = None,
    params: Optional[str] = None
) -> str:
    """Make an HTTP request to any API endpoint.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        headers: JSON string of headers (optional)
        body: Request body as string (optional)
        params: Query parameters as JSON string (optional)
    """
    try:
        # Parse JSON inputs
        header_dict = json.loads(headers) if headers else {}
        param_dict = json.loads(params) if params else {}
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=header_dict,
                params=param_dict,
                content=body,
                timeout=30.0
            )
            
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text
            }
            
            # Try to parse JSON response
            try:
                result["json"] = response.json()
            except:
                pass
                
            return json.dumps(result, indent=2, default=str)
            
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# Tool: Weather API
# ============================================================================

@server.tool()
async def get_weather(city: str, units: str = "metric") -> str:
    """Get current weather for a city using OpenWeatherMap API.
    
    Requires OPENWEATHER_API_KEY environment variable.

    Args:
        city: City name (e.g., "London", "New York", "Tokyo")
        units: Temperature units - "metric" (Celsius), "imperial" (Fahrenheit), or "kelvin"
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return "Error: OPENWEATHER_API_KEY environment variable not set"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={
                    "q": city,
                    "appid": api_key,
                    "units": units
                }
            )
            
            if response.status_code != 200:
                return f"Error: {response.json().get('message', 'Unknown error')}"
            
            data = response.json()
            
            temp_unit = {"metric": "¡ãC", "imperial": "¡ãF", "kelvin": "K"}.get(units, "¡ãC")
            
            weather_info = {
                "city": data["name"],
                "country": data["sys"]["country"],
                "temperature": f"{data['main']['temp']}{temp_unit}",
                "feels_like": f"{data['main']['feels_like']}{temp_unit}",
                "humidity": f"{data['main']['humidity']}%",
                "pressure": f"{data['main']['pressure']} hPa",
                "weather": data["weather"][0]["description"],
                "wind_speed": f"{data['wind']['speed']} m/s",
                "visibility": f"{data.get('visibility', 'N/A')} m",
                "cloudiness": f"{data['clouds']['all']}%"
            }
            
            return json.dumps(weather_info, indent=2)
            
    except Exception as e:
        return f"Error fetching weather: {str(e)}"


# ============================================================================
# Tool: Exchange Rates
# ============================================================================

@server.tool()
async def get_exchange_rate(from_currency: str, to_currency: str, amount: float = 1.0) -> str:
    """Get current exchange rate between currencies.
    
    Uses exchangerate-api.com (free tier available).
    Requires EXCHANGE_RATE_API_KEY environment variable.

    Args:
        from_currency: Source currency code (e.g., "USD", "EUR", "CNY")
        to_currency: Target currency code (e.g., "USD", "EUR", "CNY")
        amount: Amount to convert (default: 1.0)
    """
    api_key = os.environ.get("EXCHANGE_RATE_API_KEY")
    if not api_key:
        return "Error: EXCHANGE_RATE_API_KEY environment variable not set"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_currency.upper()}/{to_currency.upper()}/{amount}"
            )
            
            if response.status_code != 200:
                return f"Error: Failed to fetch exchange rate"
            
            data = response.json()
            
            if data.get("result") != "success":
                return f"Error: {data.get('error-type', 'Unknown error')}"
            
            result = {
                "from": from_currency.upper(),
                "to": to_currency.upper(),
                "amount": amount,
                "converted_amount": data["conversion_result"],
                "rate": data["conversion_rate"],
                "last_updated": data["time_last_update_utc"]
            }
            
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return f"Error fetching exchange rate: {str(e)}"


# ============================================================================
# Tool: URL Shortener (using cleanuri.com - no API key required)
# ============================================================================

@server.tool()
async def shorten_url(long_url: str) -> str:
    """Shorten a URL using CleanURI service (free, no API key required).

    Args:
        long_url: The long URL to shorten
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://cleanuri.com/api/v1/shorten",
                data={"url": long_url}
            )
            
            if response.status_code != 200:
                return f"Error: {response.text}"
            
            data = response.json()
            return json.dumps({
                "original_url": long_url,
                "short_url": data.get("result_url"),
                "success": True
            }, indent=2)
            
    except Exception as e:
        return f"Error shortening URL: {str(e)}"


# ============================================================================
# Tool: IP Geolocation
# ============================================================================

@server.tool()
async def get_ip_info(ip: Optional[str] = None) -> str:
    """Get geolocation information for an IP address.
    
    Uses ip-api.com (free for non-commercial use, no API key required).

    Args:
        ip: IP address to lookup (optional, uses your IP if not provided)
    """
    try:
        target = ip if ip else ""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://ip-api.com/json/{target}",
                params={"fields": "status,message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,query"}
            )
            
            data = response.json()
            
            if data.get("status") != "success":
                return f"Error: {data.get('message', 'Failed to get IP info')}"
            
            result = {
                "ip": data["query"],
                "country": data["country"],
                "country_code": data["countryCode"],
                "region": data["regionName"],
                "city": data["city"],
                "zip": data["zip"],
                "latitude": data["lat"],
                "longitude": data["lon"],
                "timezone": data["timezone"],
                "isp": data["isp"],
                "organization": data["org"]
            }
            
            return json.dumps(result, indent=2)
            
    except Exception as e:
        return f"Error getting IP info: {str(e)}"


# ============================================================================
# Tool: Random Data Generator
# ============================================================================

@server.tool()
async def get_random_data(data_type: str = "uuid", count: int = 1) -> str:
    """Get random data from random.org or generate locally.
    
    Uses random.org for true randomness (free tier available).
    Falls back to local generation if API fails.

    Args:
        data_type: Type of random data - "uuid", "integer", "string", "boolean"
        count: Number of items to generate (max 100)
    """
    import uuid
    import random
    import string
    
    count = min(count, 100)
    
    try:
        results = []
        
        for _ in range(count):
            if data_type == "uuid":
                results.append(str(uuid.uuid4()))
            elif data_type == "integer":
                results.append(random.randint(1, 1000000))
            elif data_type == "string":
                length = random.randint(8, 32)
                chars = string.ascii_letters + string.digits
                results.append(''.join(random.choice(chars) for _ in range(length)))
            elif data_type == "boolean":
                results.append(random.choice([True, False]))
            else:
                return f"Error: Unknown data_type '{data_type}'. Use: uuid, integer, string, boolean"
        
        return json.dumps({
            "data_type": data_type,
            "count": len(results),
            "data": results if count > 1 else results[0]
        }, indent=2)
        
    except Exception as e:
        return f"Error generating random data: {str(e)}"


# ============================================================================
# Tool: DNS Lookup
# ============================================================================

@server.tool()
async def dns_lookup(domain: str, record_type: str = "A") -> str:
    """Perform DNS lookup for a domain.

    Args:
        domain: Domain name to lookup (e.g., "google.com")
        record_type: DNS record type (A, AAAA, MX, NS, TXT, CNAME, SOA)
    """
    import socket
    import dns.resolver
    
    try:
        record_type = record_type.upper()
        
        if record_type == "A":
            answers = dns.resolver.resolve(domain, 'A')
            results = [str(rdata) for rdata in answers]
        elif record_type == "AAAA":
            answers = dns.resolver.resolve(domain, 'AAAA')
            results = [str(rdata) for rdata in answers]
        elif record_type == "MX":
            answers = dns.resolver.resolve(domain, 'MX')
            results = [f"{rdata.preference} {rdata.exchange}" for rdata in answers]
        elif record_type == "NS":
            answers = dns.resolver.resolve(domain, 'NS')
            results = [str(rdata) for rdata in answers]
        elif record_type == "TXT":
            answers = dns.resolver.resolve(domain, 'TXT')
            results = [str(rdata) for rdata in answers]
        elif record_type == "CNAME":
            answers = dns.resolver.resolve(domain, 'CNAME')
            results = [str(rdata) for rdata in answers]
        elif record_type == "SOA":
            answers = dns.resolver.resolve(domain, 'SOA')
            results = [str(rdata) for rdata in answers]
        else:
            return f"Error: Unsupported record type '{record_type}'"
        
        return json.dumps({
            "domain": domain,
            "record_type": record_type,
            "records": results
        }, indent=2)
        
    except Exception as e:
        return f"Error performing DNS lookup: {str(e)}"


# ============================================================================
# Server Runner
# ============================================================================

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)


if __name__ == "__main__":
    asyncio.run(main())