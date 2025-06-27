use std::env;
use std::convert::Infallible;

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tracing::{error, info};
use warp::Filter;

#[derive(Debug, Serialize, Deserialize)]
struct StaySearchRequest {
    location: String,
    check_in_date: String,
    check_out_date: String,
    adults: Option<i32>,
    children: Option<i32>,
    rooms: Option<i32>,
}

#[derive(Debug, Serialize, Deserialize)]
struct StayOffer {
    id: String,
    hotel_name: String,
    hotel_rating: Option<f64>,
    location: String,
    total_amount: String,
    currency: String,
    check_in_date: String,
    check_out_date: String,
    room_type: Option<String>,
    amenities: Vec<String>,
    cancellation_policy: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct StaySearchResponse {
    offers: Vec<StayOffer>,
    total_results: i32,
    search_id: String,
    location_searched: String,
}

#[derive(Debug, Clone)]
struct DuffelStayServer {
    api_token: String,
    client: reqwest::Client,
}

impl DuffelStayServer {
    fn new() -> Result<Self> {
        let api_token = env::var("DUFFEL_API_TOKEN")
            .map_err(|_| anyhow::anyhow!("DUFFEL_API_TOKEN environment variable must be set"))?;

        let client = reqwest::Client::new();

        Ok(Self { api_token, client })
    }

    async fn search_stays(&self, request: StaySearchRequest) -> Result<StaySearchResponse> {
        info!("Searching stays for location: {}", request.location);
        
        // First, get coordinates for the location using a simple geocoding approach
        let coordinates = self.geocode_location(&request.location).await?;
        
        // Prepare guests array - Duffel expects guests as an array of objects
        let mut guests = Vec::new();
        let adults = request.adults.unwrap_or(1);
        let children = request.children.unwrap_or(0);
        
        for _ in 0..adults {
            guests.push(json!({"type": "adult"}));
        }
        for _ in 0..children {
            guests.push(json!({"type": "child"}));
        }

        // Prepare the request payload for Duffel Stays API
        let payload = json!({
            "data": {
                "location": {
                    "radius": 10, // 10km radius
                    "geographic_coordinates": {
                        "latitude": coordinates.0,
                        "longitude": coordinates.1
                    }
                },
                "check_in_date": request.check_in_date,
                "check_out_date": request.check_out_date,
                "guests": guests,
                "rooms": request.rooms.unwrap_or(1)
            }
        });

        info!("Searching stays with payload: {}", serde_json::to_string_pretty(&payload)?);

        // Use the actual Duffel Stays API endpoint
        let response = self
            .client
            .post("https://api.duffel.com/stays/search")
            .header("Authorization", format!("Bearer {}", self.api_token))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .header("Duffel-Version", "v2")
            .json(&payload)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(anyhow::anyhow!("Duffel Stays API error: {}", error_text));
        }

        let response_data: Value = response.json().await?;
        
        // Debug: Log the actual response structure (first 1000 chars to avoid too much output)
        let response_str = serde_json::to_string_pretty(&response_data)?;
        let truncated = if response_str.len() > 1000 { &response_str[..1000] } else { &response_str };
        info!("Raw Duffel response (truncated): {}", truncated);
        
        // Parse the actual Duffel response
        self.parse_duffel_stays_response(response_data, &request).await
    }

    async fn geocode_location(&self, location: &str) -> Result<(f64, f64)> {
        // Simple geocoding for major cities - in production, use a proper geocoding service
        let coordinates = match location.to_lowercase().as_str() {
            "new york" | "nyc" => (40.7128, -74.0060),
            "london" => (51.5074, -0.1278),
            "paris" => (48.8566, 2.3522),
            "tokyo" => (35.6762, 139.6503),
            "sydney" => (-33.8688, 151.2093),
            "los angeles" | "la" => (34.0522, -118.2437),
            "chicago" => (41.8781, -87.6298),
            "melbourne" => (-37.8136, 144.9631),
            "dubai" => (25.2048, 55.2708),
            "singapore" => (1.3521, 103.8198),
            "miami" => (25.7617, -80.1918),
            "san francisco" => (37.7749, -122.4194),
            "las vegas" => (36.1699, -115.1398),
            "toronto" => (43.6532, -79.3832),
            "berlin" => (52.5200, 13.4050),
            "rome" => (41.9028, 12.4964),
            "madrid" => (40.4168, -3.7038),
            "amsterdam" => (52.3676, 4.9041),
            "barcelona" => (41.3851, 2.1734),
            _ => {
                // Default to London if location not found
                info!("Location '{}' not found in geocoding, defaulting to London", location);
                (51.5074, -0.1278)
            }
        };
        Ok(coordinates)
    }

