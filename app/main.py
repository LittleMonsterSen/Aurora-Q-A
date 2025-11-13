from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os

from .qa import QASystem


def create_app() -> FastAPI:
    app = FastAPI(
        title="Member Memory QA",
        version="0.2.0",
        description="LLM memory agent over member messages for a luxury booking platform.",
    )

    # CORS (configurable via env)
    allow_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in allow_origins if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    qa = QASystem()

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
        except Exception as e:
            import traceback
            error_detail = str(e)
            print(f"Error answering question: {error_detail}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Failed to answer the question: {error_detail}")

    class AskRequest(BaseModel):
        question: str

    @app.post("/ask")
    async def ask_post(body: AskRequest) -> JSONResponse:
        q = (body.question or "").strip()
        if len(q) < 3:
            raise HTTPException(status_code=422, detail="question must be at least 3 characters")
        try:
            answer = await qa.answer(q)
            print(f"Answer length: {len(answer)} characters")
            return JSONResponse({"answer": answer})
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            error_detail = str(e)
            print(f"Error answering question: {error_detail}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Failed to answer the question: {error_detail}")

    return app


app = create_app()

