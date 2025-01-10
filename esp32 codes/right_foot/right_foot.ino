#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLEAdvertising.h>
#include <BLE2902.h>

// Define sensor pins for Device 2 (change if necessary)
const int sensorPin1 = 34;
const int sensorPin2 = 27;
const int sensorPin3 = 13;

// ESP32_Sensor_2 code
#define SERVICE_UUID "4fafc201-1fb5-459e-8fcc-c5c9c331914c" // Note the last character changed
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a9" // Note the last character changed

BLECharacteristic* pCharacteristic = NULL;

void setup() {
  Serial.begin(115200);

  // Initialize sensor pins
  pinMode(sensorPin1, INPUT);
  pinMode(sensorPin2, INPUT);
  pinMode(sensorPin3, INPUT);

  // Initialize BLE
  BLEDevice::init("ESP32_Sensor_2"); // Unique name for Device 2
  BLEServer* pServer = BLEDevice::createServer();

  // Create the BLE Service
  BLEService* pService = pServer->createService(SERVICE_UUID);

  // Create a BLE Characteristic
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_READ |
                      BLECharacteristic::PROPERTY_NOTIFY
                    );

  // Add CCCD Descriptor to enable notifications
  pCharacteristic->addDescriptor(new BLE2902());

  // Start the service
  pService->start();

  // Start advertising
  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  // Helps with iOS devices
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();
  Serial.println("ESP32_Sensor_2 is now advertising...");
}

void loop() {
  // Read sensor values
  int sensorValue1 = analogRead(sensorPin1);
  int sensorValue2 = analogRead(sensorPin2);
  int sensorValue3 = analogRead(sensorPin3);

  // Create a data string
  String dataString = String(sensorValue1) + "," + String(sensorValue2) + "," + String(sensorValue3);

  // Set the value to the characteristic and notify clients
  pCharacteristic->setValue(dataString.c_str());
  pCharacteristic->notify();

  // For debugging over serial
  Serial.println("Device 2: " + dataString);

  // Delay between readings
  delay(10); // Adjust as needed
}
