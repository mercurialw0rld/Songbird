
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent / ".env")

from retrieval import recommend_songs_payload  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Songbird", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    google_api_key: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional; overrides GOOGLE_API_KEY from the environment.",
    )
    cohere_api_key: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional; overrides COHERE_API_KEY from the environment.",
    )
    popularity_mode: str = Field(
        default="any",
        description="Popularity filter: any | known | unknown",
    )
    popularity_threshold: int = Field(
        default=60,
        ge=0,
        le=100,
        description="Threshold used by popularity_mode (0..100).",
    )


@app.post("/api/recommend")
def api_recommend(body: RecommendRequest):
    try:
        return recommend_songs_payload(
            body.query.strip(),
            google_api_key=(body.google_api_key or "").strip() or None,
            cohere_api_key=(body.cohere_api_key or "").strip() or None,
            popularity_mode=(body.popularity_mode or "any").strip().lower(),
            popularity_threshold=body.popularity_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/")
def serve_index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
