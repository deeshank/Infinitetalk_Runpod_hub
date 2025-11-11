import json
import base64
import argparse
import sys
from pathlib import Path


def save_video_from_json(json_data: dict, output_path: Path) -> None:
    """
    Extracts output.video from the given JSON object,
    decodes it from base64, and writes it as a binary video file.
    """

    try:
        output = json_data["output"]
        video_b64 = output["video"]
    except (KeyError, TypeError) as exc:
        raise ValueError("JSON does not contain 'output.video'") from exc

    try:
        video_bytes = base64.b64decode(video_b64)
    except Exception as exc:
        raise ValueError("Failed to base64 decode output.video") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as file:
        file.write(video_bytes)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read RunPod style JSON and save output.video as an MP4 file."
    )
    parser.add_argument(
        "-i", "--input",
        help="Path to JSON file. If omitted, JSON is read from standard input.",
        required=False,
    )
    parser.add_argument(
        "-o", "--output",
        help="Path for the output video file (default: output.mp4).",
        default="output.mp4",
    )

    args = parser.parse_args()

    # Load JSON from file or standard input
    if args.input:
        with open(args.input, "r", encoding="utf-8") as file:
            json_data = json.load(file)
    else:
        json_text = sys.stdin.read()
        json_data = json.loads(json_text)

    save_video_from_json(json_data, Path(args.output))
    print(f"Saved video to {args.output}")


if __name__ == "__main__":
    main()


#python util.py -i sample_response.json -o result.mp4