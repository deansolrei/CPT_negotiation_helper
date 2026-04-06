"""
main.py
-------
FastAPI entry point for the Solrei CPT Negotiation Helper API.

Run with:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    uvicorn backend.main:app --reload

Then open: http://localhost:8000/docs
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.routers import payers, contracts, fee_schedules, dashboard, letters, intermediaries

# Path to the dashboard HTML file (one level up from this file)
DASHBOARD_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard.html")

app = FastAPI(
    title="Solrei CPT Negotiation Helper",
    description=(
        "API for managing payer contracts, fee schedules, and negotiation targets "
        "for Solrei Behavioral Health, Inc."
    ),
    version="0.1.0",
)

# Allow all local origins (file://, localhost ports for dev tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(payers.router)
app.include_router(contracts.router)
app.include_router(fee_schedules.router)
app.include_router(dashboard.router)
app.include_router(letters.router)
app.include_router(intermediaries.router)


@app.get("/dashboard", tags=["Dashboard"], include_in_schema=False)
def serve_dashboard():
    """Serve the negotiation dashboard HTML file."""
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


@app.get("/", tags=["Health"])
def root():
    """Health check — confirms the API is running."""
    return {
        "status": "ok",
        "app": "Solrei CPT Negotiation Helper",
        "version": "0.1.0",
        "dashboard": "/dashboard",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """Detailed health check including database connectivity."""
    from backend.database import get_db
    try:
        with get_db() as cur:
            cur.execute("SELECT COUNT(*) AS payer_count FROM payers")
            result = cur.fetchone()
        return {
            "status": "ok",
            "database": "connected",
            "payer_count": result["payer_count"],
        }
    except Exception as e:
        return {"status": "error", "database": "disconnected", "detail": str(e)}
