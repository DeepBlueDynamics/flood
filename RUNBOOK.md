# Runbook: Veo 3 Video Production Agent

This agent orchestrates **Google Veo 3** to produce high-quality, long-form, and seamless looping video content using the "Nanobanana" frame-continuation technique.

## 🛠 Infrastructure & Dependencies

### 1. Authentication
- **Method:** Google API Key.
- **Environment Variable:** `GOOGLE_API_KEY` must be set in the shell.
- **Target Project:** `gnosis-459403`.

### 2. Media Processing (FFmpeg)
- **Service:** Self-hosted FFmpeg provided via the `nemisis8:latest` Docker image.
- **Usage:** The agent invokes `docker run --rm -v ${PWD}:/data nemisis8:latest ffmpeg ...` for all stitching and complex transitions.
- **Stitching:** Uses the FFmpeg `concat` demuxer for lossless segment joining.

### 3. Python Environment
- **SDK:** `google-genai` (latest).
- **Libraries:** `cv2` (OpenCV), `requests`, `subprocess`.

## 🧬 Core Technique: "Nanobanana"
To overcome the 5-8 second limitation of individual Veo clips, the agent uses **Keyframe Seeding**:
1. Generate Segment A.
2. Extract the **exact last frame** of Segment A as a high-quality image (`cv2`).
3. Pass this image as the `image` parameter to the Veo 3 `generate_videos` call for Segment B.
4. The model treats this frame as the starting state, ensuring a seamless visual transition.

## 🚀 CLI Commands

### 1. Basic Generation (5-8 Seconds)
Generates a single standalone clip.
```bash
python veo_agent.py "A majestic eagle soaring over mountains" output.mp4
```

### 2. Seamless Looping (8 Seconds)
Generates 15s of footage and uses a 1s cross-fade to blend the end back to the start.
```bash
python veo_agent.py loop "Slow aerial dolly over an alien landscape" loop.mp4
```

### 3. Long-Form Chaining (30s+)
Generates $N$ consecutive segments using frame-seeding and stitches them into a single long strip.
```bash
python veo_agent.py chain "Continuous dolly shot of a rising tide" 4 long_video.mp4
```

## 📝 Script Architecture (`veo_agent.py`)

- `get_client()`: Initialises the `genai.Client` with the environment API key.
- `extract_frame()`: Seeks to specific frames using `CAP_PROP_POS_FRAMES`.
- `generate_video()`: Main wrapper for the `models.generate_videos` endpoint. Handles polling of the operation object.
- `run_ffmpeg()`: Helper to execute FFmpeg commands inside the `nemisis8` container with local directory mounting.
- `stitch_videos()`: Automates the creation of `list.txt` and the `concat` demuxer command.

## ⚠️ Known Limitations
- **Generative Drift:** After ~10 chained segments, the visual fidelity may begin to soften as the model iterates on previously generated frames.
- **Polling Time:** Each 8s segment takes ~2 minutes to generate.
- **Resolution:** Looping/Chaining scripts are currently optimized for `720p` to ensure consistent cross-fade matching.
