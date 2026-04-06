"""
main.py
-------
FastAPI entry point for the Solrei CPT Negotiation Helper API.

Run with:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    uvicorn backend.main:app --reload

Then open: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import payers, contracts, fee_schedules, dashboard

app = FastAPI(
    title="Solrei CPT Negotiation Helper",
    description=(
        "API for managing payer contracts, fee schedules, and negotiation targets "
        "for Solrei Behavioral Health, Inc."
    ),
    version="0.1.0",
)

# Allow local front-end development (React, etc.) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(payers.router)
app.include_router(contracts.router)
app.include_router(fee_schedules.router)
app.include_router(dashboard.router)


@app.get("/", tags=["Health"])
def root():
    """Health check — confirms the API is running."""
    return {
        "status": "ok",
        "app": "Solrei CPT Negotiation Helper",
        "version": "0.1.0",
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
