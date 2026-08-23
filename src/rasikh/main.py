from fastapi import FastAPI


app = FastAPI(
    title="Rasikh",
    description="AI-powered legal and governance platform",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}