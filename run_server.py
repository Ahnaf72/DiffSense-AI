#!/usr/bin/env python3
"""
Run DiffSense-AI Server
This script properly sets up the Python path and starts the server.
"""
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Change to the project root so relative paths work
os.chdir(project_root)

# Now import and run uvicorn
if __name__ == "__main__":
    import uvicorn
    print(f"Starting DiffSense-AI server...")
    print(f"Project root: {project_root}")
    print(f"Working directory: {os.getcwd()}")
    print("-" * 60)

    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )
