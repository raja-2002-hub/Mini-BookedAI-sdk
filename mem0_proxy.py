from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("graph/.env")

from mem0 import MemoryClient

app = FastAPI()

MEM0_API_KEY = os.getenv("MEM0_API_KEY")
MEM0_NAMESPACE = os.getenv("MEM0_NAMESPACE", "bookedai")

# Only create client if API key is available
client = None
if MEM0_API_KEY:
    client = MemoryClient(api_key=MEM0_API_KEY)

class AddRequest(BaseModel):
    messages: List[dict]
    user_id: Optional[str] = None
    custom_categories: Optional[List[dict]] = None

class SearchRequest(BaseModel):
    query: str
    user_id: Optional[str] = None

@app.post("/mem0/add")
def add_memory(req: AddRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Mem0 API key not configured")
    try:
        result = client.add(
            req.messages, 
            user_id=req.user_id or MEM0_NAMESPACE,
            custom_categories=req.custom_categories,
            output_format="v1.1"
        )
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mem0/search")
def search_memory(req: SearchRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Mem0 API key not configured")
    try:
        result = client.search(req.query, user_id=req.user_id or MEM0_NAMESPACE)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy", "mem0_configured": bool(MEM0_API_KEY)} 