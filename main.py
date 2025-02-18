import cv2
import numpy as np
import asyncio
from bleak import BleakClient, BleakScanner
import uvicorn
import csv
import time
import psutil  # To check if a process is running
import threading  # To run FastAPI and BLE client in separate threads
import webview  # pywebview for embedding the frontend
import sys
import os
import json  # <-- For parsing JSON from ESP
from fastapi import FastAPI, Response, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# ----------------------------------------------------------------------
#    Adjust your BASE_PATH and static paths as before
# ----------------------------------------------------------------------
if hasattr(sys, '_MEIPASS'):
    BASE_PATH = sys._MEIPASS
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

static_path = os.path.join(BASE_PATH, 'static')
html_file_path = os.path.join(BASE_PATH, "index.html")
print("Base path:", BASE_PATH)
print("Static directory:", static_path)

app = FastAPI()
app.mount("/static", StaticFiles(directory=static_path), name="static")

insole_image_path = os.path.join(BASE_PATH, 'static', 'insole_image.jpeg')
print("Insole image path:", insole_image_path)

image = cv2.imread(insole_image_path)
if image is None:
    print(f"Error: Image at path '{insole_image_path}' not found.")
    sys.exit(1)


# ------------------------ Single Instance Lock ------------------------ #

class SingleInstance:
    """
    Prevent multiple instances from running simultaneously.
    """
    def __init__(self, lock_file):
        self.lock_file = lock_file
        self.fd = None
        self.pid = None

    def __enter__(self):
        if os.path.exists(self.lock_file):
            try:
                with open(self.lock_file, 'r') as f:
                    self.pid = int(f.read())
                if psutil.pid_exists(self.pid):
                    print("Another instance is running. Exiting.")
                    sys.exit(1)
                else:
                    print("Stale lock file found. Removing it.")
                    os.remove(self.lock_file)
            except Exception as e:
                print(f"Error reading lock file: {e}")
                print("Assuming another instance is running. Exiting.")
                sys.exit(1)

        try:
            # Create the lock file and write our PID
            self.fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR)
            os.write(self.fd, str(os.getpid()).encode())
            return self
        except Exception as e:
            print(f"Unable to create lock file: {e}")
            sys.exit(1)

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.fd:
                os.close(self.fd)
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except Exception as e:
            print(f"Error removing lock file: {e}")


# ------------------------ BLE Configuration ------------------------ #
#
# Make sure your DEVICE_NAMES, SERVICE_UUIDS, and CHARACTERISTIC_UUIDS
# match the new code in your ESP32 firmware (name, service UUID, etc.).
# --------------------------------------------------------------------
DEVICE_NAMES = ["ESP32_Sensor_1", "ESP32_Sensor_2"]  # or add more as needed

SERVICE_UUIDS = {
    "ESP32_Sensor_1": "4fafc201-1fb5-459e-8fcc-c5c9c331914b",
    "ESP32_Sensor_2": "4fafc201-1fb5-459e-8fcc-c5c9c331914c",
    # Add other devices if needed ...
}

CHARACTERISTIC_UUIDS = {
    "ESP32_Sensor_1": "beb5483e-36e1-4688-b7f5-ea07361b26a8",
    "ESP32_Sensor_2": "beb5483e-36e1-4688-b7f5-ea07361b26a9",
    # Adjust if your second device uses a different characteristic ...
}

# Example structure to store data from each device
# You can expand or reorganize as you see fit.
sensor_values_lock = threading.Lock()
sensor_values = {
    "ESP32_Sensor_1": {
        "timestamp": 0,
        # The new JSON includes sensor1..sensor4 + intervals.
        # We'll store them directly for demonstration:
        "sensor1": 0,
        "sensor2": 0,
        "sensor3": 0,
        "sensor4": 0,
        "interval1_ms": 0,
        "interval2_ms": 0,
        "interval3_ms": 0,
        "interval4_ms": 0,
    },
    "ESP32_Sensor_2": {
        "timestamp": 0,
        "sensor1": 0,
        "sensor2": 0,
        "sensor3": 0,
        "sensor4": 0,
        "interval1_ms": 0,
        "interval2_ms": 0,
        "interval3_ms": 0,
        "interval4_ms": 0,
    },
}

