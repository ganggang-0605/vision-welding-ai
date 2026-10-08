from fastapi import FastAPI

from app.api import jobs, workspaces

app = FastAPI(title="Vision Welding AI")
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok"}
