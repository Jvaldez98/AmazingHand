"""Apply a test-specific pose without webcam tracking."""

import argparse
from grasp_profiles import STAGES, load_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", help="For example grasps/card.json")
    parser.add_argument("--stage", choices=STAGES, default="approach")
    parser.add_argument("--port", help="COM port; omit for a preview without hardware")
    parser.add_argument("--transport", choices=("tether", "waveshare"), default="tether")
    parser.add_argument("--baudrate", type=int)
    parser.add_argument("--reverse-motors", action="store_true")
    args = parser.parse_args()
    profile = load_profile(args.profile)
    targets = profile["poses"][args.stage]
    if targets is None:
        parser.error(f"No pose defined for {args.stage}")
    print(f"{profile['name']} / {args.stage}: {targets}")
    if not args.port:
        print("Preview only. Add --port COM4 to move the hand.")
        return
    if args.transport == "waveshare" and args.reverse_motors:
        parser.error("--reverse-motors is supported only for tether")
    if args.transport == "tether":
        from tetheria_esp32_bridge import TetherEsp32Bridge
        bridge = TetherEsp32Bridge(port=args.port, baudrate=args.baudrate or 921600,
                                   reverse_motors=args.reverse_motors)
    else:
        from amazing_hand_bridge import AmazingHandBridge
        bridge = AmazingHandBridge(port=args.port, baudrate=args.baudrate or 1000000)
    try:
        bridge.send_servo_degrees(targets)
        print("Pose applied; torque stays enabled until exit.")
        while True:
            command = input("approach / pinch / release, or q to disable torque and quit: ").strip().lower()
            if command == "q":
                break
            if command not in STAGES:
                continue
            pose = profile["poses"][command]
            if pose is None:
                print(f"No pose defined for {command}")
                continue
            bridge.send_servo_degrees(pose)
            print(f"Applied {command}: {pose}")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
