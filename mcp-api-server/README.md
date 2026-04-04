# API Integration MCP Server

A versatile MCP (Model Context Protocol) server that provides Claude with access to multiple external APIs and web services.

## Features

This MCP server provides the following tools:

| Tool | Description | API Key Required |
|------|-------------|------------------|
| `http_request` | General purpose HTTP client for any API | No |
| `get_weather` | Current weather for any city | Yes (OpenWeatherMap) |
| `get_exchange_rate` | Currency conversion | Yes (ExchangeRate-API) |
| `shorten_url` | URL shortening service | No |
| `get_ip_info` | IP geolocation lookup | No |
| `get_random_data` | Generate random UUIDs, strings, integers | No |
| `dns_lookup` | DNS record queries | No |

## Installation

### 1. Clone/Navigate to the Server Directory

```bash
cd mcp-api-server
```

### 2. Create Virtual Environment

```bash
# Linux/Mac
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables (Optional)

For full functionality, set these API keys:

```bash
# OpenWeatherMap (free tier available at openweathermap.org)
export OPENWEATHER_API_KEY="your_api_key_here"

# ExchangeRate-API (free tier available at exchangerate-api.com)
export EXCHANGE_RATE_API_KEY="your_api_key_here"
```

On Windows:
```cmd
set OPENWEATHER_API_KEY=your_api_key_here
set EXCHANGE_RATE_API_KEY=your_api_key_here
```

## Register with Claude

Add to your Claude configuration file:

### Linux/Mac
`~/.claude/mcp.json`:
```json
{
  "mcpServers": {
    "api-integration": {
      "command": "python3",
      "args": ["/path/to/mcp-api-server/api_server.py"],
      "env": {
        "OPENWEATHER_API_KEY": "your_api_key_here",
        "EXCHANGE_RATE_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Windows
`%USERPROFILE%\.claude\mcp.json`:
```json
{
  "mcpServers": {
    "api-integration": {
      "command": "python",
      "args": ["C:\\path\\to\\mcp-api-server\\api_server.py"],
      "env": {
        "OPENWEATHER_API_KEY": "your_api_key_here",
        "EXCHANGE_RATE_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

## Usage Examples

Once registered, you can ask Claude to:

### Weather
- "What's the weather in Tokyo?"
- "Get me the weather in New York in Fahrenheit"

### HTTP Requests
- "Make a GET request to https://api.github.com/users/github"
- "POST to this API with JSON body {\"name\": \"test\"}"

### Currency Conversion
- "Convert 100 USD to EUR"
- "What's the exchange rate from CNY to JPY?"

### URL Shortening
- "Shorten this URL: https://example.com/very/long/path"

### IP Geolocation
- "Where is this IP located: 8.8.8.8"
- "What's my IP information?"

### Random Data
- "Generate 5 random UUIDs"
- "Give me 10 random strings"

### DNS Lookup
- "Lookup DNS A records for google.com"
- "Get MX records for example.com"

## Testing

You can test the server manually:

```bash
# Test with MCP Inspector
npx @anthropics/mcp-inspector python api_server.py

# Or send JSON-RPC directly
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python api_server.py
```

## API Key Setup

### OpenWeatherMap (for weather)
1. Go to https://openweathermap.org/
2. Sign up for a free account
3. Get your API key from the dashboard
4. Free tier: 1000 calls/day

### ExchangeRate-API (for currency conversion)
1. Go to https://www.exchangerate-api.com/
2. Sign up for a free account
3. Get your API key
4. Free tier: 1500 requests/month

## No-API-Key Features

These tools work without any API keys:
- `http_request` - General HTTP client
- `shorten_url` - URL shortening
- `get_ip_info` - IP geolocation
- `get_random_data` - Random data generation
- `dns_lookup` - DNS queries

## Troubleshooting

### "Module not found" errors
Make sure you've activated the virtual environment and installed requirements.

### "API key not set" errors
Some features require API keys. Set the environment variables or use the no-key features.

### Server not connecting to Claude
- Check the path in mcp.json is correct
- Ensure Python is in your PATH
- Try using the full path to the Python executable

## Security Notes

- The `http_request` tool can make requests to any URL - use with caution
- API keys are passed via environment variables, not hardcoded
- DNS lookup requires the `dnspython` package

## License

MIT