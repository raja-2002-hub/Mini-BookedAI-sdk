# Duffel Stays MCP Server

A Model Context Protocol (MCP) server that provides hotel and accommodation search capabilities using the Duffel API.

## Prerequisites

- Rust (latest stable version)
- A Duffel API account and API token

## Setup

1. **Get a Duffel API Token**
   - Sign up at [Duffel](https://duffel.com)
   - Navigate to your dashboard and create an API token
   - Copy the token for use in environment variables

2. **Set Environment Variable**
   ```bash
   export DUFFEL_API_TOKEN=your_duffel_api_token_here
   ```

3. **Build the Server**
   ```bash
   cd mcps/mcp_duffel_stays
   cargo build --release
   ```

## Usage

### Running the Server

```bash
cd mcps/mcp_duffel_stays
DUFFEL_API_TOKEN=your_token_here cargo run
```

### MCP Tools Available

#### `search_stays`

Search for hotels and accommodations using the Duffel API.

**Parameters:**
- `location` (required): Location/city to search for hotels (e.g., "New York", "Paris", "Tokyo")
- `check_in_date` (required): Check-in date in YYYY-MM-DD format
- `check_out_date` (required): Check-out date in YYYY-MM-DD format
- `adults` (optional): Number of adult guests (default: 1)
- `children` (optional): Number of child guests (default: 0)
- `rooms` (optional): Number of rooms needed (default: 1)

**Example JSON-RPC call:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_stays",
    "arguments": {
      "location": "New York",
      "check_in_date": "2024-12-15",
      "check_out_date": "2024-12-17",
      "adults": 2,
      "children": 0,
      "rooms": 1
    }
  }
}
```

## Integration with MCP Clients

This server can be integrated with any MCP-compatible client. The server communicates via JSON-RPC over HTTP.

**Default Port:** 3002 (different from flights server on 3001)

## Environment Variables

- `DUFFEL_API_TOKEN` (required): Your Duffel API token
- `PORT` (optional): Server port (default: 3002)

## Error Handling

The server handles various error conditions:
- Missing or invalid API token
- Invalid date formats
- Duffel API errors
- Network connectivity issues

All errors are returned as proper JSON-RPC error responses.

## Features

### Hotel Search Results Include:
- Hotel name and star rating
- Location details
- Pricing in local currency
- Room types available
- Amenities (WiFi, Pool, Spa, etc.)
- Cancellation policies
- Check-in/check-out dates

### Example Response:
```
Found 5 hotel offers in New York:

1. Grand Hotel - 170.00 USD
   Rating: 5.0/5.0 stars
   Location: Downtown, New York
   Check-in: 2024-12-15 | Check-out: 2024-12-17
   Room: Standard Room
   Amenities: WiFi, Pool, Spa, Restaurant
   Cancellation: Free cancellation until 24 hours before check-in

2. City Inn - 220.00 USD
   Rating: 3.5/5.0 stars
   Location: City Center, New York
   ...
```

## Development Notes

Currently uses mock data for demonstration. To implement real Duffel stays API integration:

1. Research Duffel's actual stays/accommodation API endpoints
2. Update the API calls in `search_stays()` method
3. Implement proper response parsing for real stay data
4. Handle Duffel-specific error responses

## API Reference

- **Health Check:** `GET /health`
- **MCP Endpoint:** `POST /mcp`
- **Server Info:** `GET /` 