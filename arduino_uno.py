import serial
import time
import threading

# Update these COM ports to match your devices
COM_PORT_1 = "COM13"  # First Arduino's Bluetooth COM port
COM_PORT_2 = "COM14"  # Second Arduino's Bluetooth COM port
BAUD_RATE = 9600  # Ensure this matches the Arduino baud rate


# Function to open serial connection with timeout
def open_serial_connection(port):
    try:
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1)  # Set a small timeout to avoid blocking
        print(f"✅ Connected to {port} at {BAUD_RATE} baud")
        return ser
    except serial.SerialException as e:
        print(f"❌ Error: Could not open {port}. Check if the device is connected.\n{e}")
        return None


# Thread function to continuously read data from a serial device
def read_from_serial(ser, source):
    try:
        while True:
            try:
                data = ser.readline().strip()  # Read a line and strip whitespace
                if data:  # Only process non-empty data
                    print(f"📡 Message from {source}: {data.decode('utf-8', errors='ignore')}")
            except serial.SerialException:
                print(f"⚠️ Connection lost for {source}. Retrying...")
                ser.close()
                time.sleep(2)
                ser = open_serial_connection(ser.port)  # Try to reconnect
            time.sleep(0.05)  # Small delay to prevent excessive CPU usage
    except KeyboardInterrupt:
        print(f"\n🛑 Stopping {source}...")
    finally:
        ser.close()
        print(f"🔌 Serial connection closed for {source}")


# Main function to run both threads
def main():
    ser1 = open_serial_connection(COM_PORT_1)
    ser2 = open_serial_connection(COM_PORT_2)

    if ser1 and ser2:
        thread1 = threading.Thread(target=read_from_serial, args=(ser1, "Arduino 1"))
        thread2 = threading.Thread(target=read_from_serial, args=(ser2, "Arduino 2"))

        thread1.start()
        thread2.start()

        # Keep main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping all threads...")
    else:
        print("❌ Could not establish connections with both devices.")


if __name__ == "__main__":
    main()
