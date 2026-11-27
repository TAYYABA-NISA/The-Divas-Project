import argparse
import sys

from .runtime import run_live
from .simulate import simulated_baseline, simulated_events
from .uplink import UplinkClient, UplinkError


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Local advisory proctoring agent")
    parser.add_argument("--server", required=True, help="Exam platform base URL")
    parser.add_argument("--token", required=True, help="One-time per-attempt token")
    parser.add_argument("--simulate", action="store_true", help="Emit safe simulated advisory events without hardware")
    parser.add_argument("--video", help="Optional sample video path instead of a webcam")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index for live monitoring")
    parser.add_argument("--max-frames", type=int, help="Stop after this many video frames (useful for demos)")
    parser.add_argument("--gaze-seconds", type=float, default=5.0, help="Seconds away before flagging for review")
    parser.add_argument("--calibration-distance", type=float, help="One-time known face distance in metres")
    parser.add_argument("--phone-detection", action="store_true", help="Enable local YOLOv8n cell-phone detection")
    parser.add_argument("--phone-confidence", type=float, default=0.60, help="Minimum cell-phone confidence")
    parser.add_argument("--phone-frames", type=int, default=3, help="Consecutive phone frames required")
    parser.add_argument("--screen-capture", action="store_true", help="Keep a short local screen ring buffer for phone flags")
    parser.add_argument("--screen-frames", type=int, default=75, help="Maximum screen frames kept locally")
    parser.add_argument("--identity-check", action="store_true", help="Compare an enrolled private reference photo locally")
    parser.add_argument("--identity-threshold", type=float, default=0.82, help="Reference comparison threshold")
    return parser.parse_args(argv)


def _run_simulation(client):
    client.post_baseline(simulated_baseline())
    for event_type, severity, details in simulated_events():
        client.post_event(event_type, severity, details)


def main(argv=None):
    args = parse_args(argv)
    client = UplinkClient(args.server, args.token)
    try:
        if args.simulate:
            _run_simulation(client)
        else:
            run_live(args, client)
    except (RuntimeError, UplinkError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Advisory events were flagged for examiner review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
