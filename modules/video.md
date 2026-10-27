# Video module

Use this module for video analysis, screen recording, creation, and processing.

## Actions

- `analyze`: inspect streams, duration, codecs, dimensions, sampled frames, and content evidence.
- `record`: capture a real application or workflow demonstration.
- `create`: assemble approved images, narration, audio, and transitions into a video.
- `process`: trim, transcode, compress, merge, or extract evidence.

Write `.autoflow/intermediate/plans/video.json` with requirement ids, action, real/simulated evidence policy, inputs, output, target duration/dimensions, sampling plan, and validation commands. Use the locally routed [video processor](../scripts/video_process.py) and the detected ffmpeg/ffprobe paths for analysis and screen recording. Record the exact command, input paths, output path, duration, dimensions, codec, and verification result; do not resolve an unverified external video Skill. Follow the [video acceptance contract](../references/acceptance-contracts.md).

Do not fabricate a demonstration when the request requires real operation evidence. Run `video_process.py analyze` after production and retain its `autoflow/video-validation/1.0` report. Inspect sampled frames before registering the video; zero duration, unknown dimensions, unknown codec, or missing requested samples fail acceptance.

Use `gate_after: visual` for recordings, demonstrations, and produced videos. Show sampled frames and the playable result at `VISUAL_STOP`; approval applies to the current media hash and must precede packaging.
