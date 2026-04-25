# 🎬 Xiaoyunque / Pippit Watermark Remover API

A FastAPI-based service that removes watermarks from **Xiaoyunque (Pippit)** AI-generated videos using FFmpeg.

> ⚠️ This tool is intended for **personal use only**. Please respect copyright and the platform's terms of service.

---

## ✨ Features

- Accepts video file uploads via multipart form
- Automatically crops the bottom watermark (~60px)
- Blurs the top-left "AI生成" badge (200x80px region)
- Background job processing with polling support
- Auto-cleanup of temp files after 15 minutes
- Concurrent job limiting via semaphore (max 2 simultaneous jobs)

---

## 🖥️ Requirements

- Python 3.10+
- FFmpeg installed on the system
- Linux recommended (Ubuntu 22.04+)

---

## 📦 Installation

**1. Clone the repository**
```bash
git clone https://github.com/chenwenhe12/xiaoyunque-downloader.git
cd xiaoyunque-downloader
```

**2. Install Python dependencies**
```bash
pip3 install -r requirements.txt
```

**3. Install FFmpeg**
```bash
# Ubuntu / Debian
apt install ffmpeg -y

# Verify
ffmpeg -version | head -1
```

---

## 🚀 Running the API

```bash
uvicorn pippit_api:app --host 0.0.0.0 --port 8002
```

Run in background:
```bash
nohup uvicorn pippit_api:app --host 0.0.0.0 --port 8002 &
```

---

## 📡 API Endpoints

### `GET /pippit`
Health check.

**Response:**
```json
{
  "status": "ok",
  "service": "Pippit Watermark Remover (FFmpeg crop)",
  "waiting": 0
}
```

---

### `POST /pippit/upload-and-crop`
Upload a video file → remove watermark → return job ID.

**Request:** `multipart/form-data`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file` | File | required | MP4 video file |
| `crop_bottom` | int | 60 | Pixels to crop from bottom |
| `crop_top` | int | 0 | Pixels to crop from top |
| `crop_left` | int | 0 | Pixels to crop from left |
| `crop_right` | int | 0 | Pixels to crop from right |

**Response:**
```json
{
  "job_id": "uuid-here",
  "status": "pending",
  "size_bytes": 5242880
}
```

---

### `GET /pippit/job/{job_id}`
Poll job status.

**Response:**
```json
{
  "job_id": "uuid-here",
  "status": "done",
  "download_url": "/pippit/download/uuid-here",
  "error": null
}
```

**Status values:** `pending` → `processing` → `done` / `failed`

---

### `GET /pippit/download/{job_id}`
Download the processed video (no watermark).

Returns `video/mp4` file as attachment.

---

### `GET /pippit/status`
View server queue status.

**Response:**
```json
{
  "total_jobs": 3,
  "waiting": 1,
  "by_status": {
    "done": 2,
    "processing": 1
  }
}
```

---

## 🔄 Typical Flow

```
Client uploads video file
        ↓
POST /pippit/upload-and-crop
        ↓
Receive job_id (status: pending)
        ↓
Poll GET /pippit/job/{job_id} every 3s
        ↓
status = "done"
        ↓
GET /pippit/download/{job_id}
        ↓
Download clean MP4 (no watermark)
```

---

## 🧪 Quick Test

```bash
# Health check
curl http://localhost:8002/pippit

# Upload and process a video
curl -X POST http://localhost:8002/pippit/upload-and-crop \
  -F "file=@your_video.mp4" \
  -F "crop_bottom=60"

# Poll job status (replace JOB_ID)
curl http://localhost:8002/pippit/job/JOB_ID

# Download result
curl -o output.mp4 http://localhost:8002/pippit/download/JOB_ID
```

---

## ⚙️ Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `crop_bottom` | 60px | Bottom watermark crop |
| blur region | 200x80px top-left | "AI生成" badge blur (sigma=25) |
| Max file size | 200MB | Upload limit |
| Semaphore | 2 | Max concurrent jobs |
| Cleanup delay | 900s | Auto-delete processed files |
| FFmpeg preset | ultrafast | Encoding speed/size tradeoff |
| FFmpeg CRF | 20 | Quality (lower = better) |

---

## 📋 Integration with PHP (savevideoraw.com style)

This API is designed to work alongside a PHP proxy that:
1. Parses the Xiaoyunque share link
2. Downloads the video from CDN (bypassing IP restrictions)
3. Uploads to this API for watermark removal
4. Proxies the download back to the user

See `api_pippit.php` for the PHP integration example.

---

## 📄 License

For personal and educational use only. Not affiliated with Xiaoyunque, Pippit, or ByteDance.
