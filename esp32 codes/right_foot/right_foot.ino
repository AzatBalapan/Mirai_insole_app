#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLEAdvertising.h>
#include <BLE2902.h>

// Define sensor pins
const int sensorPin1 = 33;
const int sensorPin2 = 35;
const int sensorPin3 = 36;
const int sensorPin4 = 39; // 4th sensor

// Define threshold value
const int threshold = 3000; // Adjust as needed

// We want 300 readings in the moving window
#define MAX_READINGS 300

// BLE UUIDs
#define SERVICE_UUID "4fafc201-1fb5-459e-8fcc-c5c9c331914c"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a9"

BLECharacteristic* pCharacteristic = NULL;

// -----------------------------
// Sensor interval tracking
// -----------------------------
unsigned long lastTriggerTime1 = 0;
unsigned long lastTriggerTime2 = 0;
unsigned long lastTriggerTime3 = 0;
unsigned long lastTriggerTime4 = 0;

unsigned long interval1 = 0;
unsigned long interval2 = 0;
unsigned long interval3 = 0;
unsigned long interval4 = 0;

// -----------------------------
// Ring Buffer Variables (Sensor 1)
// -----------------------------
static int sensor1Buffer[MAX_READINGS];
static int* head1 = sensor1Buffer;  // Points to the oldest reading
static int* tail1 = sensor1Buffer;  // Points to the next free location
static unsigned long sum1 = 0;
static int count1 = 0; // how many readings so far

// -----------------------------
// Ring Buffer Variables (Sensor 2)
// -----------------------------
static int sensor2Buffer[MAX_READINGS];
static int* head2 = sensor2Buffer;
static int* tail2 = sensor2Buffer;
static unsigned long sum2 = 0;
static int count2 = 0;

// -----------------------------
// Ring Buffer Variables (Sensor 3)
// -----------------------------
static int sensor3Buffer[MAX_READINGS];
static int* head3 = sensor3Buffer;
static int* tail3 = sensor3Buffer;
static unsigned long sum3 = 0;
static int count3 = 0;

// -----------------------------
// Ring Buffer Variables (Sensor 4)
// -----------------------------
static int sensor4Buffer[MAX_READINGS];
static int* head4 = sensor4Buffer;
static int* tail4 = sensor4Buffer;
static unsigned long sum4 = 0;
static int count4 = 0;

// -----------------------------
// Helper Functions for Each Sensor
// -----------------------------
void pushReadingSensor1(int value) {
  if (count1 < MAX_READINGS) {
    // Buffer not yet full
    *tail1 = value;
    sum1 += value;
    tail1++;
    count1++;
    // Wrap tail if needed
    if (tail1 >= sensor1Buffer + MAX_READINGS) {
      tail1 = sensor1Buffer; // wrap around to start
    }
  } else {
    // Buffer is full (count1 == 300)
    // Remove the oldest reading from sum
    sum1 -= *head1;
    // Overwrite oldest reading with new value
    *head1 = value;
    // Add new value to sum
    sum1 += value;
    // Advance head and tail
    head1++;
    tail1++;
    if (head1 >= sensor1Buffer + MAX_READINGS) {
      head1 = sensor1Buffer; // wrap around
    }
    if (tail1 >= sensor1Buffer + MAX_READINGS) {
      tail1 = sensor1Buffer; // wrap around
    }
  }
}

void pushReadingSensor2(int value) {
  if (count2 < MAX_READINGS) {
    *tail2 = value;
    sum2 += value;
    tail2++;
    count2++;
    if (tail2 >= sensor2Buffer + MAX_READINGS) {
      tail2 = sensor2Buffer;
    }
  } else {
    sum2 -= *head2;
    *head2 = value;
    sum2 += value;
    head2++;
    tail2++;
    if (head2 >= sensor2Buffer + MAX_READINGS) {
      head2 = sensor2Buffer;
    }
    if (tail2 >= sensor2Buffer + MAX_READINGS) {
      tail2 = sensor2Buffer;
    }
  }
}

void pushReadingSensor3(int value) {
  if (count3 < MAX_READINGS) {
    *tail3 = value;
    sum3 += value;
    tail3++;
    count3++;
    if (tail3 >= sensor3Buffer + MAX_READINGS) {
      tail3 = sensor3Buffer;
    }
  } else {
    sum3 -= *head3;
    *head3 = value;
    sum3 += value;
    head3++;
    tail3++;
    if (head3 >= sensor3Buffer + MAX_READINGS) {
      head3 = sensor3Buffer;
    }
    if (tail3 >= sensor3Buffer + MAX_READINGS) {
      tail3 = sensor3Buffer;
    }
  }
}

