"""
Pippit Watermark Remover — FFmpeg crop
"""
import os, uuid, asyncio, subprocess, tempfile, shutil, json
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Pippit Watermark Remover")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

TEMP_DIR = tempfile.gettempdir()
_jobs: dict = {}
sem = asyncio.Semaphore(2)
waiting = 0

class CropRequest(BaseModel):
    video_url: str
    crop_bottom: int = 60
    crop_top: int = 0
    crop_left: int = 0
    crop_right: int = 0

def ffmpeg_crop(input_path, output_path, crop_bottom, crop_top, crop_left, crop_right):
    probe = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', input_path
    ], capture_output=True, text=True, timeout=30)
    info = json.loads(probe.stdout)
    vstream = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not vstream:
        raise RuntimeError("No video stream found")
    w = int(vstream['width'])
    h = int(vstream['height'])
    out_w = w - crop_left - crop_right
    out_h = h - crop_top - crop_bottom
    x = crop_left
    y = crop_top
    if out_w <= 0 or out_h <= 0:
        raise RuntimeError(f"Invalid crop: {out_w}x{out_h}")
   
    vf = (
        f'crop={out_w}:{out_h}:{x}:{y},'
        f'split[main][copy];'
        f'[copy]crop=200:80:0:0,gblur=sigma=25[blurred];'
        f'[main][blurred]overlay=0:0'
    )
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-vf', vf,
        '-c:v', 'libx264', '-crf', '20', '-preset', 'ultrafast',
        '-c:a', 'copy', '-pix_fmt', 'yuv420p', output_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {r.stderr[-400:]}")

async def cleanup_later(path, delay=900):
    await asyncio.sleep(delay)
    try: os.remove(path)
    except: pass

async def do_crop_job(job_id, in_path, cb, ct, cl, cr):
    global waiting
    out_path = os.path.join(TEMP_DIR, f"{job_id}_out.mp4")
    try:
        async with sem:
            waiting = max(0, waiting - 1)
            _jobs[job_id]['status'] = 'processing'
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, ffmpeg_crop, in_path, out_path, cb, ct, cl, cr)
            _jobs[job_id].update({
                'status': 'done',
                'out_path': out_path,
                'download_url': f'/pippit/download/{job_id}'
            })
            asyncio.create_task(cleanup_later(out_path, 900))
    except Exception as e:
        _jobs[job_id].update({'status': 'failed', 'error': str(e)})
    finally:
        try: os.remove(in_path)
        except: pass

async def download_video(url, path):
    headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Referer': 'https://www.douyin.com/',
        'Accept': '*/*',
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        async with client.stream('GET', url, headers=headers) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"CDN returned HTTP {r.status_code}")
            with open(path, 'wb') as f:
                async for chunk in r.aiter_bytes(1024 * 1024):
                    f.write(chunk)
    size = os.path.getsize(path)
    if size < 1000:
        raise RuntimeError(f"Downloaded file too small: {size} bytes")

async def process_url_job(job_id, req):
    global waiting
    waiting += 1
    in_path = os.path.join(TEMP_DIR, f"{job_id}_in.mp4")
    try:
        async with sem:
            waiting = max(0, waiting - 1)
            _jobs[job_id]['status'] = 'downloading'
            await download_video(req.video_url, in_path)
            _jobs[job_id]['status'] = 'processing'
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, ffmpeg_crop, in_path,
                os.path.join(TEMP_DIR, f"{job_id}_out.mp4"),
                req.crop_bottom, req.crop_top, req.crop_left, req.crop_right)
            out_path = os.path.join(TEMP_DIR, f"{job_id}_out.mp4")
            _jobs[job_id].update({
                'status': 'done',
                'out_path': out_path,
                'download_url': f'/pippit/download/{job_id}'
            })
            asyncio.create_task(cleanup_later(out_path, 900))
    except Exception as e:
        _jobs[job_id].update({'status': 'failed', 'error': str(e)})
    finally:
        try: os.remove(in_path)
        except: pass

@app.get("/pippit")
def root():
    return {"status": "ok", "service": "Pippit Watermark Remover (FFmpeg crop)", "waiting": waiting}

@app.post("/pippit/crop")
async def crop(req: CropRequest, background_tasks: BackgroundTasks):
    if not req.video_url.startswith('http'):
        raise HTTPException(400, "Invalid video_url")
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {'status': 'pending', 'download_url': None, 'error': None, 'out_path': None}
    background_tasks.add_task(process_url_job, job_id, req)
    return {"job_id": job_id, "status": "pending"}

@app.post("/pippit/upload-and-crop")
async def upload_and_crop(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    crop_bottom: int = 60,
    crop_top: int = 0,
    crop_left: int = 0,
    crop_right: int = 0
):
    job_id  = str(uuid.uuid4())
    in_path = os.path.join(TEMP_DIR, f"{job_id}_in.mp4")

    with open(in_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = os.path.getsize(in_path)
    if size < 1000:
        os.remove(in_path)
        raise HTTPException(400, "File too small or empty")

    _jobs[job_id] = {'status': 'pending', 'download_url': None, 'error': None, 'out_path': None}
    background_tasks.add_task(do_crop_job, job_id, in_path, crop_bottom, crop_top, crop_left, crop_right)
    return {"job_id": job_id, "status": "pending", "size_bytes": size}

@app.get("/pippit/job/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found or expired")
    return {"job_id": job_id, **{k: job[k] for k in ["status","download_url","error"]}}

@app.get("/pippit/download/{job_id}")
def download(job_id: str):
    job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "File not ready or expired")
    path = job.get("out_path")
    if not path or not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(
        path, media_type="video/mp4",
        filename="video_no_watermark.mp4",
        headers={"Content-Disposition": "attachment; filename=video_no_watermark.mp4"}
    )

@app.get("/pippit/status")
def status():
    by_status = {}
    for j in _jobs.values():
        s = j["status"]
        by_status[s] = by_status.get(s, 0) + 1
    return {"total_jobs": len(_jobs), "waiting": waiting, "by_status": by_status}
