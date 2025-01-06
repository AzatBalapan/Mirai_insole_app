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
from starlette.staticfiles import StaticFiles

if hasattr(sys, '_MEIPASS'):
    BASE_PATH = sys._MEIPASS
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

static_path = os.path.join(BASE_PATH, 'static')
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


@app.get("/")
async def get():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Insole Sensor Visualization</title>
        <style>
            body {
                margin: 0;
                padding: 20px;
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
            }

            .navbar {
                width: 100%;
                background-color: #243c6b;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 10px 20px;
                color: white;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                box-sizing: border-box;
            }
            .navbar-logo {
                display: flex;
                align-items: center;
            }
            .navbar-logo img {
                height: 40px;
                margin-right: 15px;
            }
            .navbar-links {
                display: flex;
                gap: 20px;
            }
            .navbar-links a {
                color: white;
                text-decoration: none;
                font-size: 16px;
                transition: color 0.3s;
            }
            .navbar-links a:hover {
                color: #ffc107;
            }

            h1 {
                color: #333;
                text-align: center;
                margin-bottom: 15px;
            }

            #instructions {
                text-align: center;
                max-width: 1000px;
                margin: 0 auto 20px auto;
                color: #555;
            }

            .layout-container {
                display: flex;
                flex-direction: row;
                justify-content: center;
                align-items: flex-start;
                gap: 20px;
                max-width: 1400px;
                margin: 20px auto;
            }

            .left-chart, .right-chart {
                width: 300px;
                display: flex;
                flex-direction: column;
                gap: 20px;
            }

            /* Chart containers */
            .chart-container {
                width: 300px;
                height: 400px;
            }

            #insoleSvg {
                width: 600px;
                height: 600px;
                border: 1px solid #ccc;
                border-radius: 8px;
                background-color: white;
            }

            .form-container {
                display: flex;
                flex-direction: column;
                align-items: center;
                max-width: 900px;
                width: 100%;
                background-color: #fff;
                padding: 15px;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                margin: 20px auto 0 auto;
            }
            .form-row {
                display: flex;
                gap: 10px;
                width: 100%;
                margin-bottom: 10px;
            }
            input, select {
                padding: 8px;
                font-size: 14px;
                width: 100%;
                box-sizing: border-box;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
            .input-group {
                flex: 1;
            }
            #recordButton {
                padding: 10px 15px;
                font-size: 16px;
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                width: 100%;
                margin-top: 8px;
            }
            #recordButton.stop {
                background-color: #dc3545;
            }
            #recordButton:hover {
                opacity: 0.9;
            }

            /* Asymmetry display */
            #asymmetry-display {
                text-align:center; 
                font-size:16px; 
                margin-top:20px; 
                margin-bottom:20px;
            }
        </style>
    </head>
    <body>
        <div class="navbar">
            <div class="navbar-logo">
                <img src="/static/logo.jpeg" alt="Logo">
                <span>Insole Sensor App</span>
            </div>
            <div class="navbar-links">
                <a href="#about">About Us</a>
                <a href="#faq">FAQ</a>
                <a href="#contact">Contact</a>
            </div>
        </div>

        <div class="layout-container">
            <div class="left-chart">
                <canvas id="sensorGraph1" class="chart-container"></canvas>
            </div>
            <svg id="insoleSvg"></svg>
            <div class="right-chart">
                <canvas id="sensorGraph2" class="chart-container"></canvas>
            </div>
        </div>

        <!-- Asymmetry display below insoles and above the form -->
        <div id="asymmetry-display">
            Asymmetry: <span id="asymmetry-value">Calculating...</span>
        </div>

        <div class="form-container">
            <form id="userForm">
                <div class="form-row">
                    <div class="input-group">
                        <label for="name">Name:</label>
                        <input type="text" id="name" placeholder="Enter your name" required>
                    </div>
                    <div class="input-group">
                        <label for="surname">Surname:</label>
                        <input type="text" id="surname" placeholder="Enter your surname" required>
                    </div>
                    <div class="input-group">
                        <label for="height">Height (cm):</label>
                        <input type="number" id="height" placeholder="Enter your height" required>
                    </div>
                </div>
                <div class="form-row">
                    <div class="input-group">
                        <label for="weight">Weight (kg):</label>
                        <input type="number" id="weight" placeholder="Enter your weight" required>
                    </div>
                    <div class="input-group">
                        <label for="gender">Gender:</label>
                        <select id="gender" required>
                            <option value="" disabled selected>Select your gender</option>
                            <option value="Male">Male</option>
                            <option value="Female">Female</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                    <div class="input-group">
                        <label for="shoe_size">Shoe Size:</label>
                        <input type="number" id="shoe_size" placeholder="Enter your shoe size" required>
                    </div>
                </div>
                <button id="recordButton">Start Recording</button>
            </form>
        </div>

        <script src="/static/d3.v6.min.js"></script>
        <script src="/static/chart.min.js"></script>
        <script>
            var maxDataPoints = 50;

            var insoleContours;
            var sensorValuesLeft = {
                'Left_Heel': 0,
                'Left_Middle': 0,
                'Left_Top': 0
            };
            var sensorValuesRight = {
                'Right_Heel': 0,
                'Right_Middle': 0,
                'Right_Top': 0
            };
            var timeLeft = 0;
            var timeRight = 0;

            var sensorDataLeft = {
                labels: [],
                datasets: [
                    { label: 'Left_Heel', data: [], borderColor: 'red', fill: false },
                    { label: 'Left_Middle', data: [], borderColor: 'green', fill: false },
                    { label: 'Left_Top', data: [], borderColor: 'blue', fill: false }
                ]
            };
            var sensorDataRight = {
                labels: [],
                datasets: [
                    { label: 'Right_Heel', data: [], borderColor: 'red', fill: false },
                    { label: 'Right_Middle', data: [], borderColor: 'green', fill: false },
                    { label: 'Right_Top', data: [], borderColor: 'blue', fill: false }
                ]
            };

            var ctxLeft = document.getElementById('sensorGraph1').getContext('2d');
            var chartLeft = new Chart(ctxLeft, {
                type: 'line',
                data: sensorDataLeft,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    scales: {
                        x: { display: true, title: { display: true, text: 'Time' } },
                        y: { display: true, title: { display: true, text: 'Sensor Value' }, min: 0, max: 4095 }
                    }
                }
            });

            var ctxRight = document.getElementById('sensorGraph2').getContext('2d');
            var chartRight = new Chart(ctxRight, {
                type: 'line',
                data: sensorDataRight,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    scales: {
                        x: { display: true, title: { display: true, text: 'Time' } },
                        y: { display: true, title: { display: true, text: 'Sensor Value' }, min: 0, max: 4095 }
                    }
                }
            });

            function fetchInsoleContours() {
                fetch('/get_insole_contours')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        console.error('Error:', data.error);
                        return;
                    }
                    insoleContours = data;
                    drawInsoleContours();
                })
                .catch(error => {
                    console.error('Error fetching insole contours:', error);
                });
            }

            function drawInsoleContours() {
                var svg = d3.select('#insoleSvg');
                svg.selectAll("*").remove();

                var allPoints = [];
                for (var side in insoleContours) {
                    for (var partName in insoleContours[side]) {
                        var points = insoleContours[side][partName];
                        allPoints = allPoints.concat(points);
                    }
                }

                if (allPoints.length === 0) {
                    console.error('No insole contours found.');
                    return;
                }

                var xExtent = d3.extent(allPoints, function(d) { return d[0]; });
                var yExtent = d3.extent(allPoints, function(d) { return d[1]; });

                var margin = 90;
                var width = 600;
                var height = 600;
                var xRange = [margin, width - margin];
                var yRange = [margin, height - margin];

                var xScale = d3.scaleLinear()
                    .domain(xExtent)
                    .range(xRange);

                var yScale = d3.scaleLinear()
                    .domain(yExtent)
                    .range(yRange);

                for (var side in insoleContours) {
                    for (var partName in insoleContours[side]) {
                        var points = insoleContours[side][partName];
                        if (points.length === 0) continue;
                        var scaledPoints = points.map(function(d) {
                            return [xScale(d[0]), yScale(d[1])];
                        });
                        var pathData = d3.line()(scaledPoints) + 'Z';

                        svg.append('path')
                            .attr('id', partName)
                            .attr('d', pathData)
                            .attr('fill', 'white')
                            .attr('stroke', 'black')
                            .attr('stroke-width', 1);
                    }
                }
            }

            function updateInsoleColors() {
                var colorScale = d3.scaleLinear()
                    .domain([0, 4095])
                    .range(['white', 'red']);

                for (var key in sensorValuesLeft) {
                    var value = sensorValuesLeft[key];
                    var color = colorScale(value);
                    var element = d3.select('#' + key);
                    if (!element.empty()) {
                        element.attr('fill', color);
                    }
                }

                for (var key in sensorValuesRight) {
                    var value = sensorValuesRight[key];
                    var color = colorScale(value);
                    var element = d3.select('#' + key);
                    if (!element.empty()) {
                        element.attr('fill', color);
                    }
                }
            }

            // Asymmetry calculation variables
            var iterationCount = 0;
            var maxIterationsForAsymmetry = 300;
            var leftLoads = [];
            var rightLoads = [];

            function computeAsymmetry() {
                if (leftLoads.length < maxIterationsForAsymmetry || rightLoads.length < maxIterationsForAsymmetry) {
                    return;
                }

                var sumLeft = 0;
                var sumRight = 0;
                for (var i = 0; i < maxIterationsForAsymmetry; i++) {
                    sumLeft += leftLoads[i];
                    sumRight += rightLoads[i];
                }

                var avgLeft = sumLeft / maxIterationsForAsymmetry;
                var avgRight = sumRight / maxIterationsForAsymmetry;

                var asymmetry = 0;
                if ((avgLeft + avgRight) !== 0) {
                    asymmetry = (Math.abs(avgLeft - avgRight) / ((avgLeft + avgRight) / 2)) * 100;
                }

                document.getElementById('asymmetry-value').textContent = asymmetry.toFixed(2) + "%";

                leftLoads = [];
                rightLoads = [];
                iterationCount = 0;
            }

            function fetchSensorValues() {
                fetch('/get_sensor_values')
                .then(response => response.json())
                .then(data => {
                    sensorValuesLeft = {
                        'Left_Heel': data['Left_Heel'],
                        'Left_Middle': data['Left_Middle'],
                        'Left_Top': data['Left_Top']
                    };
                    sensorValuesRight = {
                        'Right_Heel': data['Right_Heel'],
                        'Right_Middle': data['Right_Middle'],
                        'Right_Top': data['Right_Top']
                    };
                    updateInsoleColors();
                    updateCharts();

                    // Add loads for asymmetry calculation
                    var leftLoad = sensorValuesLeft['Left_Heel'] + sensorValuesLeft['Left_Middle'] + sensorValuesLeft['Left_Top'];
                    var rightLoad = sensorValuesRight['Right_Heel'] + sensorValuesRight['Right_Middle'] + sensorValuesRight['Right_Top'];

                    leftLoads.push(leftLoad);
                    rightLoads.push(rightLoad);
                    iterationCount++;

                    if (iterationCount >= maxIterationsForAsymmetry) {
                        computeAsymmetry();
                    }
                })
                .catch(error => {
                    console.error('Error fetching sensor values:', error);
                });
            }

            function updateCharts() {
                timeLeft += 1;
                sensorDataLeft.labels.push(timeLeft);
                sensorDataLeft.datasets[0].data.push(sensorValuesLeft['Left_Heel']);
                sensorDataLeft.datasets[1].data.push(sensorValuesLeft['Left_Middle']);
                sensorDataLeft.datasets[2].data.push(sensorValuesLeft['Left_Top']);

                timeRight += 1;
                sensorDataRight.labels.push(timeRight);
                sensorDataRight.datasets[0].data.push(sensorValuesRight['Right_Heel']);
                sensorDataRight.datasets[1].data.push(sensorValuesRight['Right_Middle']);
                sensorDataRight.datasets[2].data.push(sensorValuesRight['Right_Top']);

                if (sensorDataLeft.labels.length > maxDataPoints) {
                    sensorDataLeft.labels.shift();
                    sensorDataRight.labels.shift();
                    sensorDataLeft.datasets.forEach(dataset => dataset.data.shift());
                    sensorDataRight.datasets.forEach(dataset => dataset.data.shift());
                }

                chartLeft.update();
                chartRight.update();
            }

            fetchInsoleContours();
            setInterval(fetchSensorValues, 100);

            var isRecording = false;
            var recordButton = document.getElementById("recordButton");

            recordButton.addEventListener("click", function(event) {
                event.preventDefault();
                if (!isRecording) {
                    var name = document.getElementById("name").value.trim();
                    var surname = document.getElementById("surname").value.trim();
                    var height = document.getElementById("height").value;
                    var weight = document.getElementById("weight").value;
                    var gender = document.getElementById("gender").value;
                    var shoe_size = document.getElementById("shoe_size").value;

                    if (name && surname && height && weight && gender && shoe_size) {
                        startRecording(name, surname, height, weight, gender, shoe_size);
                        isRecording = true;
                        recordButton.textContent = "Stop Recording";
                        recordButton.classList.add("stop");
                        document.querySelectorAll('#userForm input, #userForm select').forEach(elem => elem.disabled = true);
                    } else {
                        alert("Please fill in all the fields.");
                    }
                } else {
                    stopRecording();
                    isRecording = false;
                    recordButton.textContent = "Start Recording";
                    recordButton.classList.remove("stop");
                    document.querySelectorAll('#userForm input, #userForm select').forEach(elem => elem.disabled = false);
                }
            });

            function startRecording(name, surname, height, weight, gender, shoe_size) {
                fetch('/start_recording', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: name,
                        surname: surname,
                        height: height,
                        weight: weight,
                        gender: gender,
                        shoe_size: shoe_size
                    })
                })
                .then(response => response.json())
                .then(data => {
                    console.log("Recording started:", data);
                })
                .catch(error => {
                    console.error("Error starting recording:", error);
                });
            }

            function stopRecording() {
                fetch('/stop_recording', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    console.log("Recording stopped:", data);
                    alert("Recording stopped. Data saved to CSV.");
                })
                .catch(error => {
                    console.error("Error stopping recording:", error);
                });
            }

        </script>
    </body>
    </html>
    """
    return Response(content=html_content, media_type="text/html")


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
