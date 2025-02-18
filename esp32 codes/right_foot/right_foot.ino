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
const int threshold = 3000;

// We want 300 readings in the moving window
#define MAX_READINGS 300

// Define a fixed JSON buffer size
#define JSON_BUFFER_SIZE 200  // Adjust based on required data length

// BLE UUIDs (Unique for the second device)
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
// Ring Buffer Variables
// -----------------------------
static int sensor1Buffer[MAX_READINGS], sensor2Buffer[MAX_READINGS];
static int sensor3Buffer[MAX_READINGS], sensor4Buffer[MAX_READINGS];

static int* head1 = sensor1Buffer, * tail1 = sensor1Buffer;
static int* head2 = sensor2Buffer, * tail2 = sensor2Buffer;
static int* head3 = sensor3Buffer, * tail3 = sensor3Buffer;
static int* head4 = sensor4Buffer, * tail4 = sensor4Buffer;

static unsigned long sum1 = 0, sum2 = 0, sum3 = 0, sum4 = 0;
static int count1 = 0, count2 = 0, count3 = 0, count4 = 0;

// -----------------------------
// Function to update ring buffer
// -----------------------------
void pushReading(int value, int* buffer, int*& head, int*& tail, unsigned long& sum, int& count) {
  if (count < MAX_READINGS) {
    *tail = value;
    sum += value;
    tail++;
    count++;
    if (tail >= buffer + MAX_READINGS) tail = buffer;  // Wrap around
  } else {
    sum -= *head;
    *head = value;
    sum += value;
    head++;
    tail++;
    if (head >= buffer + MAX_READINGS) head = buffer;  // Wrap around
    if (tail >= buffer + MAX_READINGS) tail = buffer;
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
  BLEService* pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_READ |
                      BLECharacteristic::PROPERTY_NOTIFY
                    );
  pCharacteristic->addDescriptor(new BLE2902());
  pService->start();

  // Start advertising
  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
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

  // Update intervals based on threshold triggers
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

//  // Push new readings into buffers
//  pushReading(sensorValue1, sensor1Buffer, head1, tail1, sum1, count1);
//  pushReading(sensorValue2, sensor2Buffer, head2, tail2, sum2, count2);
//  pushReading(sensorValue3, sensor3Buffer, head3, tail3, sum3, count3);
//  pushReading(sensorValue4, sensor4Buffer, head4, tail4, sum4, count4);
//
//  // Compute moving averages
//  float avg1 = (count1 < MAX_READINGS) ? (sum1 / (float)count1) : (sum1 / (float)MAX_READINGS);
//  float avg2 = (count2 < MAX_READINGS) ? (sum2 / (float)count2) : (sum2 / (float)MAX_READINGS);
//  float avg3 = (count3 < MAX_READINGS) ? (sum3 / (float)count3) : (sum3 / (float)MAX_READINGS);
//  float avg4 = (count4 < MAX_READINGS) ? (sum4 / (float)count4) : (sum4 / (float)MAX_READINGS);

//  // Create a fixed-size JSON buffer
//  char dataString[JSON_BUFFER_SIZE];
//  snprintf(dataString, JSON_BUFFER_SIZE, 
//           "{"
//           "\"sensor1\":%d,"
//           "\"sensor2\":%d,"
//           "\"sensor3\":%d,"
//           "\"sensor4\":%d,"
//           "\"interval1_ms\":%lu,"
//           "\"interval2_ms\":%lu,"
//           "\"interval3_ms\":%lu,"
//           "\"interval4_ms\":%lu,"
//           "\"avg1\":%.2f,"
//           "\"avg2\":%.2f,"
//           "\"avg3\":%.2f,"
//           "\"avg4\":%.2f"
//           "}", 
//           sensorValue1, sensorValue2, sensorValue3, sensorValue4,
//           interval1, interval2, interval3, interval4,
//           avg1, avg2, avg3, avg4);

// Create a fixed-size JSON buffer
  char dataString[JSON_BUFFER_SIZE];
  snprintf(dataString, JSON_BUFFER_SIZE, 
           "{"
           "\"sensor1\":%d,"
           "\"sensor2\":%d,"
           "\"sensor3\":%d,"
           "\"sensor4\":%d,"
           "\"interval1_ms\":%lu,"
           "\"interval2_ms\":%lu,"
           "\"interval3_ms\":%lu,"
           "\"interval4_ms\":%lu"
           "}", 
           sensorValue1, sensorValue2, sensorValue3, sensorValue4,
           interval1, interval2, interval3, interval4);

  // Ensure buffer size is always fixed
  dataString[JSON_BUFFER_SIZE - 1] = '\0'; // Null-terminate

  // Send data via BLE
  pCharacteristic->setValue(dataString);
  pCharacteristic->notify();

  // Debug output
  Serial.println("Device 2: ");
  Serial.println(dataString);

  // Delay between readings
  delay(10);
}
