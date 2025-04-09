import asyncio
import struct
import websockets
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

class ESP32Connection:
    def __init__(self, device_name):
        self.device_name = device_name
        self.client = None
        self.connected = False
        self.data_queue = asyncio.Queue()

    async def find_device(self):
        """Scan for the device by its exact name"""
        print(f"🔍 Scanning for {self.device_name}...")
        try:
            devices = await BleakScanner.discover(timeout=5.0)
            for d in devices:
                if d.name == self.device_name:
                    print(f"✅ Found {self.device_name} at {d.address}")
                    return d.address
            print(f"❌ {self.device_name} not found")
            return None
        except Exception as e:
            print(f"⚠️ Scan error for {self.device_name}: {e}")
            return None

    async def connect(self):
        """Establish BLE connection"""
        address = await self.find_device()
        if not address:
            return False

        self.client = BleakClient(address)
        try:
            await self.client.connect()
            self.connected = True
            print(f"🔗 Connected to {self.device_name}")
            return True
        except Exception as e:
            print(f"⚠️ Connection error to {self.device_name}: {e}")
            return False

    async def read_data(self):
        """Continuously read data and print to console"""
        if not self.connected:
            print(f"⚠️ {self.device_name} not connected")
            return

        print(f"📶 Starting data read from {self.device_name}")
        while self.connected:
            try:
                raw_data = await self.client.read_gatt_char(DATA_CHARACTERISTIC_UUID)
                if len(raw_data) == 22:
                    data_tuple = struct.unpack("<hhhhhhhhhhh", raw_data)
                    msg = (
                        f"{self.device_name} => "
                        f"s1:{data_tuple[0]}, s2:{data_tuple[1]}, s3:{data_tuple[2]}, s4:{data_tuple[3]}, "
                        f"avg1:{data_tuple[4]}, avg2:{data_tuple[5]}, avg3:{data_tuple[6]}, avg4:{data_tuple[7]}, "
                        f"ang1:{data_tuple[8]}, ang2:{data_tuple[9]}, ang3:{data_tuple[10]}"
                    )
                    print(msg)
                    await self.data_queue.put(msg)
                else:
                    print(f"⚠️ {self.device_name} returned {len(raw_data)} bytes (expected 22)")
            except Exception as e:
                print(f"⚠️ Read error from {self.device_name}: {e}")
                self.connected = False
            await asyncio.sleep(0.01)

    async def disconnect(self):
        """Disconnect from device"""
        if self.connected and self.client:
            await self.client.disconnect()
            self.connected = False
            print(f"🔴 Disconnected from {self.device_name}")

async def connect_and_read_esp32():
    """Connect to both ESP32 devices and start reading data"""
    esp1 = ESP32Connection(DEVICE_1_NAME)
    esp2 = ESP32Connection(DEVICE_2_NAME)

    # Connect to both devices first
    connected1 = await esp1.connect()
    connected2 = await esp2.connect()

    if not connected1 and not connected2:
        print("💥 Failed to connect to both devices")
        return None, None

    # Start reading data from connected devices
    if connected1:
        asyncio.create_task(esp1.read_data())
    if connected2:
        asyncio.create_task(esp2.read_data())

    return esp1, esp2


async def websocket_handler(websocket, path):
    """Handle WebSocket connections and forward data"""
    remote_address = websocket.remote_address
    print(f"🔌 New WebSocket connection from {remote_address}")

    try:
        # Send initial connection acknowledgement
        await websocket.send("CONNECTION_ESTABLISHED")

        while True:
            # Check if we have ESP data to send
            if esp1 and esp1.connected:
                try:
                    msg = await asyncio.wait_for(esp1.data_queue.get(), timeout=0.1)
                    await websocket.send(msg)
                except asyncio.TimeoutError:
                    pass

            if esp2 and esp2.connected:
                try:
                    msg = await asyncio.wait_for(esp2.data_queue.get(), timeout=0.1)
                    await websocket.send(msg)
                except asyncio.TimeoutError:
                    pass

            await asyncio.sleep(0.01)

    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 WebSocket connection closed from {remote_address}")
    except Exception as e:
        print(f"⚠️ WebSocket error from {remote_address}: {e}")


async def main():
    """Main program flow"""
    # Step 1: Connect to ESP32 devices
    print("🔄 Connecting to ESP32 devices...")
    global esp1, esp2
    esp1, esp2 = await connect_and_read_esp32()

    # Step 2: Start WebSocket server
    if esp1 or esp2:
        print("🚀 Starting WebSocket server...")
        async with websockets.serve(
                websocket_handler,
                "localhost",
                8765,
                ping_interval=20,
                ping_timeout=40,
                close_timeout=1
        ):
            print("🌐 WebSocket server running at ws://localhost:8765")
            await asyncio.Future()  # Run forever
    else:
        print("💥 No devices connected, exiting")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Server stopped by user")
    except Exception as e:
        print(f"💥 Critical error: {e}")