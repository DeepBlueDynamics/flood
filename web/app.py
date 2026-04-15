"""FastAPI web application for Veo Studio."""

import asyncio
import json
import os
import threading
import time
import uuid

from fastapi import FastAPI, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core import veo

app = FastAPI(title="Veo Studio")

os.makedirs("output/jobs", exist_ok=True)


# ---------------------------------------------------------------------------
# Job store (in-memory — single-process, concurrency-1 design)
# ---------------------------------------------------------------------------

class Job:
    def __init__(self, job_id, mode):
        self.id = job_id
        self.mode = mode
        self.status = "running"
        self.progress = 0.0
        self.message = ""
        self.result_path = None
        self.error = None
        self.created_at = time.time()
        self.queue = asyncio.Queue()

    def to_dict(self):
        return {
            "id": self.id,
            "mode": self.mode,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result_path": self.result_path,
            "error": self.error,
        }


jobs: dict[str, Job] = {}


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def _push(job, event, loop):
    """Thread-safe push to job's async queue."""
    asyncio.run_coroutine_threadsafe(job.queue.put(event), loop)


def _run_job(job, mode, prompt, segments, source_path, work_dir, loop):
    def progress_cb(event):
        job.message = event.get("message", job.message)
        if event.get("type") == "segment_complete":
            job.progress = event["segment"] / event["total"]
        _push(job, event, loop)

    try:
        output_file = os.path.join(work_dir, "output.mp4")

        if mode == "generate":
            veo.generate_video(prompt, output_file, progress_cb=progress_cb)
        elif mode == "loop":
            veo.create_loop(prompt, output_file,
                            progress_cb=progress_cb, work_dir=work_dir)
        elif mode == "chain":
            veo.chain_videos(prompt, segments, output_file,
                             progress_cb=progress_cb, work_dir=work_dir)
        elif mode == "extend":
            prompts = [p.strip() for p in prompt.strip().splitlines() if p.strip()]
            veo.extend_video(source_path, prompts, output_file,
                             progress_cb=progress_cb, work_dir=work_dir)

        job.status = "complete"
        job.progress = 1.0
        job.result_path = f"/output/jobs/{job.id}/output.mp4"
        _push(job, {"type": "complete", "path": job.result_path,
                     "message": "Done!"}, loop)

    except Exception as e:
        job.status = "error"
        job.error = str(e)
        _push(job, {"type": "error", "message": str(e)}, loop)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.post("/api/jobs")
async def create_job(
    mode: str = Form(...),
    prompt: str = Form(...),
    segments: int = Form(3),
    source: UploadFile = File(None),
):
    job_id = uuid.uuid4().hex[:8]
    work_dir = os.path.join("output", "jobs", job_id)
    os.makedirs(work_dir, exist_ok=True)

    source_path = None
    if source and source.filename and mode == "extend":
        source_path = os.path.join(work_dir, source.filename)
        with open(source_path, "wb") as f:
            content = await source.read()
            f.write(content)

    job = Job(job_id, mode)
    jobs[job_id] = job

    loop = asyncio.get_running_loop()
    thread = threading.Thread(
        target=_run_job,
        args=(job, mode, prompt, segments, source_path, work_dir, loop),
        daemon=True,
    )
    thread.start()

    return JSONResponse({"job_id": job_id}, status_code=202)


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Not found"}, status_code=404)

    job = jobs[job_id]

    async def stream():
        while True:
            try:
                event = await asyncio.wait_for(job.queue.get(), timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                yield 'data: {"type": "keepalive"}\n\n'

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return jobs[job_id].to_dict()


@app.get("/api/jobs")
async def list_jobs():
    return [j.to_dict() for j in
            sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)]


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path) as f:
        return f.read()


# Static mount last so API routes take priority
app.mount("/output", StaticFiles(directory="output"), name="output")
