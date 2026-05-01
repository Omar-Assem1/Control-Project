"""
main.py
-------
Entry point for the Signal Flow Graph Analyzer API.

Run with:
    uvicorn main:app --reload --port 8000
"""

from app import app  # noqa: F401  – re-exported so uvicorn can find it

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
