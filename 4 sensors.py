import asyncio
import json
from bleak import BleakScanner, BleakClient
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# BLE Device Names (Ensure these match your ESP32 BLE advertising names)
ESP1_NAME = "ESP32_Sensor_1"
ESP2_NAME = "ESP32_Sensor_2"

# BLE Characteristic UUIDs (Must match ESP32 firmware)
CHARACTERISTIC_UUID_1 = "beb5483e-36e1-4688-b7f5-ea07361b26a8"  # ESP32_Sensor_1
CHARACTERISTIC_UUID_2 = "beb5483e-36e1-4688-b7f5-ea07361b26a9"  # ESP32_Sensor_2

# Data storage for plotting
sensor_data = {f"sensor{i}": [] for i in range(1, 9)}
time_steps = list(range(100))  # Store last 100 data points for each sensor

# Device addresses (Updated dynamically)
esp1_address = None
esp2_address = None
client1 = None
client2 = None

# Function to handle BLE notifications
def notification_handler(device_id):
    def handle_data(sender, data):
        try:
            json_data = json.loads(data.decode("utf-8"))

            if device_id == 1:
                sensor_data["sensor1"].append(json_data["sensor1"])
                sensor_data["sensor2"].append(json_data["sensor2"])
                sensor_data["sensor3"].append(json_data["sensor3"])
                sensor_data["sensor4"].append(json_data["sensor4"])
            else:
                sensor_data["sensor5"].append(json_data["sensor1"])  # Map to sensor5-8
                sensor_data["sensor6"].append(json_data["sensor2"])
                sensor_data["sensor7"].append(json_data["sensor3"])
                sensor_data["sensor8"].append(json_data["sensor4"])

            # Maintain only last 100 data points
            for key in sensor_data:
                if len(sensor_data[key]) > 100:
                    sensor_data[key].pop(0)

        except json.JSONDecodeError:
            print(f"❌ Error decoding JSON from Device {device_id}")

    return handle_data

# Function to scan and get BLE device addresses by name
async def find_ble_devices():
    global esp1_address, esp2_address
    print("🔍 Scanning for ESP32 devices...")
    devices = await BleakScanner.discover()

    for device in devices:
        print(f"📡 Found device: {device.name} - {device.address}")  # Debugging output
        if device.name == ESP1_NAME:
            esp1_address = device.address
            print(f"✅ Found {ESP1_NAME} at {esp1_address}")
        elif device.name == ESP2_NAME:
            esp2_address = device.address
            print(f"✅ Found {ESP2_NAME} at {esp2_address}")

    if not esp1_address and not esp2_address:
        print("❌ ERROR: No ESP32 devices found. Retrying in 5 seconds...")
        await asyncio.sleep(5)
        await find_ble_devices()  # Recursive retry

# Function to connect to BLE devices independently
async def connect_ble():
    global client1, client2
    await find_ble_devices()  # Find available ESP32s

    if esp1_address:
        try:
            client1 = BleakClient(esp1_address)
            await client1.connect()
            if await client1.is_connected():
                print(f"✅ Connected to {ESP1_NAME}")
                await client1.start_notify(CHARACTERISTIC_UUID_1, notification_handler(1))
        except Exception as e:
            print(f"❌ Failed to connect to {ESP1_NAME}: {e}")

    if esp2_address:
        try:
            client2 = BleakClient(esp2_address)
            await client2.connect()
            if await client2.is_connected():
                print(f"✅ Connected to {ESP2_NAME}")
                await client2.start_notify(CHARACTERISTIC_UUID_2, notification_handler(2))
        except Exception as e:
            print(f"❌ Failed to connect to {ESP2_NAME}: {e}")

    while True:
        await asyncio.sleep(1)  # Keep BLE loop running

# Function to update the plot
def update_plot(frame):
    plt.clf()
    plt.suptitle("Real-Time Sensor Data from ESP32 Sensors")

    # Plot sensor values if device 1 is connected
    if client1 and client1.is_connected:
        plt.subplot(4, 2, 1)
        plt.plot(sensor_data["sensor1"], label="ESP1 Sensor 1")
        plt.legend()
        plt.subplot(4, 2, 2)
        plt.plot(sensor_data["sensor2"], label="ESP1 Sensor 2")
        plt.legend()
        plt.subplot(4, 2, 3)
        plt.plot(sensor_data["sensor3"], label="ESP1 Sensor 3")
        plt.legend()
        plt.subplot(4, 2, 4)
        plt.plot(sensor_data["sensor4"], label="ESP1 Sensor 4")
        plt.legend()

    # Plot sensor values if device 2 is connected
    if client2 and client2.is_connected:
        plt.subplot(4, 2, 5)
        plt.plot(sensor_data["sensor5"], label="ESP2 Sensor 1")
        plt.legend()
        plt.subplot(4, 2, 6)
        plt.plot(sensor_data["sensor6"], label="ESP2 Sensor 2")
        plt.legend()
        plt.subplot(4, 2, 7)
        plt.plot(sensor_data["sensor7"], label="ESP2 Sensor 3")
        plt.legend()
        plt.subplot(4, 2, 8)
        plt.plot(sensor_data["sensor8"], label="ESP2 Sensor 4")
        plt.legend()

# Start BLE loop in background
loop = asyncio.get_event_loop()
loop.create_task(connect_ble())

# Setup Matplotlib animation
fig = plt.figure(figsize=(10, 8))
ani = animation.FuncAnimation(fig, update_plot, interval=100)
plt.show()
