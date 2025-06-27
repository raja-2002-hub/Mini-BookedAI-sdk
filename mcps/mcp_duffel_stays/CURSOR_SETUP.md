# Running Duffel Stays MCP HTTP Server

## Prerequisites

1. **Rust installed** (already done)
2. **Duffel API token** in `config.env` (already done)

## Running the HTTP Server

### Step 1: Start the Server

1. **Open Cursor Terminal** (`Ctrl+` ` or `View → Terminal`)

2. **Navigate and run the server**:
   ```bash
   cd ~/repos/mini_bookedai/mcps/mcp_duffel_stays
   source config.env
   source ~/.cargo/env
   cargo run
   ```

3. **The server will start** and show:
   ```
   INFO mcp_duffel_stays: Starting Duffel Stays MCP HTTP Server
   INFO mcp_duffel_stays: Server starting on http://localhost:3002
   INFO mcp_duffel_stays: MCP endpoint: http://localhost:3002/mcp
   INFO mcp_duffel_stays: Health check: http://localhost:3002/health
   ```

### Step 2: Test the Server

1. **Health Check** (in another terminal):
   ```bash
   curl http://localhost:3002/health
   ```

2. **Test MCP Initialize**:
   ```bash
   curl -X POST http://localhost:3002/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
   ```

3. **Test Hotel Search**:
   ```bash
   curl -X POST http://localhost:3002/mcp \
     -H "Content-Type: application/json" \
     -d '{
       "jsonrpc": "2.0",
       "id": 2,
       "method": "tools/call",
       "params": {
         "name": "search_stays",
         "arguments": {
           "location": "New York",
           "check_in_date": "2024-12-15",
           "check_out_date": "2024-12-17",
           "adults": 2,
           "rooms": 1
         }
       }
     }'
   ```

### Step 3: Configure Cursor

Add the server to your `~/.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "duffel-stays": {
      "url": "http://localhost:3002/mcp",
      "enabled": true
    }
  }
}
```

**Restart Cursor** for the configuration to take effect.

## Environment Setup

### Method 1: Using config.env (Current)
```bash
# In mcps/mcp_duffel_stays/config.env
export DUFFEL_API_TOKEN=your_token_here
export RUST_LOG=info
```

### Method 2: Cursor Environment Variables
1. **Open Settings** (`Ctrl+,`)
2. **Search for "terminal env"**
3. **Add to "Terminal › Integrated › Env: Linux"**:
   ```json
   {
     "DUFFEL_API_TOKEN": "your_token_here",
     "RUST_LOG": "info"
   }
   ```

## Usage Workflow

1. **Start the server** in a terminal (Step 1 above)
2. **Leave it running** - the server will handle multiple requests
3. **Cursor will connect** to `http://localhost:3002/mcp` automatically
4. **Ask Cursor** to search for hotels - it will use your server!

## Integration with Your Project

### Using from LangGraph Agent

If you want to call the flight search directly from your Python code:

```python
# In your graph/src/agent/graph.py
import aiohttp
import json

async def call_mcp_hotel_search(location, check_in_date, check_out_date, **kwargs):
    """Call the Rust MCP HTTP server for hotel search"""
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "search_stays",
            "arguments": {
                "location": location,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                **kwargs
            }
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://localhost:3002/mcp",
            json=request,
            headers={"Content-Type": "application/json"}
        ) as response:
            return await response.json()
```

### Cursor Integration

With the HTTP server approach, Cursor automatically handles the connection. Just:
1. **Ask Cursor**: *"Search for hotels in New York from December 15th to 17th for 2 adults"*
2. **Cursor will**: Use your running MCP server to get real hotel data
3. **You get**: Live hotel results with ratings, amenities, and pricing!

## Troubleshooting

### Common Issues

1. **"DUFFEL_API_TOKEN not set"**
   - Ensure `config.env` exists and is sourced
   - Check token is valid at duffel.com

2. **"cargo not found"**
   - Run: `source ~/.cargo/env`
   - Or restart Cursor after Rust installation

3. **Compilation errors**
   - Run: `cargo clean && cargo build`
   - Check Rust version: `rustc --version`

### Logs
- Server logs appear in the terminal where you run `cargo run`
- Set `RUST_LOG=debug` for verbose logging
- Check Duffel API status at their status page

## Next Steps

1. **Test flight search** with real airport codes
2. **Integrate with your AI agent** in the graph module  
3. **Add error handling** for API failures
4. **Configure for production** with proper logging 