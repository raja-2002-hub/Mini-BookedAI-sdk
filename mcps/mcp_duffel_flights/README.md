# Duffel Flights MCP Server

A Model Context Protocol (MCP) server that provides flight search capabilities using the Duffel API.

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
   cd mcps/mcp_duffel_flights
   cargo build --release
   ```

## Usage

### Running the Server

```bash
cd mcps/mcp_duffel_flights
DUFFEL_API_TOKEN=your_token_here cargo run
```

### MCP Tools Available

#### `search_flights`

Search for flights using the Duffel API.

**Parameters:**
- `origin` (required): Origin airport code (e.g., "JFK", "LAX")
- `destination` (required): Destination airport code (e.g., "LHR", "CDG")
- `departure_date` (required): Departure date in YYYY-MM-DD format
- `return_date` (optional): Return date in YYYY-MM-DD format (for round-trip)
- `passengers` (optional): Number of passengers (default: 1)
- `cabin_class` (optional): Cabin class - economy, premium_economy, business, first (default: economy)

**Example JSON-RPC call:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "search_flights",
    "arguments": {
      "origin": "JFK",
      "destination": "LHR",
      "departure_date": "2024-12-15",
      "return_date": "2024-12-22",
      "passengers": 2,
      "cabin_class": "economy"
    }
  }
}
```

## Integration with MCP Clients

This server can be integrated with any MCP-compatible client. The server communicates via JSON-RPC over stdin/stdout.

## Environment Variables

- `DUFFEL_API_TOKEN` (required): Your Duffel API token

## Error Handling

The server handles various error conditions:
- Missing or invalid API token
- Invalid date formats
- Duffel API errors
- Network connectivity issues

All errors are returned as proper JSON-RPC error responses. 