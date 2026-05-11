from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import routes
import os

app = FastAPI(title="Immigration Translation Tool")

app.include_router(routes.router, prefix="/api")

static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def root():
    return {"message": "Immigration Translation Tool"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
