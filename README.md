# upscale-video-2k-to-4k-collab

Windows CLI client + Google Colab backend for upscaling 720p video to 4K using Video2X 6.4.0.

## Quick start

### 1. Colab backend
1. Open `colab/Video2X_Colab.ipynb` in Google Colab.
2. Set runtime to GPU (T4/L4/A100).
3. Add secrets `NGROK_TOKEN` and `API_TOKEN`.
4. Run all cells. Copy the printed Backend URL + token.

### 2. Windows client
1. Put videos in `client/input/`.
2. Run `client/start.bat`.
3. Paste the Backend URL and token when prompted.
4. Outputs land in `client/output/`.

## Profiles
- `quality` (default): Real-ESRGAN x4 + ffmpeg downscale to 4K (best for live action).
- `anime`: realesr-animevideov3 x3 (exact 4K, one pass).
- `fast`: libplacebo Anime4K (exact 4K, fastest).

## Run tests
Backend:
```
cd backend
python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest -q
```
Smoke:
```
python scripts/smoke_local.py
```
