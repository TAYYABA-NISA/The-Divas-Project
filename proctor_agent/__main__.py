import argparse
import sys

from .simulate import simulated_baseline, simulated_events
from .uplink import UplinkClient, UplinkError


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Local advisory proctoring agent")
    parser.add_argument("--server", required=True, help="Exam platform base URL")
    parser.add_argument("--token", required=True, help="One-time per-attempt token")
    parser.add_argument("--simulate", action="store_true", help="Emit safe simulated advisory events without hardware")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.simulate:
        print("Only --simulate is available in this lightweight agent build.", file=sys.stderr)
        return 2
    client = UplinkClient(args.server, args.token)
    try:
        client.post_baseline(simulated_baseline())
        for event_type, severity, details in simulated_events():
            client.post_event(event_type, severity, details)
    except UplinkError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Simulated advisory events were flagged for review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