connected_clients = {}

# --------------------- Recording State (if needed) --------------------- #
recording_lock = threading.Lock()
is_recording = False
current_recording_1 = []
current_recording_2 = []
user_data = {}
RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)
last_recorded_timestamp = 0


# ------------------------ Image Processing ------------------------ #

def process_image():
    """
    (Optional) Example that processes an insole image and extracts contours.
    Adapt/keep as needed.
    """
    image_path = os.path.join(BASE_PATH, 'static', 'insole_image.jpeg')
    image_gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image_gray is None:
        print(f"Error: Image at path '{image_path}' not found.")
        return None

    desired_width, desired_height = 600, 600
    image_gray = cv2.resize(image_gray, (desired_width, desired_height))

    _, binary = cv2.threshold(image_gray, 100, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        print("No contours found in the image.")
        return None

    # (Optional) Example of how you might separate left vs. right insole
    contour_centroids = []
    for cnt in contours:
        M = cv2.moments(cnt)
        if M['m00'] != 0:
            cx = int(M['m10'] / M['m00'])
        else:
            cx = 0
        contour_centroids.append((cnt, cx))

    contour_centroids.sort(key=lambda x: x[1])
    xs = [cx for _, cx in contour_centroids]
    median_x = np.median(xs)

    left_contours = [cnt for cnt, cx in contour_centroids if cx < median_x]
    right_contours = [cnt for cnt, cx in contour_centroids if cx >= median_x]

    def contour_to_list(contour):
        return contour[:, 0, :].tolist()

    insole_c = {"Left": {}, "Right": {}}
    part_names = ["Heel", "Middle", "Top"]

    def assign_parts(conts, side):
        conts.sort(key=lambda c: cv2.boundingRect(c)[1], reverse=True)
        for i, part in enumerate(conts):
            if i < len(part_names):
                part_name = f"{side}_{part_names[i]}"
            else:
                part_name = f"{side}_Part_{i}"
            insole_c[side][part_name] = contour_to_list(part)

        # Ensure at least these keys exist
        for part_name in part_names:
            key = f"{side}_{part_name}"
            if key not in insole_c[side]:
                insole_c[side][key] = []

    assign_parts(left_contours, "Left")
    assign_parts(right_contours, "Right")

    return insole_c


insole_contours = process_image()


# ------------------------ WebSocket Example ------------------------ #
@app.websocket("/ws")
async def imu_websocket_endpoint(ws: WebSocket):
    """
    Example WebSocket to stream data to a client in real-time.
    """
    await ws.accept()
    print("[WebSocket] Client connected.")
    try:
        while True:
            # Gather IMU or foot sensor data to broadcast, for instance:
            with sensor_values_lock:
                data_to_send = {
                    "ESP32_Sensor_1": sensor_values["ESP32_Sensor_1"],
                    "ESP32_Sensor_2": sensor_values["ESP32_Sensor_2"],
                }
            await ws.send_json(data_to_send)
            await asyncio.sleep(0.1)
    except Exception as e:
        print(f"[WebSocket] Disconnected: {e}")


# ------------------------ BLE Data Parsing ------------------------ #

async def process_sensor_data(device_name, data_str):
    """
    This function is invoked whenever notifications arrive from the BLE characteristic.
    In the new ESP32 code, the data is JSON (like {"sensor1":..., "sensor2":..., ...}).
    """
    try:
        # Attempt to decode JSON from the data string
        data_json = json.loads(data_str)

        # Example fields: sensor1, sensor2, sensor3, sensor4, interval1_ms, ...
        # This depends on what your ESP sends. Adjust accordingly:
        s1 = data_json.get("sensor1", 0)
        s2 = data_json.get("sensor2", 0)
        s3 = data_json.get("sensor3", 0)
        s4 = data_json.get("sensor4", 0)

        i1 = data_json.get("interval1_ms", 0)
        i2 = data_json.get("interval2_ms", 0)
        i3 = data_json.get("interval3_ms", 0)
        i4 = data_json.get("interval4_ms", 0)

        current_timestamp = time.time()

        with sensor_values_lock:
            # Update the global dictionary with new values
            sensor_values[device_name]["timestamp"] = current_timestamp
            sensor_values[device_name]["sensor1"] = s1
            sensor_values[device_name]["sensor2"] = s2
            sensor_values[device_name]["sensor3"] = s3
            sensor_values[device_name]["sensor4"] = s4
            sensor_values[device_name]["interval1_ms"] = i1
            sensor_values[device_name]["interval2_ms"] = i2
            sensor_values[device_name]["interval3_ms"] = i3
            sensor_values[device_name]["interval4_ms"] = i4

        # Debug print
        print(f"[{device_name}] => "
              f"sensor1={s1}, sensor2={s2}, sensor3={s3}, sensor4={s4}, "
              f"i1={i1}, i2={i2}, i3={i3}, i4={i4}")
    except json.JSONDecodeError:
        print(f"Warning: Received non-JSON data from {device_name}: {data_str}")
    except Exception as e:
        print(f"Error processing data from {device_name}: {e}")


# ------------------------ BLE Connection Management ------------------------ #

async def connect_to_device(address, device_name):
    """
    Attempt to connect to the device at `address` with a known `device_name`.
    Start notifications on the characteristic if connected.
    """
    global connected_clients
    try:
        if address in connected_clients:
            client = connected_clients[address]
            if client.is_connected:
                print(f"{device_name} at {address} is already connected.")
                return
            else:
                del connected_clients[address]

        client = BleakClient(address)
        await client.connect()
        print(f"Connected to {device_name} at {address}")

        connected_clients[address] = client

        # Notification handler
        def notification_handler(sender, data):
            data_str = data.decode('utf-8', errors='replace')
            asyncio.create_task(process_sensor_data(device_name, data_str))

        characteristic_uuid = CHARACTERISTIC_UUIDS[device_name]
        await client.start_notify(characteristic_uuid, notification_handler)
        print(f"Started notification handler for {device_name}")

        # Keep the connection alive:
        while True:
            await asyncio.sleep(1)
            if not client.is_connected:
                print(f"{device_name} disconnected. Attempting to reconnect...")
                del connected_clients[address]
                await connect_to_device(address, device_name)
                break
    except Exception as e:
        print(f"Failed to connect to {device_name} at {address}: {e}")
        if address in connected_clients:
            del connected_clients[address]
        await asyncio.sleep(5)
        await connect_to_device(address, device_name)


async def run_ble_client_main():
    """
    Main BLE scanning loop. Attempts to discover devices with known names
    and connect to them.
    """
    print("Scanning for BLE devices...")
    while True:
        try:
            devices = await BleakScanner.discover()

            tasks = []
            found_addresses = set()

            for dev in devices:
                dev_name = dev.name or dev.metadata.get('local_name', '')
                if dev_name in DEVICE_NAMES and dev.address not in found_addresses:
                    print(f"Found {dev_name} at {dev.address}")
                    task = asyncio.create_task(connect_to_device(dev.address, dev_name))
                    tasks.append(task)
                    found_addresses.add(dev.address)

            if not tasks:
                print("No matching ESP32 devices found. Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue

            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error in BLE client: {e}")
            await asyncio.sleep(5)


def run_ble_client():
    """
    Helper to run the BLE main loop in a separate thread.
    """
    asyncio.run(run_ble_client_main())


# ----------- If you want to record data in CSV, same logic as before ----------- #

async def synchronized_data_collector():
    """
    Example of a "synchronized" data collector that can record from both devices
    in a time-synchronized fashion. Adjust as needed.
    """
    global last_recorded_timestamp
    while True:
        with sensor_values_lock:
            ts1 = sensor_values["ESP32_Sensor_1"]["timestamp"]
            ts2 = sensor_values["ESP32_Sensor_2"]["timestamp"]

            # If both new timestamps are greater than the last saved,
            # we consider them a new pair of readings for potential logging
            if ts1 > last_recorded_timestamp and ts2 > last_recorded_timestamp:
                entry_1 = {
                    "timestamp": ts1,
                    "sensor1": sensor_values["ESP32_Sensor_1"]["sensor1"],
                    "sensor2": sensor_values["ESP32_Sensor_1"]["sensor2"],
                    "sensor3": sensor_values["ESP32_Sensor_1"]["sensor3"],
                    "sensor4": sensor_values["ESP32_Sensor_1"]["sensor4"],
                    "interval1_ms": sensor_values["ESP32_Sensor_1"]["interval1_ms"],
                    "interval2_ms": sensor_values["ESP32_Sensor_1"]["interval2_ms"],
                    "interval3_ms": sensor_values["ESP32_Sensor_1"]["interval3_ms"],
                    "interval4_ms": sensor_values["ESP32_Sensor_1"]["interval4_ms"],
                }
                entry_2 = {
                    "timestamp": ts2,
                    "sensor1": sensor_values["ESP32_Sensor_2"]["sensor1"],
                    "sensor2": sensor_values["ESP32_Sensor_2"]["sensor2"],
                    "sensor3": sensor_values["ESP32_Sensor_2"]["sensor3"],
                    "sensor4": sensor_values["ESP32_Sensor_2"]["sensor4"],
                    "interval1_ms": sensor_values["ESP32_Sensor_2"]["interval1_ms"],
                    "interval2_ms": sensor_values["ESP32_Sensor_2"]["interval2_ms"],
                    "interval3_ms": sensor_values["ESP32_Sensor_2"]["interval3_ms"],
                    "interval4_ms": sensor_values["ESP32_Sensor_2"]["interval4_ms"],
                }
                with recording_lock:
                    if is_recording:
                        current_recording_1.append(entry_1)
                        current_recording_2.append(entry_2)
                last_recorded_timestamp = max(ts1, ts2)

        await asyncio.sleep(0.1)


# ------------------------ FastAPI Routes ------------------------ #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index_page():
    """
    Return your main index.html
    """
    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return Response(content="index.html not found", media_type="text/plain", status_code=404)


@app.get("/get_insole_contours")
async def get_insole_contours_endpoint():
    if insole_contours is None:
        return JSONResponse(content={"error": "Insole contours not available."}, status_code=500)
    else:
        return JSONResponse(content=insole_contours)


@app.get("/get_sensor_values")
async def get_sensor_values():
    """
    Example endpoint to return the latest sensor values.
    Adjust the JSON structure if you want.
    """
    with sensor_values_lock:
        data = {
            "ESP32_Sensor_1": sensor_values["ESP32_Sensor_1"],
            "ESP32_Sensor_2": sensor_values["ESP32_Sensor_2"],
        }
    return JSONResponse(content=data)


# -------------- Example Start/Stop Recording Endpoints -------------- #

@app.post("/start_recording")
async def start_recording_endpoint(data: dict):
    """
    Example endpoint that starts recording.
    """
    required_fields = ['name', 'surname', 'height', 'weight', 'gender', 'shoe_size']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    # Extract user info
    name = data['name'].strip()
    surname = data['surname'].strip()
    height = data['height']
    weight = data['weight']
    gender = data['gender']
    shoe_size = data['shoe_size']

    if not name or not surname:
        raise HTTPException(status_code=400, detail="Name/surname cannot be empty.")

    with recording_lock:
        global is_recording, current_recording_1, current_recording_2, user_data
        if is_recording:
            raise HTTPException(status_code=400, detail="Recording is already in progress.")
        is_recording = True
        user_data = {
            'name': name,
            'surname': surname,
            'height': height,
            'weight': weight,
            'gender': gender,
            'shoe_size': shoe_size
        }
        current_recording_1 = []
        current_recording_2 = []

    return {"status": "Recording started."}


@app.post("/stop_recording")
async def stop_recording_endpoint():
    """
    Example endpoint that stops recording and saves CSV.
    """
    with recording_lock:
        global is_recording, current_recording_1, current_recording_2, user_data
        if not is_recording:
            raise HTTPException(status_code=400, detail="No recording in progress.")
        is_recording = False
        data1 = current_recording_1.copy()
        data2 = current_recording_2.copy()
        saved_user_data = user_data.copy()
        current_recording_1.clear()
        current_recording_2.clear()
        user_data = {}

    try:
        name = saved_user_data['name']
        surname = saved_user_data['surname']
        shoe_size = saved_user_data['shoe_size']
        height = str(saved_user_data['height'])
        weight = str(saved_user_data['weight'])
        gender = saved_user_data['gender']

        filename_1 = f"{name}{surname}_S{shoe_size}_H{height}_W{weight}_{gender[0].upper()}_Dev1.csv"
        filename_2 = f"{name}{surname}_S{shoe_size}_H{height}_W{weight}_{gender[0].upper()}_Dev2.csv"

        filepath_1 = os.path.join(RECORDINGS_DIR, filename_1)
        filepath_2 = os.path.join(RECORDINGS_DIR, filename_2)

        # Save each device's data to CSV
        fieldnames = [
            "timestamp", "sensor1", "sensor2", "sensor3", "sensor4",
            "interval1_ms", "interval2_ms", "interval3_ms", "interval4_ms"
        ]

        def save_csv(path, rows, hdrs):
            import csv
            with open(path, mode='w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=hdrs)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

        save_csv(filepath_1, data1, fieldnames)
        save_csv(filepath_2, data2, fieldnames)

        print(f"Device1 recording saved to {filepath_1}")
        print(f"Device2 recording saved to {filepath_2}")

    except Exception as e:
        print(f"Error saving recordings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save recordings.")

    return {
        "status": "Recording stopped and data saved.",
        "csv_device1": filename_1,
        "csv_device2": filename_2
    }


@app.post("/exit_app")
async def exit_app():
    """
    Endpoint to gracefully disconnect from BLE and then exit the app.
    """
    await disconnect_all_clients()
    os._exit(0)
    return {"status": "Exiting..."}  # Not actually reached


@app.get("/visualize", response_class=HTMLResponse)
async def visualize_page():
    """
    Returns a hypothetical visualize.html page (if you have one).
    """
    visualize_file_path = os.path.join(BASE_PATH, "visualize.html")
    try:
        with open(visualize_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return Response(content="visualize.html not found", media_type="text/plain", status_code=404)


@app.get("/list_csv_files")
def list_csv_files():
    """
    Return a list of CSV files in the 'recordings' directory.
    """
    files = []
    for fname in os.listdir(RECORDINGS_DIR):
        if fname.lower().endswith(".csv"):
            files.append(fname)
    return JSONResponse(files)


@app.get("/get_csv_data")
def get_csv_data(filename: str):
    """
    Read a CSV file and return its contents as JSON.
    E.g. GET /get_csv_data?filename=some.csv
    """
    file_path = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    rows = []
    with open(file_path, mode='r', newline='') as f:
        import csv
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return JSONResponse(rows)


async def disconnect_all_clients():
    """
    Disconnect from all BLE clients.
    """
    global connected_clients
    print("Disconnecting all BLE clients...")
    for address, client in connected_clients.items():
        if client.is_connected:
            await client.disconnect()
            print(f"Disconnected from {address}")
    connected_clients.clear()


# --------------------- Main Entry Point --------------------- #

def run_fastapi():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


def main():
    lock_file = 'app.lock'
    with SingleInstance(lock_file):
        # If needed, confirm your image was processed:
        if insole_contours is None:
            print("Failed to process insole image, continuing anyway...")

        # Start FastAPI in one thread
        fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
        fastapi_thread.start()
        print("FastAPI server started on http://127.0.0.1:8000")

        # Start the BLE scanning in another thread
        ble_thread = threading.Thread(target=run_ble_client, daemon=True)
        ble_thread.start()
        print("BLE client thread started.")

        # (Optional) Start a background collector for recording
        collector_thread = threading.Thread(target=lambda: asyncio.run(synchronized_data_collector()), daemon=True)
        collector_thread.start()

        # Start the embedded webview window
        try:
            webview.create_window("Insole Sensor App", "http://127.0.0.1:8000", fullscreen=False)
            webview.start()
        except Exception as e:
            print(f"Error starting webview: {e}")

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down application...")
            sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("Program terminated by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
