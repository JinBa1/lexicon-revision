from fastapi import FastAPI

app = FastAPI(title="RAG Exam Revision Tool")


@app.get("/")
async def root():
    return {"message": "Backend is running. Add your endpoints here."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
