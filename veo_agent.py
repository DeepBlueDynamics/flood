import os
import sys
import time
import requests
import cv2
import subprocess
from google import genai
from google.genai import types

def get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    return genai.Client(api_key=api_key)

def extract_frame(video_path, output_image_path, last=True):
    print(f"Extracting {'last' if last else 'first'} frame from {video_path}...")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    if last:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(output_image_path, frame)
    cap.release()
    return output_image_path if ret else None

def generate_video(prompt, output_path="video_output.mp4", start_image=None):
    client = get_client()
    model_id = "veo-3.0-generate-001" 
    try:
        print(f"Generating segment: '{prompt[:50]}...'")
        config = types.GenerateVideosConfig(
            aspect_ratio="16:9",
            resolution="720p",
            duration_seconds=8  # Maximize duration
        )
        kwargs = {"model": model_id, "prompt": prompt, "config": config}
        if start_image:
            with open(start_image, 'rb') as f:
                img_data = f.read()
            kwargs["image"] = types.Image(image_bytes=img_data, mime_type="image/png")

        raw_op = client.models.generate_videos(**kwargs)
        op_id = raw_op.name if hasattr(raw_op, 'name') else str(raw_op)
        while True:
            status = client.operations.get(types.GenerateVideosOperation(name=op_id))
            if hasattr(status, 'done') and status.done:
                final_op = status
                break
            time.sleep(25)
            print(".", end="", flush=True)
            
        video_resp = final_op.result if final_op.result else final_op.response
        video_uri = video_resp.generated_videos[0].video.uri
        api_key = os.environ.get("GOOGLE_API_KEY")
        download_resp = requests.get(f"{video_uri}&key={api_key}")
        if download_resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(download_resp.content)
            return output_path
    except Exception as e:
        print(f"\nError: {e}")
    return None

def run_ffmpeg(args):
    cwd = os.getcwd()
    cmd = ["docker", "run", "--rm", "-v", f"{cwd}:/data", "nemisis8:latest", "ffmpeg", "-y"] + args
    print(f"FFmpeg: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True)

def stitch_videos(clips, output_path):
    print(f"Stitching {len(clips)} segments...")
    with open("list.txt", "w") as f:
        for p in clips: f.write(f"file '/data/{p}'\n")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "/data/list.txt", "-c", "copy", f"/data/{output_path}"])
    if os.path.exists("list.txt"): os.remove("list.txt")
    return output_path

def create_loop(prompt, final_output):
    print("Building a seamless cross-fade loop...")
    parts = ["p1.mp4", "p2.mp4", "p3.mp4"]
    last_frame = None
    for i, p in enumerate(parts):
        if not generate_video(prompt, p, start_image=last_frame): return
        last_frame = f"frame_{i}.png"
        extract_frame(p, last_frame, last=True)

    stitch_videos(parts, "long.mp4")
    filter_complex = "[0:v]split[v1][v2];[v1]trim=start=0:end=8,setpts=PTS-STARTPTS[main];[v2]trim=start=8:end=9,setpts=PTS-STARTPTS[fade];[fade][main]xfade=transition=fade:duration=1:offset=0"
    run_ffmpeg(["-i", "/data/long.mp4", "-filter_complex", filter_complex, "-c:v", "libx264", "-pix_fmt", "yuv420p", f"/data/{final_output}"])

    for f in parts + ["long.mp4"] + [f"frame_{i}.png" for i in range(3)]:
        if os.path.exists(f): os.remove(f)
    print(f"Loop saved to {final_output}")

def chain_videos(prompt, num_segments, final_output):
    print(f"Chaining {num_segments} segments for a long video...")
    parts = []
    last_frame = None
    for i in range(num_segments):
        p = f"part_{i}.mp4"
        if not generate_video(prompt, p, start_image=last_frame):
            break
        parts.append(p)
        last_frame = f"last_frame_{i}.png"
        extract_frame(p, last_frame, last=True)
    
    stitch_videos(parts, final_output)
    
    # Cleanup
    for f in parts + [f"last_frame_{i}.png" for i in range(len(parts))]:
        if os.path.exists(f): os.remove(f)
    print(f"Chained video saved to {final_output}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python veo_agent.py \"Prompt\" [out.mp4]")
        print("Usage: python veo_agent.py loop \"Prompt\" out.mp4")
        print("Usage: python veo_agent.py chain \"Prompt\" count out.mp4")
    elif sys.argv[1] == "loop":
        create_loop(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "chain":
        chain_videos(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        generate_video(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "video_output.mp4")
