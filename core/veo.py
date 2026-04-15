"""Consolidated Veo 3 generation logic."""

import os
import time
import requests
import cv2
from google import genai
from google.genai import types
from core import ffmpeg

MODEL_ID = "veo-3.0-generate-001"

def default_progress(event):
    t = event.get("type", "")
    if t == "polling":
        print(".", end="", flush=True)
    else:
        msg = event.get("message", "")
        if msg:
            print(msg)

def get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)

def extract_frame(video_path, output_image_path, last=True):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    if last:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total - 1)
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Could not read frame from {video_path}")
    cv2.imwrite(output_image_path, frame)
    return output_image_path

def _p(work_dir, name):
    if work_dir:
        return os.path.join(work_dir, name)
    return name

def generate_video(prompt, output_path, start_image=None, progress_cb=None):
    if progress_cb is None:
        progress_cb = default_progress
    client = get_client()
    progress_cb({"type": "message", "message": f"Generating: '{prompt[:60]}'"})
    config = types.GenerateVideosConfig(aspect_ratio="16:9", resolution="1080p", duration_seconds=8)
    kwargs = {"model": MODEL_ID, "prompt": prompt, "config": config}
    if start_image:
        with open(start_image, 'rb') as f:
            img_data = f.read()
        kwargs["image"] = types.Image(image_bytes=img_data, mime_type="image/png")
    operation = client.models.generate_videos(**kwargs)
    while not getattr(operation, "done", False):
        progress_cb({"type": "polling"})
        time.sleep(25)
        operation = client.operations.get(operation)
    video_resp = operation.result or operation.response
    if not video_resp or not video_resp.generated_videos:
        raise RuntimeError(f"No video generated. Response: {video_resp}")
    video_uri = video_resp.generated_videos[0].video.uri
    dl = requests.get(f"{video_uri}&key={os.environ['GOOGLE_API_KEY']}")
    with open(output_path, "wb") as f:
        f.write(dl.content)
    progress_cb({"type": "message", "message": f"Saved -> {output_path}"})
    return output_path

def create_loop(prompt, final_output, progress_cb=None, work_dir=None):
    if progress_cb is None:
        progress_cb = default_progress
    progress_cb({"type": "message", "message": "Generating 10s seamless loop (3 robust segments)..."})
    parts = []
    last_frame = None
    for i in range(3):
        seg = _p(work_dir, f"_loop_p{i}.mp4")
        if not os.path.exists(seg):
            generate_video(prompt, seg, start_image=last_frame, progress_cb=progress_cb)
        parts.append(seg)
        last_frame = _p(work_dir, f"_loop_frame_{i}.png")
        extract_frame(seg, last_frame, last=True)

    wd = work_dir or os.getcwd()
    
    # Step 1: Join the segments into a long strip (24s)
    long_strip = _p(work_dir, "_loop_full_strip.mp4")
    ffmpeg.stitch_videos(parts, long_strip, work_dir=work_dir)
    
    # Step 2: Create the loop from the strip
    # We take 11 seconds from the strip and loop the last 1s back to the start.
    # Result is a 10s loop.
    filter_complex = (
        "[0:v]trim=start=0:end=11,setpts=PTS-STARTPTS[short];"
        "[short]split[v1][v2];"
        "[v1]trim=start=1:end=11,setpts=PTS-STARTPTS[main];"
        "[v2]trim=start=0:end=1,setpts=PTS-STARTPTS[start_fade];"
        "[main][start_fade]xfade=transition=fade:duration=1:offset=9"
    )
    
    args = [
        "-i", ffmpeg.data_path(long_strip, wd),
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        ffmpeg.data_path(final_output, wd)
    ]
    ffmpeg.run_ffmpeg(args, work_dir=wd)
    
    progress_cb({"type": "complete", "message": f"Loop saved to {final_output}"})
    return final_output

def storyboard_videos(prompts, final_output, progress_cb=None, work_dir=None, start_image=None):
    if progress_cb is None:
        progress_cb = default_progress
    num_segments = len(prompts)
    parts = []
    last_frame = start_image
    for i, prompt in enumerate(prompts):
        seg = _p(work_dir, f"_story_p{i}.mp4")
        generate_video(prompt, seg, start_image=last_frame, progress_cb=progress_cb)
        parts.append(seg)
        last_frame = _p(work_dir, f"_story_frame_{i}.png")
        extract_frame(seg, last_frame, last=True)
    ffmpeg.stitch_videos(parts, final_output, work_dir=work_dir)
    return final_output

def chain_videos(prompt, num_segments, final_output, progress_cb=None, work_dir=None, start_image=None):
    prompts = [prompt] * num_segments
    return storyboard_videos(prompts, final_output, progress_cb, work_dir, start_image)

def extend_video(source_video, prompts, output_path, progress_cb=None, work_dir=None):
    if progress_cb is None:
        progress_cb = default_progress
    segments = [os.path.abspath(source_video)]
    current_video = source_video
    for i, prompt in enumerate(prompts):
        last_frame = _p(work_dir, f"_ext_frame_{i}.png")
        extract_frame(current_video, last_frame, last=True)
        seg_path = _p(work_dir, f"_ext_seg_{i}.mp4")
        generate_video(prompt, seg_path, start_image=last_frame, progress_cb=progress_cb)
        segments.append(os.path.abspath(seg_path))
        current_video = seg_path
    ffmpeg.stitch_videos(segments, output_path, work_dir=work_dir)
    return output_path
