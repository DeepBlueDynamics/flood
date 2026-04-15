"""FFmpeg abstraction — Docker container or local binary."""

import os
import shutil
import subprocess

def get_mode():
    return os.environ.get("FFMPEG_MODE", "docker")

def data_path(filepath, work_dir=None):
    cwd = os.path.abspath(work_dir or os.getcwd())
    abs_fp = os.path.abspath(filepath)
    try:
        rel = os.path.relpath(abs_fp, cwd).replace("\\", "/")
    except ValueError:
        rel = os.path.basename(filepath)
    return f"/data/{rel}"

def run_ffmpeg(args, work_dir=None):
    mode = get_mode()
    cwd = os.path.abspath(work_dir or os.getcwd()).replace("\\", "/")
    if mode == "local":
        translated = [a.replace("/data/", cwd + "/") for a in args]
        cmd = ["ffmpeg", "-y"] + translated
    else:
        image = os.environ.get("FFMPEG_DOCKER_IMAGE", "nemisis8:latest")
        cmd = ["docker", "run", "--rm", "-v", f"{cwd}:/data", image, "ffmpeg", "-y"] + args
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg exit {result.returncode}: {result.stderr}")
    return result

def stitch_videos(clips, output_path, work_dir=None):
    """Robustly concatenate video clips using the concat filter to prevent freezes."""
    if len(clips) == 1:
        shutil.copy2(clips[0], output_path)
        return output_path

    # Build the filter complex: [0:v][0:a][1:v][1:a]...concat=n=N:v=1:a=1[v][a]
    inputs = []
    filter_str = ""
    for i, clip in enumerate(clips):
        inputs.extend(["-i", data_path(clip, work_dir)])
        filter_str += f"[{i}:v][{i}:a]"
    
    filter_str += f"concat=n={len(clips)}:v=1:a=1[v][a]"
    
    args = inputs + [
        "-filter_complex", filter_str,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", 
        "-c:a", "aac", "-b:a", "192k",
        data_path(output_path, work_dir)
    ]
    
    return run_ffmpeg(args, work_dir=work_dir)
