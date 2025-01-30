import sys
import os
import math
import time
import asyncio
import psutil
import threading
from bleak import BleakClient, BleakScanner
import uvicorn
import webview
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from starlette.responses import FileResponse


# ------------- SINGLE-INSTANCE LOCK -------------
class SingleInstance:
    def __init__(self, lock_file):
        self.lock_file = lock_file
        self.fd = None

    def __enter__(self):
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, 'r') as f:
                    pid = int(f.read())
                if psutil.pid_exists(pid):
                    print("Another instance is running. Exiting.")
                    sys.exit(1)
                else:
                    print("Removing stale lock file.")
                    os.remove(self.lock_file)
            except Exception:
                print("Error reading lock file. Assuming another instance is running.")
                sys.exit(1)

        try:
            self.fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
            os.write(self.fd, str(os.getpid()).encode())
            return self
        except Exception:
            print("Unable to create lock file.")
            sys.exit(1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd:
            os.close(self.fd)
        if os.path.exists(self.lock_file):
            os.remove(self.lock_file)

# ------------- FASTAPI APP -------------
app = FastAPI()

# ------------- BLE + IMU DATA -------------
SERVICE_UUID        = "5d6fce32-7d51-48c3-bb12-d11fba01e12f"
CHARACTERISTIC_UUID = "bafabc41-3b2b-4231-bdaf-e89a1bcbdf45"

esp_data = {
    "roll1":  0.0,
    "pitch1": 0.0,
    "roll2":  0.0,
    "pitch2": 0.0,
    "timestamp": time.strftime("%H:%M:%S")
}

connected_client = None
ble_task_running = False

# ------------- BLE SCAN + CONNECT + LISTEN -------------
async def scan_for_esp32():
    print("Scanning for ESP32 device advertising SERVICE_UUID...")
    while True:
        devices = await BleakScanner.discover()
        for d in devices:
            if SERVICE_UUID in d.metadata.get("uuids", []):
                print(f"Found ESP32 at {d.address}")
                return d.address
        print("Not found. Retrying in 5s...")
        await asyncio.sleep(5)

async def connect_and_listen():
    global connected_client
    esp32_address = await scan_for_esp32()

    async with BleakClient(esp32_address) as client:
        connected_client = client
        if not client.is_connected:
            print("Failed to connect to ESP32.")
            return
        print("Connected to ESP32!")

        def notification_handler(sender, data: bytearray):
            decoded = data.decode("utf-8").strip()
            print(f"[BLE] Raw data: {decoded}")
            try:
                vals = decoded.split(",")
                if len(vals) >= 4:
                    r1, p1, r2, p2 = map(float, vals[:4])
                    esp_data["roll1"]  = r1
                    esp_data["pitch1"] = p1
                    esp_data["roll2"]  = r2
                    esp_data["pitch2"] = p2
                    esp_data["timestamp"] = time.strftime("%H:%M:%S")
                    print(f"[BLE Parsed] r1={r1}, p1={p1}, r2={r2}, p2={p2} | {esp_data['timestamp']}")
            except Exception as e:
                print(f"Error parsing BLE data '{decoded}': {e}")

        await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
        print("Notification handler started.")

        while True:
            if not client.is_connected:
                print("BLE device disconnected.")
                return
            await asyncio.sleep(1)

async def run_ble_client():
    global ble_task_running
    if ble_task_running:
        print("BLE client already running.")
        return
    ble_task_running = True
    try:
        await connect_and_listen()
    except Exception as e:
        print(f"BLE Error: {e}")
    finally:
        ble_task_running = False

# ------------- WEBSOCKET /ws -------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    print("[WebSocket] Client connected.")
    try:
        while True:
            await ws.send_json(esp_data)
            await asyncio.sleep(0.05)  # 20 times/sec
    except Exception as e:
        print(f"[WebSocket] Disconnected: {e}")

# ------------- ROOT HTML PAGE -------------
@app.get("/", response_class=FileResponse)
async def serve_index():
    return FileResponse("walking_human.html")

# ------------- RUN SERVERS -------------
def run_fastapi_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

def run_ble_client_in_thread():
    asyncio.run(run_ble_client())

def main():
    lock_file = "app.lock"
    with SingleInstance(lock_file):
        threading.Thread(target=run_fastapi_server, daemon=True).start()
        threading.Thread(target=run_ble_client_in_thread, daemon=True).start()
        webview.create_window("IMU Visualization", "http://127.0.0.1:8000", width=1024, height=768)
        webview.start(debug=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Program terminated.")
