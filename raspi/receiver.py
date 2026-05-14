"""
receiver.py
Spresense (sender.ino, KX126) から CSV "x,y,z" を受信し、
ノルムと移動分散を計算して標準出力する。

使い方:
    python3 receiver.py [--port /dev/ttyUSB0] [--baud 115200]
"""
import argparse
import math
import sys
import time
from collections import deque

import serial

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
WINDOW = 20            # 約1秒 @ 20Hz
MOVE_VAR_THRESHOLD = 0.02  # G^2: これ以上で MOVE 判定


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=DEFAULT_PORT)
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    return p.parse_args()


def main():
    args = parse_args()
    ser = serial.Serial(args.port, args.baud, timeout=2)
    time.sleep(2)
    ser.reset_input_buffer()
    print(f"# connected: {args.port} @ {args.baud}", flush=True)

    norms = deque(maxlen=WINDOW)
    prev_state = None

    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode(errors="ignore").strip()
            if not line:
                continue

            parts = line.split(",")
            if len(parts) != 3:
                continue
            try:
                x, y, z = (float(p) for p in parts)
            except ValueError:
                continue

            norm = math.sqrt(x * x + y * y + z * z)
            norms.append(norm)

            if len(norms) < WINDOW:
                print(
                    f"x={x:+.3f} y={y:+.3f} z={z:+.3f} |a|={norm:.3f} (warming up)",
                    flush=True,
                )
                continue

            mean = sum(norms) / WINDOW
            var = sum((n - mean) ** 2 for n in norms) / WINDOW
            state = "MOVE " if var > MOVE_VAR_THRESHOLD else "STILL"

            marker = " *" if state != prev_state else ""
            prev_state = state
            print(
                f"x={x:+.3f} y={y:+.3f} z={z:+.3f} "
                f"|a|={norm:.3f} mean={mean:.3f} var={var:.4f} [{state}]{marker}",
                flush=True,
            )

    except KeyboardInterrupt:
        print("\n# stopping...", flush=True)
    finally:
        ser.close()
        print("# closed", flush=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
