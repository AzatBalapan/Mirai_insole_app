import asyncio
import struct
import websockets
import threading
import webbrowser
from bleak import BleakClient, BleakScanner

# UUIDs for the first ESP32 (must match your ESP32 service & characteristic UUIDs)
SERVICE_UUID_1 = "4fafc201-1fb5-459e-8fcc-c5c9c331914c"
CHARACTERISTIC_UUID_1 = "beb5483e-36e1-4688-b7f5-ea07361b26a9"

# UUIDs for the second ESP32
SERVICE_UUID_2 = "4fafc202-1fb5-459e-8fcc-c5c9c331914c"  # Different service UUID
CHARACTERISTIC_UUID_2 = "beb5483f-36e1-4688-b7f5-ea07361b26a9"  # Different characteristic UUID

# Path to HTML file
HTML_FILE_PATH = "static\\skeletal_structure.html"

def open_html():
    webbrowser.open(HTML_FILE_PATH)

async def find_esp32(device_name):
    print(f"Scanning for {device_name} BLE device...")
    devices = await BleakScanner.discover()

    for device in devices:
        if device_name in device.name:  # Adjust based on ESP32 BLE name
            print(f"✅ Found {device_name}: {device.name} [{device.address}]")
            return device.address

    print(f"❌ {device_name} not found. Make sure it's advertising.")
    return None

async def ble_to_websocket(websocket):
    esp32_address_1 = await find_esp32("ESP32_MPU6050")
    esp32_address_2 = await find_esp32("ESP32_MPU6050_2")

    if not esp32_address_1 or not esp32_address_2:
        return

    async with BleakClient(esp32_address_1) as client1, BleakClient(esp32_address_2) as client2:
        print(f"🔗 Connected to {esp32_address_1} and {esp32_address_2}")

        async def notification_handler_1(sender, data):
            if len(data) == 6:  # Ensure 6 bytes are received
                roll, pitch, yaw = struct.unpack('<hhh', data)  # Little Endian
                print(f"📡 Sending Roll from Sensor 1: {roll} to WebSocket")
                await websocket.send(f"SENSOR1:{roll}")  # Send roll as string with identifier

        async def notification_handler_2(sender, data):
            if len(data) == 6:  # Ensure 6 bytes are received
                roll, pitch, yaw = struct.unpack('<hhh', data)  # Little Endian
                print(f"📡 Sending Roll from Sensor 2: {roll} to WebSocket")
                await websocket.send(f"SENSOR2:{roll}")  # Send roll as string with identifier

        await client1.start_notify(CHARACTERISTIC_UUID_1, notification_handler_1)
        await client2.start_notify(CHARACTERISTIC_UUID_2, notification_handler_2)
        print("✅ Listening for BLE notifications... Press Ctrl+C to stop.")

        try:
            while True:
                await asyncio.sleep(1)  # Keep script running
        except KeyboardInterrupt:
            print("🔴 Stopping BLE clients...")
            await client1.stop_notify(CHARACTERISTIC_UUID_1)
            await client2.stop_notify(CHARACTERISTIC_UUID_2)

async def websocket_server():
    async with websockets.serve(ble_to_websocket, "localhost", 8765):
        print("🚀 WebSocket Server started at ws://localhost:8765")
        await asyncio.Future()  # Keep the server running

# Open HTML file in browser
threading.Thread(target=open_html, daemon=True).start()

# Run WebSocket Server
asyncio.run(websocket_server())