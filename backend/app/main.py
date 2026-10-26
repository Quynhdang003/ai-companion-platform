from fastapi import FastAPI

app = FastAPI(title="AI Companion Backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
