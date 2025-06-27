use std::env;
use std::collections::HashMap;
use std::convert::Infallible;

use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tracing::{error, info};
use warp::Filter;

#[derive(Debug, Serialize, Deserialize)]
struct FlightSearchRequest {
    origin: String,
    destination: String,
    departure_date: String,
    return_date: Option<String>,
    passengers: Option<i32>,
    cabin_class: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct FlightOffer {
    id: String,
    price: String,
    currency: String,
    departure_time: String,
    arrival_time: String,
    duration: String,
    airline: String,
    flight_number: String,
    aircraft: Option<String>,
    stops: i32,
}

#[derive(Debug, Serialize, Deserialize)]
struct FlightSearchResponse {
    offers: Vec<FlightOffer>,
    total_results: i32,
    search_id: String,
}

#[derive(Debug, Clone)]
struct DuffelFlightServer {
    api_token: String,
    client: reqwest::Client,
}

impl DuffelFlightServer {
    fn new() -> Result<Self> {
        let api_token = env::var("DUFFEL_API_TOKEN")
            .map_err(|_| anyhow::anyhow!("DUFFEL_API_TOKEN environment variable must be set"))?;

        let client = reqwest::Client::new();

        Ok(Self { api_token, client })
    }

    async fn search_flights(&self, request: FlightSearchRequest) -> Result<FlightSearchResponse> {
        // Prepare the request payload for Duffel API
        let mut passengers = Vec::new();
        let passenger_count = request.passengers.unwrap_or(1);
        
        for _ in 0..passenger_count {
            passengers.push(json!({
                "type": "adult"
            }));
        }

        let mut slices = vec![json!({
            "origin": request.origin,
            "destination": request.destination,
            "departure_date": request.departure_date
        })];

        // Add return slice if return_date is provided
        if let Some(return_date) = &request.return_date {
            slices.push(json!({
                "origin": request.destination,
                "destination": request.origin,
                "departure_date": return_date
            }));
        }

        let payload = json!({
            "data": {
                "slices": slices,
                "passengers": passengers,
                "cabin_class": request.cabin_class.unwrap_or_else(|| "economy".to_string())
            }
        });

        info!("Searching flights with payload: {}", serde_json::to_string_pretty(&payload)?);

        // Make the API request
        let response = self
            .client
            .post("https://api.duffel.com/air/offer_requests")
            .header("Authorization", format!("Bearer {}", self.api_token))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .header("Duffel-Version", "v2")
            .json(&payload)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(anyhow::anyhow!("Duffel API error: {}", error_text));
        }

        let response_data: Value = response.json().await?;
        
        // Extract offer request ID
        let offer_request_id = response_data["data"]["id"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("No offer request ID in response"))?;

        // Fetch the actual offers
        let offers_response = self
            .client
            .get(&format!("https://api.duffel.com/air/offers?offer_request_id={}", offer_request_id))
            .header("Authorization", format!("Bearer {}", self.api_token))
            .header("Accept", "application/json")
            .header("Duffel-Version", "v2")
            .send()
            .await?;

        if !offers_response.status().is_success() {
            let error_text = offers_response.text().await?;
            return Err(anyhow::anyhow!("Duffel offers API error: {}", error_text));
        }

        let offers_data: Value = offers_response.json().await?;
        let offers_array = offers_data["data"]
            .as_array()
            .ok_or_else(|| anyhow::anyhow!("No offers data in response"))?;

        // Parse offers into our format
        let mut flight_offers = Vec::new();
        
        for offer in offers_array.iter().take(10) { // Limit to 10 results
            if let Some(flight_offer) = self.parse_flight_offer(offer) {
                flight_offers.push(flight_offer);
            }
        }

        Ok(FlightSearchResponse {
            offers: flight_offers,
            total_results: offers_array.len() as i32,
            search_id: offer_request_id.to_string(),
        })
    }

    fn parse_flight_offer(&self, offer: &Value) -> Option<FlightOffer> {
        let id = offer["id"].as_str()?.to_string();
        let total_amount = offer["total_amount"].as_str()?.to_string();
        let currency = offer["total_currency"].as_str()?.to_string();
        
        // Get the first slice for departure info
        let slices = offer["slices"].as_array()?;
        let first_slice = &slices[0];
        let segments = first_slice["segments"].as_array()?;
        let first_segment = &segments[0];
        
        let departure_time = first_segment["departing_at"].as_str()?.to_string();
        let arrival_time = first_segment["arriving_at"].as_str()?.to_string();
        let duration = first_slice["duration"].as_str()?.to_string();
        
        // Get airline info
        let marketing_carrier = &first_segment["marketing_carrier"];
        let airline = marketing_carrier["name"].as_str()?.to_string();
        let flight_number = first_segment["marketing_carrier_flight_number"].as_str()?.to_string();
        
        let aircraft = first_segment["aircraft"]["name"].as_str().map(|s| s.to_string());
        let stops = segments.len() as i32 - 1; // Number of segments minus 1 = number of stops

        Some(FlightOffer {
            id,
            price: total_amount,
            currency,
            departure_time,
            arrival_time,
            duration,
            airline,
            flight_number,
            aircraft,
            stops,
        })
    }

