import asyncio
import struct
import websockets
import threading
import webbrowser
from bleak import BleakClient, BleakScanner

#####################################
# BLE UUIDs from the Arduino code
#####################################
SERVICE_UUID = "4fafc202-1fb5-459e-8fcc-c5c9c331914c"
DATA_CHARACTERISTIC_UUID = "beb5483f-36e1-4688-b7f5-ea07361b26a9"

#####################################
# Device Names
#####################################
DEVICE_1_NAME = "ESP32_Sensor_1"
DEVICE_2_NAME = "ESP32_Sensor_2"

HTML_FILE_PATH = "static\\skeletal_structure.html"


def open_html():
    """Open the local HTML file in the browser."""
    webbrowser.open(HTML_FILE_PATH)


async def find_esp32(device_name: str):
    """Scan for a device by its exact name, return its address if found."""
    print(f"Scanning for {device_name}...")
    devices = await BleakScanner.discover()
    for d in devices:
        if d.name == device_name:
            print(f"✅ Found {device_name} at {d.address}")
            return d.address
    print(f"❌ {device_name} not found. Make sure it's advertising.")
    return None


async def read_sensor_data_loop(client: BleakClient, device_name: str, sensor_id: int, websocket):
    """
    Continuously read the data characteristic from the device and
    forward it over the WebSocket every ~0.01 seconds.

    The new Arduino code sends 11 short values = 22 bytes total.
    """
    while True:
        try:
            raw_data = await client.read_gatt_char(DATA_CHARACTERISTIC_UUID)
            # Expect 22 bytes: 11 * 2
            if len(raw_data) == 22:
                # Unpack 11 short values, little-endian
                # (sensor1, sensor2, sensor3, sensor4, avg1, avg2, avg3, avg4, angle1, angle2, angle3)
                data_tuple = struct.unpack("<hhhhhhhhhhh", raw_data)
                s1, s2, s3, s4, avg1, avg2, avg3, avg4, ang1, ang2, ang3 = data_tuple

                # Build a message string
                msg = (
                    f"SENSOR{sensor_id} => "
                    f"s1:{s1}, s2:{s2}, s3:{s3}, s4:{s4}, "
                    f"avg1:{avg1}, avg2:{avg2}, avg3:{avg3}, avg4:{avg4}, "
                    f"ang1:{ang1}, ang2:{ang2}, ang3:{ang3}"
                )
                print(f"📡 {device_name}: {msg}")

                # Send over WebSocket
                await websocket.send(msg)
            else:
                print(f"⚠ {device_name} returned {len(raw_data)} bytes (expected 22). Ignoring.")
        except Exception as e:
            print(f"Read error from {device_name}: {e}")
            break  # Exit loop on read error

        await asyncio.sleep(0.01)  # Poll interval


async def connect_and_poll(device_name: str, websocket, sensor_id: int):
    """
    Finds the device, connects via BLE, then polls for data in a loop.
    """
    address = await find_esp32(device_name)
    if not address:
        return  # Could not find device

    client = BleakClient(address)
    try:
        print(f"🔗 Connecting to {device_name} ({address})...")
        await client.connect()

        # Now that we're connected, read in a loop
        await read_sensor_data_loop(client, device_name, sensor_id, websocket)

    except Exception as e:
        print(f"❌ Connection error with {device_name}: {e}")
    finally:
        if client.is_connected:
            print(f"🔴 Disconnecting from {device_name}")
            await client.disconnect()


async def ble_to_websocket(websocket):
    """
    Called once per WebSocket client connection. We spawn tasks to connect to
    two ESP32 devices and poll them in parallel.
    """
    tasks = [
        asyncio.create_task(connect_and_poll(DEVICE_1_NAME, websocket, 1)),
        asyncio.create_task(connect_and_poll(DEVICE_2_NAME, websocket, 2))
    ]
    await asyncio.gather(*tasks)  # Wait for both tasks


async def websocket_server():
    """Start a WebSocket server at ws://localhost:8765."""
    async with websockets.serve(ble_to_websocket, "localhost", 8765):
        print("🚀 WebSocket server running at ws://localhost:8765")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    # (Optional) automatically open the local HTML file
    threading.Thread(target=open_html, daemon=True).start()

    # Start the WebSocket server
    asyncio.run(websocket_server())
