#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <utility/imumaths.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLEAdvertising.h>
#include <BLE2902.h>

// Initialize BNO055 IMU sensor
Adafruit_BNO055 bno = Adafruit_BNO055(-1, 0x29, &Wire);

// Define new BLE UUIDs for ESP32 Mini
#define SERVICE_UUID "5c4fd4d9-0e93-43f7-b02a-6321c781c675"
#define CHARACTERISTIC_UUID "c37454cb-7586-4fc8-9d09-dcbd96a85d2c"

BLECharacteristic* pCharacteristic = NULL;

void setup() {
    Serial.begin(115200);
    
    // Wait for Serial Monitor
    while (!Serial) delay(10);
    Serial.println("Initializing BNO055 Sensor with BLE...");
    
    // Initialize BNO055 Sensor
    if (!bno.begin()) {
        Serial.println("BNO055 not detected. Check wiring or I2C address!");
        while (1);
    }
    
    delay(1000);
    bno.setExtCrystalUse(true);

    Serial.println("BNO055 Initialized. Starting BLE...");

    // Initialize BLE
    BLEDevice::init("ESP32_BNO055_6");  // Unique name for ESP32 Mini
    BLEServer* pServer = BLEDevice::createServer();
    BLEService* pService = pServer->createService(SERVICE_UUID);
    pCharacteristic = pService->createCharacteristic(
                        CHARACTERISTIC_UUID,
                        BLECharacteristic::PROPERTY_READ |
                        BLECharacteristic::PROPERTY_NOTIFY
                      );
    pCharacteristic->addDescriptor(new BLE2902());
    pService->start();

    // Start BLE Advertising
    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();

    Serial.println("ESP32_BNO055 is now advertising...");
}

void loop() {
    // Get Euler angles from BNO055 sensor
    imu::Vector<3> euler = bno.getVector(Adafruit_BNO055::VECTOR_EULER);

    // Prepare data string (CSV format)
    char dataString[50];
    snprintf(dataString, sizeof(dataString), "%.2f,%.2f,%.2f", 
             euler.x(), euler.y(), euler.z());

    // Send data via BLE
    pCharacteristic->setValue(dataString);
    pCharacteristic->notify();

    // Debug output
    Serial.print("Orientation: ");
    Serial.println(dataString);

    delay(100);  // Adjust delay as needed
}
