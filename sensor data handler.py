import asyncio
import platform
import matplotlib.pyplot as plt
from bleak import BleakScanner, BleakClient

# Define ESP32 BLE device name
ESP_NAME = "ESP32_Sensor_2"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a9"

# Store sensor data
sensor_data = [[], [], [], []]
time_data = []

# Plot setup
plt.ion()
fig, ax = plt.subplots()
lines = [ax.plot([], [], label=f"Sensor {i+1}")[0] for i in range(4)]
ax.set_xlim(0, 100)
ax.set_ylim(0, 4095)  # ESP32 ADC range
ax.set_xlabel("Time (samples)")
ax.set_ylabel("Sensor Value")
ax.legend()


async def find_esp():
    """Scan for ESP32 device."""
    print("Scanning for ESP32 device...")
    devices = await BleakScanner.discover()
    for device in devices:
        if device.name == ESP_NAME:
            print(f"Found {ESP_NAME} at {device.address}")
            return device.address
    print("ESP32 not found!")
    return None


async def notification_handler(sender, data):
    """Handle BLE notifications."""
    global sensor_data, time_data
    try:
        values = data.decode("utf-8").split(",")
        if len(values) == 4:
            values = [int(v) for v in values]
            time_data.append(len(time_data))
            for i in range(4):
                sensor_data[i].append(values[i])
            if len(time_data) > 100:
                time_data.pop(0)
                for i in range(4):
                    sensor_data[i].pop(0)
            for i in range(4):
                lines[i].set_xdata(time_data)
                lines[i].set_ydata(sensor_data[i])
            ax.relim()
            ax.autoscale_view()
            plt.draw()
            plt.pause(0.01)
    except Exception as e:
        print(f"Error parsing data: {e}")


async def main():
    """Scan, connect, and receive data from ESP32."""
    esp_address = await find_esp()
    if not esp_address:
        return
    async with BleakClient(esp_address) as client:
        if await client.is_connected():
            print(f"Connected to {ESP_NAME}")
            await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            while True:
                await asyncio.sleep(1)


# ✅ Windows-friendly execution fix
if __name__ == "__main__":
    if platform.system() == "Windows":
        loop = asyncio.ProactorEventLoop()  # Windows-specific event loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    else:
        asyncio.run(main())  # Normal execution for Linux/macOS
