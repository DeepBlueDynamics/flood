#!/usr/bin/env python3
"""Extend a video with chained Veo continuations."""

import os
import sys
import time
import argparse
import subprocess
import cv2
import requests
from google import genai
from google.genai import types


MODEL_ID = "veo-3.0-generate-001"


def get_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def extract_last_frame(video_path):
    """Extract last frame from a video file, return path to saved PNG."""
    output_path = os.path.splitext(video_path)[0] + "_lastframe.png"
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Could not read last frame from {video_path}")

    cv2.imwrite(output_path, frame)
    print(f"Extracted last frame ({total_frames} total) -> {output_path}")
    return output_path


def generate_continuation(prompt, start_frame_path, end_frame_path=None,
                          output_path="continuation.mp4"):
    """Generate a continuation clip using Veo image-to-video.

    start_frame_path: image used as the starting frame (top-level image param)
    end_frame_path:   optional image used as the target end frame (last_frame in config)
    """
    client = get_client()
    api_key = os.environ["GOOGLE_API_KEY"]

    print(f"Generating continuation: '{prompt}'")
    print(f"  Start frame: {start_frame_path}")
    if end_frame_path:
        print(f"  End frame target: {end_frame_path}")

    config_kwargs = {}
    if end_frame_path:
        config_kwargs["last_frame"] = types.Image.from_file(end_frame_path)

    operation = client.models.generate_videos(
        model=MODEL_ID,
        prompt=prompt,
        image=types.Image.from_file(start_frame_path),
        config=types.GenerateVideosConfig(**config_kwargs),
    )

    print(f"Operation: {operation.name}")

    while not operation.done:
        print(".", end="", flush=True)
        time.sleep(20)
        operation = client.operations.get(operation)

    if operation.error:
        raise RuntimeError(f"Veo error: {operation.error}")

    video_resp = operation.result or operation.response
    if not video_resp or not video_resp.generated_videos:
        raise RuntimeError(f"No video generated. Response: {video_resp}")

    video_uri = video_resp.generated_videos[0].video.uri
    print(f"\nVideo ready: {video_uri}")

    download_resp = requests.get(f"{video_uri}&key={api_key}")
    if download_resp.status_code != 200:
        raise RuntimeError(
            f"Download failed ({download_resp.status_code}): {download_resp.text}"
        )

    with open(output_path, "wb") as f:
        f.write(download_resp.content)
    print(f"Saved segment -> {output_path}")
    return output_path


def stitch_videos(video_paths, output_path):
    """Concatenate video files. Try ffmpeg-service docker, fall back to cv2."""
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return output_path

    try:
        return _stitch_ffmpeg(video_paths, output_path)
    except Exception as e:
        print(f"FFmpeg stitch failed ({e}), falling back to OpenCV...")
        return _stitch_cv2(video_paths, output_path)


def _stitch_ffmpeg(video_paths, output_path):
    """Stitch using ffmpeg via the ffmpeg-service docker container."""
    cwd = os.getcwd()
    concat_file = os.path.join(cwd, "_concat_list.txt")

    with open(concat_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '/data/{os.path.basename(vp)}'\n")

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{cwd}:/data",
        "ffmpeg-service:latest",
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", "/data/_concat_list.txt",
        "-c", "copy",
        f"/data/{os.path.basename(output_path)}",
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if os.path.exists(concat_file):
        os.remove(concat_file)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg exit {result.returncode}: {result.stderr}")

    print(f"Stitched ({len(video_paths)} clips) -> {output_path}")
    return output_path


def _stitch_cv2(video_paths, output_path):
    """Stitch using OpenCV as fallback."""
    print(f"Stitching {len(video_paths)} clips with OpenCV...")

    cap = cv2.VideoCapture(video_paths[0])
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    for vp in video_paths:
        cap = cv2.VideoCapture(vp)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        cap.release()

    out.release()
    print(f"Stitched ({len(video_paths)} clips) -> {output_path}")
    return output_path


def extend_video(source_video, prompts, output_path):
    """Main pipeline: chain continuations from a source video."""
    if not os.path.exists(source_video):
        raise FileNotFoundError(f"Source video not found: {source_video}")

    segments = [os.path.abspath(source_video)]
    current_video = source_video
    temp_files = []

    try:
        for i, prompt in enumerate(prompts):
            print(f"\n=== Segment {i + 1}/{len(prompts)} ===")

            last_frame = extract_last_frame(current_video)
            temp_files.append(last_frame)

            segment_path = os.path.join(
                os.path.dirname(output_path) or ".", f"_segment_{i + 1}.mp4"
            )
            generate_continuation(prompt, last_frame, output_path=segment_path)
            segments.append(os.path.abspath(segment_path))
            temp_files.append(os.path.abspath(segment_path))
            current_video = segment_path

        print(f"\n=== Stitching {len(segments)} segments ===")
        stitch_videos(segments, output_path)
        print(f"\nDone! Extended video -> {os.path.abspath(output_path)}")
        return output_path

    finally:
        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extend a video with chained Veo continuations"
    )
    parser.add_argument("source", help="Source video file")
    parser.add_argument("prompts", nargs="+", help="Continuation prompts")
    parser.add_argument("-o", "--output", default="extended.mp4", help="Output path")
    args = parser.parse_args()

    extend_video(args.source, args.prompts, args.output)
