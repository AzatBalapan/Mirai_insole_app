import asyncio
from bleak import BleakClient, BleakScanner
import json

# Define all ESP32 device names and UUIDs
ESP32_SENSORS = {
    "ESP32_BNO055": "b8a40475-5c37-40f1-b1d4-f83bb3e0dc4a",
    "ESP32_BNO055_2": "7e2b60c5-ef12-47fc-b897-6d2db96fefcb",
    "ESP32_BNO055_3": "f2417a16-06da-4733-a71e-31b9a97a19d6",
    "ESP32_BNO055_4": "3b65a9be-7e7d-44f2-bd1a-5a4a1db25716",
    "ESP32_BNO055_5": "1b27bc3f-3f0b-42b1-b832-73ea58b4bce7",
    "ESP32_BNO055_6": "c37454cb-7586-4fc8-9d09-dcbd96a85d2c"
}

sensor_addresses = {}


async def find_esp32_sensors():
    """Scan for all ESP32 sensors and store their addresses."""
    print("🔍 Scanning for ESP32 sensors...")
    devices = await BleakScanner.discover()

    for device in devices:
        if device.name and device.name in ESP32_SENSORS:
            sensor_addresses[device.name] = device.address
            print(f"✅ Found {device.name} at {device.address}")

    if not sensor_addresses:
        print("❌ No ESP32 sensors found. Ensure they are powered and advertising.")
    else:
        print(f"📡 Found {len(sensor_addresses)} ESP32 sensors.")


async def handle_data(sensor_name, sender, data):
    """Process incoming BLE data from a sensor."""
    try:
        decoded_data = data.decode("utf-8")
        values = decoded_data.split(",")

        # Ensure correct number of values (3 angles: yaw, pitch, roll)
        if len(values) == 3:
            yaw, pitch, roll = map(float, values)
            print(f"📡 {sensor_name}: Yaw={yaw:.2f}°, Pitch={pitch:.2f}°, Roll={roll:.2f}°")
        else:
            print(f"⚠️ Invalid data from {sensor_name}: {decoded_data}")

    except Exception as e:
        print(f"⚠️ Error parsing data from {sensor_name}: {e}")


async def connect_and_read():
    """Connect to all found sensors and read data."""
    if not sensor_addresses:
        print("❌ No ESP32 sensors found. Run scan first.")
        return

    # List of async tasks for each sensor
    tasks = []
    for sensor_name, address in sensor_addresses.items():
        async def read_sensor(name, addr):
            async with BleakClient(addr) as client:
                print(f"🔄 Connected to {name} ({addr}). Subscribing to notifications...")
                await client.start_notify(ESP32_SENSORS[name], lambda s, d: handle_data(name, s, d))
                while True:
                    await asyncio.sleep(1)  # Keep connection alive

        tasks.append(read_sensor(sensor_name, address))

    await asyncio.gather(*tasks)


# Run the async process
async def main():
    await find_esp32_sensors()
    if sensor_addresses:
        await connect_and_read()


asyncio.run(main())
