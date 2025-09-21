
from __future__ import annotations
import argparse, time
from sdk import SDK_CONFIG, REGISTRY
from sdk.runtime import Session
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    s = Session(name=args.name); s.start()
    screen = REGISTRY.create(SDK_CONFIG.plugins["screen"])
    screen.configure(region=None, fps=SDK_CONFIG.video_fps); screen.start()
    for i in range(3):
        frame = screen.read()
        s.emit_video(frame_idx=i, w=1280, h=720, path=None)
        s.emit_input({"btn":"A","pressed": bool(i % 2)})
        time.sleep(0.016)
    screen.stop(); s.stop(); print("session:", s.session_id)
if __name__ == "__main__":
    main()
