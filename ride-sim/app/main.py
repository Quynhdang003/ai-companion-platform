from fastapi import FastAPI

app = FastAPI(title="Ride Simulator")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
