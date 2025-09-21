
from time import sleep
from sdk.runtime import Session

def main():
    s = Session(name="runtime_smoke")
    s.start()
    for i in range(3):
        s.emit_video(frame_idx=i, w=1280, h=720, path=None)
        s.emit_input({"heartbeat": i})
        sleep(0.01)
    s.stop()
    print("[game_bot] stopped")

if __name__ == "__main__":
    main()