    fn format_flight_results(&self, response: &FlightSearchResponse) -> String {
        if response.offers.is_empty() {
            return "No flights found for the specified criteria.".to_string();
        }

        let mut result = format!("Found {} flight offers:\n\n", response.total_results);
        
        for (i, offer) in response.offers.iter().enumerate() {
            result.push_str(&format!(
                "{}. {} {} - {} {}\n",
                i + 1,
                offer.airline,
                offer.flight_number,
                offer.price,
                offer.currency
            ));
            
            result.push_str(&format!(
                "   Departure: {}\n",
                offer.departure_time
            ));
            
            result.push_str(&format!(
                "   Arrival: {}\n",
                offer.arrival_time
            ));
            
            result.push_str(&format!(
                "   Duration: {}\n",
                offer.duration
            ));
            
            if offer.stops > 0 {
                result.push_str(&format!(
                    "   Stops: {}\n",
                    offer.stops
                ));
            } else {
                result.push_str("   Direct flight\n");
            }
            
            if let Some(aircraft) = &offer.aircraft {
                result.push_str(&format!(
                    "   Aircraft: {}\n",
                    aircraft
                ));
            }
            
            result.push_str("\n");
        }

        result.push_str(&format!("Search ID: {}", response.search_id));
        result
    }
}

async fn handle_mcp_request(
    server: DuffelFlightServer,
    request: Value,
) -> Result<impl warp::Reply, Infallible> {
    let response = handle_request(&server, request).await;
    Ok(warp::reply::json(&response))
}

async fn handle_request(server: &DuffelFlightServer, request: Value) -> Value {
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
                        "name": "duffel-flights-mcp",
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
                            "name": "search_flights",
                            "description": "Search for flights using the Duffel API",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "origin": {
                                        "type": "string",
                                        "description": "Origin airport code (e.g., 'JFK', 'LAX')"
                                    },
                                    "destination": {
                                        "type": "string", 
                                        "description": "Destination airport code (e.g., 'LHR', 'CDG')"
                                    },
                                    "departure_date": {
                                        "type": "string",
                                        "description": "Departure date in YYYY-MM-DD format"
                                    },
                                    "return_date": {
                                        "type": "string",
                                        "description": "Return date in YYYY-MM-DD format (optional, for round-trip)"
                                    },
                                    "passengers": {
                                        "type": "integer",
                                        "description": "Number of passengers (default: 1)"
                                    },
                                    "cabin_class": {
                                        "type": "string",
                                        "description": "Cabin class: economy, premium_economy, business, first (default: economy)"
                                    }
                                },
                                "required": ["origin", "destination", "departure_date"]
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
                "search_flights" => {
                    match serde_json::from_value::<FlightSearchRequest>(arguments.clone()) {
                        Ok(search_request) => {
                            match server.search_flights(search_request).await {
                                Ok(search_response) => {
                                    let formatted_results = server.format_flight_results(&search_response);
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
                                    error!("Flight search error: {}", e);
                                    json!({
                                        "jsonrpc": "2.0",
                                        "error": {
                                            "code": -32000,
                                            "message": format!("Flight search failed: {}", e)
                                        },
                                        "id": id
                                    })
                                }
                            }
                        }
                        Err(e) => {
                            error!("Invalid arguments for search_flights: {}", e);
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
    info!("Starting Duffel Flights MCP HTTP Server");

    // Initialize the server
    let server = DuffelFlightServer::new()?;
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
                "service": "duffel-flights-mcp",
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
                "service": "Duffel Flights MCP Server",
                "version": "0.1.0",
                "endpoints": {
                    "health": "GET /health",
                    "mcp": "POST /mcp"
                },
                "tools": ["search_flights"]
            }))
        });

    let routes = health
        .or(mcp)
        .or(root)
        .with(cors)
        .with(warp::log("duffel_flights"));

    let port = env::var("PORT")
        .unwrap_or_else(|_| "3001".to_string())
        .parse::<u16>()
        .unwrap_or(3001);

    info!("Server starting on http://localhost:{}", port);
    info!("MCP endpoint: http://localhost:{}/mcp", port);
    info!("Health check: http://localhost:{}/health", port);

    warp::serve(routes)
        .run(([127, 0, 0, 1], port))
        .await;

    Ok(())
} 