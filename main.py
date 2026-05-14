from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes
import os
from pathlib import Path

app = FastAPI(title="Immigration Translation Tool")

# Allow cross-origin requests (e.g. from Open Design preview)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")

static_path = Path(__file__).parent / "static"
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def root():
    index = static_path / "index.html"
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Immigration Translation Tool"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