void pushReadingSensor4(int value) {
  if (count4 < MAX_READINGS) {
    *tail4 = value;
    sum4 += value;
    tail4++;
    count4++;
    if (tail4 >= sensor4Buffer + MAX_READINGS) {
      tail4 = sensor4Buffer;
    }
  } else {
    sum4 -= *head4;
    *head4 = value;
    sum4 += value;
    head4++;
    tail4++;
    if (head4 >= sensor4Buffer + MAX_READINGS) {
      head4 = sensor4Buffer;
    }
    if (tail4 >= sensor4Buffer + MAX_READINGS) {
      tail4 = sensor4Buffer;
    }
  }
}

void setup() {
  Serial.begin(115200);

  // Initialize sensor pins
  pinMode(sensorPin1, INPUT);
  pinMode(sensorPin2, INPUT);
  pinMode(sensorPin3, INPUT);
  pinMode(sensorPin4, INPUT);

  // Initialize BLE
  BLEDevice::init("ESP32_Sensor_2");
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
  unsigned long currentTime = millis();

  // Read sensor values
  int sensorValue1 = analogRead(sensorPin1);
  int sensorValue2 = analogRead(sensorPin2);
  int sensorValue3 = analogRead(sensorPin3);
  int sensorValue4 = analogRead(sensorPin4);

  // ---------------------------------------------------
  // (A) Update intervals based on threshold triggers
  // ---------------------------------------------------
  if (sensorValue1 > threshold) {
    interval1 = (lastTriggerTime1 == 0) ? 0 : (currentTime - lastTriggerTime1);
    lastTriggerTime1 = currentTime;
  }

  if (sensorValue2 > threshold) {
    interval2 = (lastTriggerTime2 == 0) ? 0 : (currentTime - lastTriggerTime2);
    lastTriggerTime2 = currentTime;
  }

  if (sensorValue3 > threshold) {
    interval3 = (lastTriggerTime3 == 0) ? 0 : (currentTime - lastTriggerTime3);
    lastTriggerTime3 = currentTime;
  }

  if (sensorValue4 > threshold) {
    interval4 = (lastTriggerTime4 == 0) ? 0 : (currentTime - lastTriggerTime4);
    lastTriggerTime4 = currentTime;
  }

  // ---------------------------------------------------
  // (B) Push new readings into the ring buffers
  // ---------------------------------------------------
  pushReadingSensor1(sensorValue1);
  pushReadingSensor2(sensorValue2);
  pushReadingSensor3(sensorValue3);
  pushReadingSensor4(sensorValue4);

  // ---------------------------------------------------
  // (C) Compute averages
  //   - If we haven't reached 300 reads yet for a sensor,
  //     average = sum / count.
  //   - Once we have 300, average = sum / 300.
  // ---------------------------------------------------
  float avg1 = (count1 < MAX_READINGS) 
                ? (sum1 / (float)count1) 
                : (sum1 / (float)MAX_READINGS);

  float avg2 = (count2 < MAX_READINGS) 
                ? (sum2 / (float)count2) 
                : (sum2 / (float)MAX_READINGS);

  float avg3 = (count3 < MAX_READINGS) 
                ? (sum3 / (float)count3) 
                : (sum3 / (float)MAX_READINGS);

  float avg4 = (count4 < MAX_READINGS) 
                ? (sum4 / (float)count4) 
                : (sum4 / (float)MAX_READINGS);

  // ---------------------------------------------------
  // (D) Create JSON string for BLE
  // ---------------------------------------------------
  String dataString = "{";
  dataString += "\"sensor1\":" + String(sensorValue1) + ",";
  dataString += "\"sensor2\":" + String(sensorValue2) + ",";
  dataString += "\"sensor3\":" + String(sensorValue3) + ",";
  dataString += "\"sensor4\":" + String(sensorValue4) + ",";

  dataString += "\"interval1_ms\":" + String(interval1) + ",";
  dataString += "\"interval2_ms\":" + String(interval2) + ",";
  dataString += "\"interval3_ms\":" + String(interval3) + ",";
  dataString += "\"interval4_ms\":" + String(interval4) + ",";

  dataString += "\"avg1\":" + String(avg1, 2) + ",";
  dataString += "\"avg2\":" + String(avg2, 2) + ",";
  dataString += "\"avg3\":" + String(avg3, 2) + ",";
  dataString += "\"avg4\":" + String(avg4, 2);
  dataString += "}";

  // ---------------------------------------------------
  // (E) Send data via BLE
  // ---------------------------------------------------
  pCharacteristic->setValue(dataString.c_str());
  pCharacteristic->notify();

  // Debug output
  Serial.println("Device 2: " + dataString);

  // Delay between readings
  delay(10); // Adjust as needed
}
