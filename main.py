from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import routes
import os
from pathlib import Path

app = FastAPI(title="Immigration Translation Tool")

app.include_router(routes.router, prefix="/api")

static_path = Path(__file__).parent.parent / "static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def root():
    return {"message": "Immigration Translation Tool"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