    async fn parse_duffel_stays_response(&self, response_data: Value, request: &StaySearchRequest) -> Result<StaySearchResponse> {
        // Debug: Log the response structure to understand the format
        info!("Parsing response with top-level keys: {:?}", response_data.as_object().map(|o| o.keys().collect::<Vec<_>>()));
        
        if let Some(data) = response_data.get("data") {
            info!("Data section keys: {:?}", data.as_object().map(|o| o.keys().collect::<Vec<_>>()));
            info!("Data section is_array: {}, is_object: {}", data.is_array(), data.is_object());
            
            if data.is_array() {
                info!("Data is an array with {} items", data.as_array().unwrap().len());
            }
            if data.is_object() {
                info!("Data is an object");
                if let Some(search_results) = data.get("search_results") {
                    info!("Found search_results, type: {:?}", search_results);
                    if search_results.is_array() {
                        info!("search_results is array with {} items", search_results.as_array().unwrap().len());
                    }
                }
            }
        }
        
        // Extract search results from the response
        let search_results = response_data
            .get("data")
            .and_then(|data| data.get("results"))
            .and_then(|results| results.as_array())
            .ok_or_else(|| {
                error!("Could not find results array in response");
                anyhow::anyhow!("No search results found in API response")
            })?;

        let mut offers = Vec::new();
        
        for result in search_results.iter().take(10) { // Limit to 10 results
            if let Some(stay_offer) = self.parse_stay_result(result, request) {
                offers.push(stay_offer);
            }
        }

        Ok(StaySearchResponse {
            offers,
            total_results: search_results.len() as i32,
            search_id: response_data["meta"]["request_id"]
                .as_str()
                .unwrap_or("unknown")
                .to_string(),
            location_searched: request.location.clone(),
        })
    }

    fn parse_stay_result(&self, result: &Value, request: &StaySearchRequest) -> Option<StayOffer> {
        let accommodation = &result["accommodation"];
        
        let id = result["id"].as_str()?.to_string();
        let hotel_name = accommodation["name"].as_str()?.to_string();
        let hotel_rating = accommodation["rating"].as_f64();
        
        // Get location info from accommodation.location.address.city_name
        let location_name = accommodation["location"]["address"]["city_name"].as_str()
            .unwrap_or(&request.location)
            .to_string();
        
        // Get cheapest rate from root level fields
        let total_amount = result["cheapest_rate_total_amount"].as_str()
            .unwrap_or("0.00")
            .to_string();
        let currency = result["cheapest_rate_currency"].as_str()
            .unwrap_or("USD")
            .to_string();
        
        // Get amenities - they have description field instead of name
        let amenities = accommodation["amenities"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|a| a["description"].as_str())
                    .map(|s| s.to_string())
                    .collect()
            })
            .unwrap_or_else(|| vec!["WiFi".to_string()]);

        Some(StayOffer {
            id,
            hotel_name,
            hotel_rating,
            location: location_name,
            total_amount,
            currency,
            check_in_date: request.check_in_date.clone(),
            check_out_date: request.check_out_date.clone(),
            room_type: None, // Room details not available in this response
            amenities,
            cancellation_policy: None, // Cancellation policy not available in this response
        })
    }

    fn format_stay_results(&self, response: &StaySearchResponse) -> String {
        if response.offers.is_empty() {
            return format!("No hotels found in {} for the specified dates.", response.location_searched);
        }

        let mut result = format!("Found {} hotel offers in {}:\n\n", response.total_results, response.location_searched);
        
        for (i, offer) in response.offers.iter().enumerate() {
            result.push_str(&format!(
                "{}. {} - {} {}\n",
                i + 1,
                offer.hotel_name,
                offer.total_amount,
                offer.currency
            ));
            
            if let Some(rating) = offer.hotel_rating {
                result.push_str(&format!(
                    "   Rating: {:.1}/5.0 stars\n",
                    rating
                ));
            }
            
            result.push_str(&format!(
                "   Location: {}\n",
                offer.location
            ));
            
            result.push_str(&format!(
                "   Check-in: {} | Check-out: {}\n",
                offer.check_in_date,
                offer.check_out_date
            ));
            
            if let Some(room_type) = &offer.room_type {
                result.push_str(&format!(
                    "   Room: {}\n",
                    room_type
                ));
            }
            
            if !offer.amenities.is_empty() {
                result.push_str(&format!(
                    "   Amenities: {}\n",
                    offer.amenities.join(", ")
                ));
            }
            
            if let Some(policy) = &offer.cancellation_policy {
                result.push_str(&format!(
                    "   Cancellation: {}\n",
                    policy
                ));
            }
            
            result.push_str("\n");
        }

        result.push_str(&format!("Search ID: {}", response.search_id));
        result
    }
}

async fn handle_mcp_request(
    server: DuffelStayServer,
    request: Value,
) -> Result<impl warp::Reply, Infallible> {
    let response = handle_request(&server, request).await;
    Ok(warp::reply::json(&response))
}

async fn handle_request(server: &DuffelStayServer, request: Value) -> Value {
    let method = request["method"].as_str().unwrap_or("");
    let id = request["id"].clone();

    match method {
        "initialize" => {
            json!({
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "duffel-stays-mcp",
                        "version": "0.1.0"
                    }
                },
                "id": id
            })
        }
        "tools/list" => {
            json!({
                "jsonrpc": "2.0",
                "result": {
                    "tools": [
                        {
                            "name": "search_stays",
                            "description": "Search for hotels and accommodations using the Duffel API",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "Location/city to search for hotels (e.g., 'New York', 'Paris', 'Tokyo')"
                                    },
                                    "check_in_date": {
                                        "type": "string",
                                        "description": "Check-in date in YYYY-MM-DD format"
                                    },
                                    "check_out_date": {
                                        "type": "string",
                                        "description": "Check-out date in YYYY-MM-DD format"
                                    },
                                    "adults": {
                                        "type": "integer",
                                        "description": "Number of adult guests (default: 1)"
                                    },
                                    "children": {
                                        "type": "integer",
                                        "description": "Number of child guests (default: 0)"
                                    },
                                    "rooms": {
                                        "type": "integer",
                                        "description": "Number of rooms needed (default: 1)"
                                    }
                                },
                                "required": ["location", "check_in_date", "check_out_date"]
                            }
                        }
                    ]
                },
                "id": id
            })
        }
        "tools/call" => {
            let params = &request["params"];
            let tool_name = params["name"].as_str().unwrap_or("");
            let arguments = &params["arguments"];

            match tool_name {
                "search_stays" => {
                    match serde_json::from_value::<StaySearchRequest>(arguments.clone()) {
                        Ok(search_request) => {
                            match server.search_stays(search_request).await {
                                Ok(search_response) => {
                                    let formatted_results = server.format_stay_results(&search_response);
                                    json!({
                                        "jsonrpc": "2.0",
                                        "result": {
                                            "content": [
                                                {
                                                    "type": "text",
                                                    "text": formatted_results
                                                }
                                            ]
                                        },
                                        "id": id
                                    })
                                }
                                Err(e) => {
                                    error!("Stay search error: {}", e);
                                    json!({
                                        "jsonrpc": "2.0",
                                        "error": {
                                            "code": -32000,
                                            "message": format!("Stay search failed: {}", e)
                                        },
                                        "id": id
                                    })
                                }
                            }
                        }
                        Err(e) => {
                            error!("Invalid arguments for search_stays: {}", e);
                            json!({
                                "jsonrpc": "2.0",
                                "error": {
                                    "code": -32602,
                                    "message": format!("Invalid parameters: {}", e)
                                },
                                "id": id
                            })
                        }
                    }
                }
                _ => {
                    json!({
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32601,
                            "message": "Method not found"
                        },
                        "id": id
                    })
                }
            }
        }
        _ => {
            json!({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": "Method not found"
                },
                "id": id
            })
        }
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    tracing_subscriber::fmt::init();
    info!("Starting Duffel Stays MCP HTTP Server");

    // Initialize the server
    let server = DuffelStayServer::new()?;
    info!("Duffel API token loaded successfully");

    // Create CORS configuration
    let cors = warp::cors()
        .allow_any_origin()
        .allow_headers(vec!["content-type"])
        .allow_methods(vec!["GET", "POST", "OPTIONS"]);

    // Health check endpoint
    let health = warp::path("health")
        .and(warp::get())
        .map(|| {
            warp::reply::json(&json!({
                "status": "healthy",
                "service": "duffel-stays-mcp",
                "version": "0.1.0"
            }))
        });

    // MCP endpoint
    let server_clone = server.clone();
    let mcp = warp::path("mcp")
        .and(warp::post())
        .and(warp::body::json())
        .and_then(move |request: Value| {
            let server = server_clone.clone();
            async move {
                handle_mcp_request(server, request).await
            }
        });

    // Root endpoint with info
    let root = warp::path::end()
        .and(warp::get())
        .map(|| {
            warp::reply::json(&json!({
                "service": "Duffel Stays MCP Server",
                "version": "0.1.0",
                "endpoints": {
                    "health": "GET /health",
                    "mcp": "POST /mcp"
                },
                "tools": ["search_stays"]
            }))
        });

    let routes = health
        .or(mcp)
        .or(root)
        .with(cors)
        .with(warp::log("duffel_stays"));

    let port = env::var("PORT")
        .unwrap_or_else(|_| "3002".to_string())
        .parse::<u16>()
        .unwrap_or(3002);

    info!("Server starting on http://localhost:{}", port);
    info!("MCP endpoint: http://localhost:{}/mcp", port);
    info!("Health check: http://localhost:{}/health", port);

    warp::serve(routes)
        .run(([127, 0, 0, 1], port))
        .await;

    Ok(())
} 