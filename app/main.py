from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
import os

from .qa import QASystem


def create_app() -> FastAPI:
    app = FastAPI(
        title="Member Memory QA",
        version="0.2.0",
        description="LLM memory agent over member messages for a luxury booking platform.",
    )

    messages_base = os.getenv(
        "MESSAGES_API_BASE", "https://november7-730026606190.europe-west1.run.app"
    )
    qa = QASystem(messages_api_base=messages_base)

    @app.get("/healthz")
    async def health() -> dict:
        return {"ok": True}

    @app.get("/ask")
    async def ask(question: str = Query(..., min_length=3)) -> JSONResponse:
        try:
            answer = await qa.answer(question)
            return JSONResponse({"answer": answer})
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to answer the question")

    return app


app = create_app()

