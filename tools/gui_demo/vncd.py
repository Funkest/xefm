"""Hold the one VNC connection to the demo VM, and serve primitives over a
Unix socket: key, pointer, still, record, stop. Everything with timing or
meaning lives in the client, so this never needs restarting (a second VNC
connection can crash the Virtualization framework's server).

    $VENV/bin/python tools/gui_demo/vncd.py temp/gui-demo/tart-run.log
"""
import json, os, re, socketserver, subprocess, sys, threading, time
from pathlib import Path

from PIL import Image

from rfb import RFB

SOCKET = "/tmp/xefm-demo-vnc.sock"
FPS = 30


class Daemon:
    def __init__(self, url_file):
        m = re.search(r"vnc://:([^@]+)@([\d.]+):(\d+)", Path(url_file).read_text())
        self.c = RFB(m.group(2), int(m.group(3)), m.group(1))
        self.c.request(False)
        threading.Thread(target=self._read, daemon=True).start()
        self.ffmpeg = None

    def _read(self):
        while True:
            if self.c.read_message() == "update":
                if getattr(self.c, "resized", None):
                    self.c.resized = None
                    self.c.request(False)
                else:
                    self.c.request(True)

    def record(self, path, fps=FPS):
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr0",
             "-s", f"{self.c.w}x{self.c.h}", "-r", str(fps), "-i", "-",
             "-c:v", "h264_videotoolbox", "-b:v", "40M", "-pix_fmt", "yuv420p", path],
            stdin=subprocess.PIPE)
        self.recording = True
        self.writer = threading.Thread(target=self._write, args=(fps,), daemon=True)
        self.writer.start()

    def _write(self, fps):
        start, frames = time.monotonic(), 0
        while self.recording:
            due = start + frames / fps
            now = time.monotonic()
            if now < due:
                time.sleep(due - now)
            self.ffmpeg.stdin.write(self.c.snapshot().tobytes())
            frames += 1

    def stop(self):
        if self.ffmpeg:
            self.recording = False
            self.writer.join()
            self.ffmpeg.stdin.close()
            self.ffmpeg.wait()
            self.ffmpeg = None

    def still(self, path, scale=2):
        img = self.c.snapshot()[:, :, [2, 1, 0]]
        Image.fromarray(img).resize((self.c.w // scale, self.c.h // scale)).save(path)

    def handle(self, req):
        op = req["op"]
        if op == "key":
            self.c.key(req["sym"], req["down"])
        elif op == "pointer":
            self.c.pointer(req["x"], req["y"], req["buttons"])
        elif op == "still":
            self.still(req["path"])
        elif op == "record":
            self.record(req["path"])
        elif op == "stop":
            self.stop()
        elif op == "size":
            return {"w": self.c.w, "h": self.c.h}
        return {}


def main():
    d = Daemon(sys.argv[1])

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                try:
                    reply = {"ok": True, **d.handle(json.loads(line))}
                except Exception as e:
                    reply = {"ok": False, "error": repr(e)}
                self.wfile.write((json.dumps(reply) + "\n").encode())
                self.wfile.flush()

    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with socketserver.ThreadingUnixStreamServer(SOCKET, Handler) as server:
        print("serving", SOCKET, d.c.w, d.c.h, flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
