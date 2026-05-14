"""
receiver.py
Spresense (sender.ino, KX126) から CSV "x,y,z" を受信し、
ノルムの移動分散から STILL / WALK / RUN を分類して標準出力する。
さらに 10 秒ごとに分類結果を CSV にまとめて FTP 送信する。

使い方:
    python3 receiver.py [--port COM7] [--baud 115200]
"""
import argparse
import math
import os
import sys
import time
from collections import deque
from datetime import datetime

import serial

from ftp import upload

DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 115200
WINDOW = 20              # 約1秒 @ 20Hz
FLUSH_INTERVAL_SEC = 10  # FTP 送信間隔

# 分類しきい値 (G^2): 環境に合わせて要調整
STILL_VAR_MAX = 0.02   # これ未満は STILL
WALK_VAR_MAX  = 0.50   # これ未満は WALK、それ以上は RUN

LOG_DIR = "logs"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port", default=DEFAULT_PORT)
    p.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    return p.parse_args()


def classify(var: float) -> str:
    if var < STILL_VAR_MAX:
        return "STILL"
    if var < WALK_VAR_MAX:
        return "WALK"
    return "RUN"


def flush(buffer: list) -> None:
    """buffer 内のレコードを CSV に保存して FTP 送信。失敗時はローカルだけ残す。"""
    if not buffer:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"accel_{ts}.csv"
    local_path = os.path.join(LOG_DIR, filename)

    with open(local_path, "w") as f:
        f.write("timestamp,state,norm,x,y,z\n")
        for r in buffer:
            f.write(
                f"{r['t']},{r['state']},{r['norm']:.3f},"
                f"{r['x']:.3f},{r['y']:.3f},{r['z']:.3f}\n"
            )
    print(f"# saved: {local_path} ({len(buffer)} rows)", flush=True)

    try:
        upload(local_path, filename)
        print(f"# FTP sent: {filename}", flush=True)
    except Exception as e:
        print(f"# FTP error: {e}", flush=True)


def main():
    args = parse_args()
    ser = serial.Serial(args.port, args.baud, timeout=2)
    time.sleep(2)
    ser.reset_input_buffer()
    print(f"# connected: {args.port} @ {args.baud}", flush=True)

    norms = deque(maxlen=WINDOW)
    buffer: list = []
    last_flush = time.time()
    prev_state = None

    try:
        while True:
            raw = ser.readline()
            if raw:
                line = raw.decode(errors="ignore").strip()
                parts = line.split(",")
                if len(parts) == 3:
                    try:
                        x, y, z = (float(p) for p in parts)
                    except ValueError:
                        x = None
                    if x is not None:
                        norm = math.sqrt(x * x + y * y + z * z)
                        norms.append(norm)

                        if len(norms) < WINDOW:
                            print(
                                f"x={x:+.3f} y={y:+.3f} z={z:+.3f} "
                                f"|a|={norm:.3f} (warming up)",
                                flush=True,
                            )
                        else:
                            mean = sum(norms) / WINDOW
                            var = sum((n - mean) ** 2 for n in norms) / WINDOW
                            state = classify(var)

                            marker = " *" if state != prev_state else ""
                            prev_state = state
                            now = datetime.now().isoformat(timespec="milliseconds")
                            print(
                                f"{now} x={x:+.3f} y={y:+.3f} z={z:+.3f} "
                                f"|a|={norm:.3f} var={var:.4f} [{state}]{marker}",
                                flush=True,
                            )
                            buffer.append(
                                {"t": now, "state": state, "norm": norm,
                                 "x": x, "y": y, "z": z}
                            )

            # 10 秒経過したら FTP 送信
            if time.time() - last_flush >= FLUSH_INTERVAL_SEC:
                flush(buffer)
                buffer = []
                last_flush = time.time()

    except KeyboardInterrupt:
        print("\n# stopping...", flush=True)
    finally:
        flush(buffer)  # 残りも送信
        ser.close()
        print("# closed", flush=True)


if __name__ == "__main__":
    main()
    sys.exit(0)
