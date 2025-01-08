import cv2
import numpy as np
import asyncio
from bleak import BleakClient, BleakScanner
from fastapi import FastAPI, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import csv
import time
from fastapi.responses import JSONResponse
import psutil  # To check if a process is running
import threading  # To run FastAPI and BLE client in separate threads
import webview  # pywebview for embedding the frontend
import sys
import os

from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

if hasattr(sys, '_MEIPASS'):
    BASE_PATH = sys._MEIPASS
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

static_path = os.path.join(BASE_PATH, 'static')
html_file_path = os.path.join(BASE_PATH, "index.html")
print("Base path:", BASE_PATH)
print("Static directory:", static_path)

app = FastAPI()
# Now use `static_path` when mounting static files
app.mount("/static", StaticFiles(directory=static_path), name="static")

if hasattr(sys, '_MEIPASS'):
    BASE_PATH = sys._MEIPASS
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

insole_image_path = os.path.join(BASE_PATH, 'static', 'insole_image.jpeg')
print("Insole image path:", insole_image_path)

image = cv2.imread(insole_image_path)
if image is None:
    print(f"Error: Image at path '{insole_image_path}' not found.")
    sys.exit(1)

# ------------------------ Lock Mechanism ------------------------ #

class SingleInstance:
    """
    A context manager to ensure only one instance of the application runs.
    It creates a lock file upon entering and removes it upon exiting.
    If the lock file exists, it checks if the process is still running.
    If not, it removes the stale lock file and proceeds.
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
            # Create the lock file and write the current PID
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

DEVICE_NAMES = ["ESP32_Sensor_1", "ESP32_Sensor_2"]

SERVICE_UUIDS = {
    "ESP32_Sensor_1": "4fafc201-1fb5-459e-8fcc-c5c9c331914a",
    "ESP32_Sensor_2": "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
}

CHARACTERISTIC_UUIDS = {
    "ESP32_Sensor_1": "beb5483e-36e1-4688-b7f5-ea07361b26a8",
    "ESP32_Sensor_2": "beb5483e-36e1-4688-b7f5-ea07361b26a9"
}

sensor_values = {
    'ESP32_Sensor_1': {'timestamp': 0, 'Left_Heel': 0, 'Left_Middle': 0, 'Left_Top': 0},
    'ESP32_Sensor_2': {'timestamp': 0, 'Right_Heel': 0, 'Right_Middle': 0, 'Right_Top': 0}
}

sensor_values_lock = threading.Lock()

recording_lock = threading.Lock()
is_recording = False
current_recording_left = []
current_recording_right = []
user_data = {}

RECORDINGS_DIR = "recordings"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

insole_contours = None
connected_clients = {}


# ------------------------ Image Processing ------------------------ #

def process_image():
    image_path = os.path.join(BASE_PATH, 'static', 'insole_image.jpeg')
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    if image is None:
        print(f"Error: Image at path '{image_path}' not found.")
        return None

    desired_width = 600
    desired_height = 600
    image = cv2.resize(image, (desired_width, desired_height))

    _, binary = cv2.threshold(image, 100, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        print("No contours found in the image.")
        return None

    contour_centroids = []
    for cnt in contours:
        M = cv2.moments(cnt)
        if M['m00'] != 0:
            cx = int(M['m10'] / M['m00'])
        else:
            cx = 0
        contour_centroids.append((cnt, cx))

    contour_centroids.sort(key=lambda x: x[1])
    xs = [cx for cnt, cx in contour_centroids]
    median_x = np.median(xs)

    left_contours = [cnt for cnt, cx in contour_centroids if cx < median_x]
    right_contours = [cnt for cnt, cx in contour_centroids if cx >= median_x]

    insole_c = {'Left': {}, 'Right': {}}
    part_names = ["Heel", "Middle", "Top"]

    def contour_to_list(contour):
        return contour[:, 0, :].tolist()

    def assign_parts(contours, side):
        contours.sort(key=lambda cnt: cv2.boundingRect(cnt)[1], reverse=True)
        for i, part in enumerate(contours):
            if i < len(part_names):
                part_name = f"{side}_{part_names[i]}"
            else:
                part_name = f"{side}_Part_{i}"
            insole_c[side][part_name] = contour_to_list(part)

        for part_name in part_names:
            key = f"{side}_{part_name}"
            if key not in insole_c[side]:
                insole_c[side][key] = []

    assign_parts(left_contours, 'Left')
    assign_parts(right_contours, 'Right')

    print("Left insole parts:", list(insole_c['Left'].keys()))
    print("Right insole parts:", list(insole_c['Right'].keys()))

    return insole_c


# ------------------------ BLE Data Processing ------------------------ #

async def process_sensor_data(device_name, data_str):
    try:
        values = [int(val) for val in data_str.strip().split(',')]
        print(f"Raw values from {device_name}: {values}")
        current_timestamp = time.time()
        with sensor_values_lock:
            if device_name == "ESP32_Sensor_1":
                sensor_values['ESP32_Sensor_1']['timestamp'] = current_timestamp
                sensor_values['ESP32_Sensor_1']['Left_Heel'] = values[0]
                sensor_values['ESP32_Sensor_1']['Left_Middle'] = values[1]
                sensor_values['ESP32_Sensor_1']['Left_Top'] = values[2]
            elif device_name == "ESP32_Sensor_2":
                sensor_values['ESP32_Sensor_2']['timestamp'] = current_timestamp
                sensor_values['ESP32_Sensor_2']['Right_Heel'] = values[0]
                sensor_values['ESP32_Sensor_2']['Right_Middle'] = values[1]
                sensor_values['ESP32_Sensor_2']['Right_Top'] = values[2]
    except Exception as e:
        print(f"Error processing data from {device_name}: {e}")


# ------------------------ BLE Connection Management ------------------------ #

async def connect_to_device(address, device_name):
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
        print(f"Connected to {device_name}")

        connected_clients[address] = client

        def notification_handler(sender, data):
            data_str = data.decode('utf-8')
            print(f"Received from {device_name}: {data_str}")
            asyncio.create_task(process_sensor_data(device_name, data_str))

        characteristic_uuid = CHARACTERISTIC_UUIDS[device_name]
        await client.start_notify(characteristic_uuid, notification_handler)
        print(f"Started notification handler for {device_name}")

        while True:
            await asyncio.sleep(1)
            if not client.is_connected:
                print(f"{device_name} disconnected. Attempting to reconnect...")
                del connected_clients[address]
                await connect_to_device(address, device_name)
    except Exception as e:
        print(f"Failed to connect to {device_name} at {address}: {e}")
        if address in connected_clients:
            del connected_clients[address]
        await asyncio.sleep(5)
        await connect_to_device(address, device_name)


# ------------------------ Data Collection ------------------------ #

last_recorded_timestamp = 0

async def synchronized_data_collector():
    global last_recorded_timestamp
    while True:
        with sensor_values_lock:
            ts1 = sensor_values['ESP32_Sensor_1']['timestamp']
            ts2 = sensor_values['ESP32_Sensor_2']['timestamp']
            if ts1 > last_recorded_timestamp and ts2 > last_recorded_timestamp:
                record_entry_left = {
                    'timestamp': ts1,
                    'Left_Heel': sensor_values['ESP32_Sensor_1']['Left_Heel'],
                    'Left_Middle': sensor_values['ESP32_Sensor_1']['Left_Middle'],
                    'Left_Top': sensor_values['ESP32_Sensor_1']['Left_Top']
                }
                record_entry_right = {
                    'timestamp': ts2,
                    'Right_Heel': sensor_values['ESP32_Sensor_2']['Right_Heel'],
                    'Right_Middle': sensor_values['ESP32_Sensor_2']['Right_Middle'],
                    'Right_Top': sensor_values['ESP32_Sensor_2']['Right_Top']
                }
                with recording_lock:
                    if is_recording:
                        current_recording_left.append(record_entry_left)
                        current_recording_right.append(record_entry_right)
                last_recorded_timestamp = max(ts1, ts2)
        await asyncio.sleep(0.05)


# ------------------------ BLE Client Runner ------------------------ #

async def run_ble_client_main():
    print("Scanning for BLE devices...")
    while True:
        try:
            devices = await BleakScanner.discover()

            tasks = []
            found_addresses = set()

            for device in devices:
                device_name = device.name or device.metadata.get('local_name', '')
                if device_name in DEVICE_NAMES and device.address not in found_addresses:
                    print(f"Found {device_name} at address {device.address}")
                    task = asyncio.create_task(connect_to_device(device.address, device_name))
                    tasks.append(task)
                    found_addresses.add(device.address)

            if not tasks:
                print("No specified ESP32 devices found. Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue

            if not any(task.get_name() == "collector_task" for task in tasks):
                collector_task = asyncio.create_task(synchronized_data_collector())
                collector_task.set_name("collector_task")
                tasks.append(collector_task)

            await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error in BLE client: {e}")
            await asyncio.sleep(5)

def run_ble_client():
    asyncio.run(run_ble_client_main())


# ------------------------ FastAPI Configuration ------------------------ #

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/get_insole_contours")
async def get_insole_contours_endpoint():
    global insole_contours
    if insole_contours is None:
        return JSONResponse(content={"error": "Insole contours not available yet."}, status_code=500)
    else:
        return JSONResponse(content=insole_contours)

@app.get("/get_sensor_values")
async def get_sensor_values():
    with sensor_values_lock:
        flat_values = {
            'Left_Heel': sensor_values['ESP32_Sensor_1']['Left_Heel'],
            'Left_Middle': sensor_values['ESP32_Sensor_1']['Left_Middle'],
            'Left_Top': sensor_values['ESP32_Sensor_1']['Left_Top'],
            'Right_Heel': sensor_values['ESP32_Sensor_2']['Right_Heel'],
            'Right_Middle': sensor_values['ESP32_Sensor_2']['Right_Middle'],
            'Right_Top': sensor_values['ESP32_Sensor_2']['Right_Top']
        }
        return JSONResponse(content=flat_values)


@app.get("/", response_class=HTMLResponse)
async def get():
    # Build the path to index.html in the same directory
    html_file_path = os.path.join(BASE_PATH, "index.html")

    try:
        with open(html_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        return Response(content="index.html not found", media_type="text/plain", status_code=404)

    # Return the content of index.html
    return HTMLResponse(content=html_content, status_code=200)


BASELINE_LEFT_HEEL = 2400

@app.post("/start_recording")
async def start_recording_endpoint(data: dict):
    required_fields = ['name', 'surname', 'height', 'weight', 'gender', 'shoe_size']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing field: {field}")

    name = data['name'].strip()
    surname = data['surname'].strip()
    height = data['height']
    weight = data['weight']
    gender = data['gender']
    shoe_size = data['shoe_size']

    if not name or not surname:
        raise HTTPException(status_code=400, detail="Name and surname cannot be empty.")

    with recording_lock:
        global is_recording, current_recording_left, current_recording_right, user_data
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
        current_recording_left = []
        current_recording_right = []
    return {"status": "Recording started."}

@app.post("/stop_recording")
async def stop_recording_endpoint():
    with recording_lock:
        global is_recording, current_recording_left, current_recording_right, user_data
        if not is_recording:
            raise HTTPException(status_code=400, detail="No recording in progress.")
        is_recording = False
        recording_data_left = current_recording_left.copy()
        recording_data_right = current_recording_right.copy()
        recording_user_data = user_data.copy()
        current_recording_left = []
        current_recording_right = []
        user_data = {}

    try:
        name = recording_user_data['name']
        surname = recording_user_data['surname']
        shoe_size = recording_user_data['shoe_size']
        height = str(recording_user_data['height'])
        weight = str(recording_user_data['weight'])
        gender = recording_user_data['gender']

        filename_left = f"{name}{surname}S{shoe_size}H{height}W{weight}{gender[0].upper()}_Left.csv"
        filename_right = f"{name}{surname}S{shoe_size}H{height}W{weight}{gender[0].upper()}_Right.csv"
        filepath_left = os.path.join(RECORDINGS_DIR, filename_left)
        filepath_right = os.path.join(RECORDINGS_DIR, filename_right)

        with open(filepath_left, mode='w', newline='') as csvfile_left:
            fieldnames_left = ['timestamp', 'Left_Heel', 'Left_Middle', 'Left_Top']
            writer_left = csv.DictWriter(csvfile_left, fieldnames=fieldnames_left)
            writer_left.writeheader()
            for entry in recording_data_left:
                writer_left.writerow(entry)
        print(f"Left recording saved to {filepath_left}")

        with open(filepath_right, mode='w', newline='') as csvfile_right:
            fieldnames_right = ['timestamp', 'Right_Heel', 'Right_Middle', 'Right_Top']
            writer_right = csv.DictWriter(csvfile_right, fieldnames=fieldnames_right)
            writer_right.writeheader()
            for entry in recording_data_right:
                writer_right.writerow(entry)
        print(f"Right recording saved to {filepath_right}")

        combined_filename = f"{name}{surname}S{shoe_size}H{height}W{weight}{gender[0].upper()}_Combined.csv"
        combined_filepath = os.path.join(RECORDINGS_DIR, combined_filename)

        left_data = []
        with open(filepath_left, mode='r', newline='') as csvfile_left:
            reader_left = csv.DictReader(csvfile_left)
            for row in reader_left:
                left_data.append(row)

        right_data = []
        with open(filepath_right, mode='r', newline='') as csvfile_right:
            reader_right = csv.DictReader(csvfile_right)
            for row in reader_right:
                right_data.append(row)

        combined_data = []
        i, j = 0, 0
        while i < len(left_data) and j < len(right_data):
            ts_left = float(left_data[i]['timestamp'])
            ts_right = float(right_data[j]['timestamp'])
            if abs(ts_left - ts_right) < 0.1:
                combined_entry = {
                    'timestamp': ts_left,
                    'Left_Heel': left_data[i]['Left_Heel'],
                    'Left_Middle': left_data[i]['Left_Middle'],
                    'Left_Top': left_data[i]['Left_Top'],
                    'Right_Heel': right_data[j]['Right_Heel'],
                    'Right_Middle': right_data[j]['Right_Middle'],
                    'Right_Top': right_data[j]['Right_Top']
                }
                combined_data.append(combined_entry)
                i += 1
                j += 1
            elif ts_left < ts_right:
                i += 1
            else:
                j += 1

        with open(combined_filepath, mode='w', newline='') as csvfile_combined:
            fieldnames_combined = ['timestamp', 'Left_Heel', 'Left_Middle', 'Left_Top',
                                   'Right_Heel', 'Right_Middle', 'Right_Top']
            writer_combined = csv.DictWriter(csvfile_combined, fieldnames=fieldnames_combined)
            writer_combined.writeheader()
            for entry in combined_data:
                writer_combined.writerow(entry)
        print(f"Combined recording saved to {combined_filepath}")

    except Exception as e:
        print(f"Error saving recordings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save recordings.")

    return {
        "status": "Recording stopped and data saved to CSV files.",
        "left_csv": filename_left,
        "right_csv": filename_right,
        "combined_csv": combined_filename
    }

@app.post("/calibrate_left_heel")
async def calibrate_left_heel_endpoint(data: dict):
    global BASELINE_LEFT_HEEL
    if 'baseline' not in data:
        raise HTTPException(status_code=400, detail="Missing 'baseline' value.")
    try:
        new_baseline = int(data['baseline'])
        BASELINE_LEFT_HEEL = new_baseline
        print(f"Left Heel baseline updated to {BASELINE_LEFT_HEEL}")
        return {"status": f"Left Heel baseline set to {BASELINE_LEFT_HEEL}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid 'baseline' value.")


def run_fastapi():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

async def disconnect_all_clients():
    global connected_clients
    print("Disconnecting all BLE clients...")
    for address, client in connected_clients.items():
        if client.is_connected:
            await client.disconnect()
            print(f"Disconnected from {address}")
    connected_clients.clear()

@app.post("/exit_app")
async def exit_app():
    # 1) Disconnect all BLE clients
    await disconnect_all_clients()

    # 2) Immediately kill the process
    #    Either sys.exit(0) or os._exit(0).
    #    os._exit(0) is more "forceful" — it bypasses cleanup of other threads.
    import os
    os._exit(0)

    # We won't reach a return statement after os._exit(0),
    # but let's keep it for completeness:
    return {"status": "Exiting..."}

@app.get("/visualize", response_class=HTMLResponse)
async def visualize_page():
    # Build the path to visualize.html in the same directory
    visualize_file_path = os.path.join(BASE_PATH, "visualize.html")

    try:
        with open(visualize_file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    except FileNotFoundError:
        return Response(content="visualize.html not found", media_type="text/plain", status_code=404)

    return HTMLResponse(content=html_content, status_code=200)


@app.get("/list_csv_files")
def list_csv_files():
    # Return a JSON list of all CSV filenames in RECORDINGS_DIR
    files = []
    for fname in os.listdir(RECORDINGS_DIR):
        if fname.lower().endswith(".csv"):
            files.append(fname)
    return JSONResponse(files)


@app.get("/get_csv_data")
def get_csv_data(filename: str):
    """
    Expects a query param: /get_csv_data?filename=MyFile.csv
    Reads the CSV from RECORDINGS_DIR and returns JSON array of objects.
    """
    import csv

    file_path = os.path.join(RECORDINGS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    data_rows = []
    with open(file_path, mode='r', newline='') as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            data_rows.append(row)

    # Return as JSON
    return JSONResponse(data_rows)

def main():
    lock_file = 'app.lock'
    with SingleInstance(lock_file):
        global insole_contours
        insole_contours = process_image()
        if insole_contours is None:
            print("Failed to process insole image. Exiting.")
            return

        fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
        fastapi_thread.start()
        print("FastAPI server started.")

        ble_thread = threading.Thread(target=run_ble_client, daemon=True)
        ble_thread.start()
        print("BLE client started.")

        try:
            webview.create_window("Insole Sensor App", "http://127.0.0.1:8000", fullscreen=True)
            webview.start()
        except Exception as e:
            print(f"Error starting webview: {e}")

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