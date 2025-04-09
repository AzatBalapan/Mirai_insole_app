#include <Wire.h>
#include <MPU6050.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEAdvertising.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// -----------------------------------------
// 1) ANALOG SENSORS + MOVING AVERAGE
// -----------------------------------------
#define SENSOR_PIN_1  33
#define SENSOR_PIN_2  35
#define SENSOR_PIN_3  36
#define SENSOR_PIN_4  39

// If below threshold, treat as zero
const int threshold = 3600;

// Ring buffer settings
#define MAX_READINGS 300

static short buffer1[MAX_READINGS], buffer2[MAX_READINGS];
static short buffer3[MAX_READINGS], buffer4[MAX_READINGS];

static short *head1 = buffer1, *tail1 = buffer1;
static short *head2 = buffer2, *tail2 = buffer2;
static short *head3 = buffer3, *tail3 = buffer3;
static short *head4 = buffer4, *tail4 = buffer4;

static unsigned long sum1 = 0, sum2 = 0, sum3 = 0, sum4 = 0;
static int count1 = 0, count2 = 0, count3 = 0, count4 = 0;

// Helper to push a new reading into a ring buffer
void pushReading(short value, 
                 short* buffer, 
                 short*& head, 
                 short*& tail, 
                 unsigned long& sum, 
                 int& count) 
{
  if (count < MAX_READINGS) {
    *tail = value;
    sum += value;
    tail++;
    count++;
    if (tail >= buffer + MAX_READINGS) {
      tail = buffer;
    }
  } else {
    // buffer is full, overwrite oldest
    sum -= *head;    // remove oldest from sum
    *head = value;   // store new
    sum += value;    // add new
    head++;
    tail++;
    if (head >= buffer + MAX_READINGS) head = buffer;
    if (tail >= buffer + MAX_READINGS) tail = buffer;
  }
}

// We'll store "last" raw sensor values and their averages here
static short lastSensorValues[4] = {0,0,0,0};
static short lastAverages[4]    = {0,0,0,0};

// -----------------------------------------
// 2) MPU6050 + COMPLEMENTARY FILTER
// -----------------------------------------
MPU6050 mpu;

// Filter coefficients
#define ALPHA 0.98f  // typical 0.95–0.99

// We'll track the integrated angles here
static float roll_cf  = 0.0f;  
static float pitch_cf = 0.0f;
static float yaw_cf   = 0.0f;

// For dt calculations
static unsigned long prevMicros = 0;

// We'll store the latest short angles here
static short lastAngles[3] = {0,0,0};

// -----------------------------------------
// 3) BLE
// -----------------------------------------
#define SERVICE_UUID             "4fafc202-1fb5-459e-8fcc-c5c9c331914c"
#define CHARACTERISTIC_DATA_UUID "beb5483f-36e1-4688-b7f5-ea07361b26a8"

// We'll send ASCII data (CSV) as in your first example
BLECharacteristic* pDataCharacteristic = nullptr;

// (Optional) A fixed-size buffer for sending data
// Make it large enough for your CSV/JSON string
#define DATA_BUFFER_SIZE 100
static char dataString[DATA_BUFFER_SIZE];

void setup()
{
  Serial.begin(115200);
  Wire.begin();

  // 1) Initialize analog sensor pins
  pinMode(SENSOR_PIN_1, INPUT);
  pinMode(SENSOR_PIN_2, INPUT);
  pinMode(SENSOR_PIN_3, INPUT);
  pinMode(SENSOR_PIN_4, INPUT);

  // 2) Initialize MPU6050
  Serial.println("Initializing MPU6050...");
  mpu.initialize();
  if(!mpu.testConnection()) {
    Serial.println("MPU6050 connection failed!");
    while(1);
  }
  Serial.println("MPU6050 connected!");

  // 3) Initialize BLE
  BLEDevice::init("MPU_Sensor_1"); // Device name
  BLEServer* pServer = BLEDevice::createServer();
  
  BLEService* pService = pServer->createService(SERVICE_UUID);
  
  // Use NOTIFY property (like the first code)
  pDataCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_DATA_UUID,
    BLECharacteristic::PROPERTY_READ |   // you can keep READ if you want
    BLECharacteristic::PROPERTY_NOTIFY
  );
  // Important for notifications
  pDataCharacteristic->addDescriptor(new BLE2902());

  pService->start();

  BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);
  pAdvertising->setMinPreferred(0x12);
  BLEDevice::startAdvertising();

  Serial.println("ESP32 is now advertising - 4 analog + MPU angles...");
}

void loop()
{
  // -------------------------------------
  // (A) Read 4 analog sensors
  // -------------------------------------
  short val1 = analogRead(SENSOR_PIN_1);
  short val2 = analogRead(SENSOR_PIN_2);
  short val3 = analogRead(SENSOR_PIN_3);
  short val4 = analogRead(SENSOR_PIN_4);

  // Apply threshold => if <= threshold => 0
  if(val1 <= threshold) val1 = 0;
  if(val2 <= threshold) val2 = 0;
  if(val3 <= threshold) val3 = 0;
  if(val4 <= threshold) val4 = 0;

  // Push into ring buffers
  pushReading(val1, buffer1, head1, tail1, sum1, count1);
  pushReading(val2, buffer2, head2, tail2, sum2, count2);
  pushReading(val3, buffer3, head3, tail3, sum3, count3);
  pushReading(val4, buffer4, head4, tail4, sum4, count4);

  // Compute moving averages
  short avg1 = 0, avg2 = 0, avg3 = 0, avg4 = 0;
  if(count1 > 0) {
    avg1 = (short)((count1 < MAX_READINGS) ? (sum1 / (float)count1) : (sum1 / (float)MAX_READINGS));
  }
  if(count2 > 0) {
    avg2 = (short)((count2 < MAX_READINGS) ? (sum2 / (float)count2) : (sum2 / (float)MAX_READINGS));
  }
  if(count3 > 0) {
    avg3 = (short)((count3 < MAX_READINGS) ? (sum3 / (float)count3) : (sum3 / (float)MAX_READINGS));
  }
  if(count4 > 0) {
    avg4 = (short)((count4 < MAX_READINGS) ? (sum4 / (float)count4) : (sum4 / (float)MAX_READINGS));
  }

  // Store for reference (if you still need them):
  lastSensorValues[0] = val1;
  lastSensorValues[1] = val2;
  lastSensorValues[2] = val3;
  lastSensorValues[3] = val4;

  lastAverages[0] = avg1;
  lastAverages[1] = avg2;
  lastAverages[2] = avg3;
  lastAverages[3] = avg4;

  // -------------------------------------
  // (B) Read MPU6050, update complementary filter
  // -------------------------------------
  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  unsigned long currentMicros = micros();
  float dt = 0.01f; 
  if(prevMicros > 0) {
    dt = (currentMicros - prevMicros)/1000000.0f;
  }
  prevMicros = currentMicros;

  // Convert to 'g'
  float accX = ax / 16384.0f;
  float accY = ay / 16384.0f;
  float accZ = az / 16384.0f;

  // Convert gyro to deg/sec
  float gyroX = gx / 131.0f;
  float gyroY = gy / 131.0f;
  float gyroZ = gz / 131.0f;

  // "accelerometer-only" angles for pitch & roll
  float accRoll  = atan2(accY, accZ) * 180.0f / PI;
  float accPitch = atan(-accX / sqrtf(accY*accY + accZ*accZ)) * 180.0f / PI;

  // Integrate gyro for roll/pitch
  roll_cf  += gyroX * dt;  
  pitch_cf += gyroY * dt;  

  // Complementary filter
  roll_cf  = ALPHA * roll_cf  + (1.0f-ALPHA)*(accRoll);
  pitch_cf = ALPHA * pitch_cf + (1.0f-ALPHA)*(accPitch);

  // Yaw from gyroZ integration only
  yaw_cf   += gyroZ * dt;

  // Store short versions
  lastAngles[0] = (short)roll_cf;
  lastAngles[1] = (short)pitch_cf;
  lastAngles[2] = (short)yaw_cf;
  short sensor_name = 3;
  // -------------------------------------
  // (C) Send data via BLE NOTIFY (like your first code)
  // -------------------------------------
  // Build a CSV line: 4 raw, 4 avg, 3 angles => total 11 fields
  // Increase DATA_BUFFER_SIZE if needed
  snprintf(dataString, DATA_BUFFER_SIZE,
           "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d",
           sensor_name, val1, val2, val3, val4, 
           avg1, avg2, avg3, avg4,
           lastAngles[0], lastAngles[1], lastAngles[2]);

  // Terminate the string
  dataString[DATA_BUFFER_SIZE - 1] = '\0';

  // Update BLE characteristic and notify
  pDataCharacteristic->setValue((uint8_t*)dataString, strlen(dataString));
  pDataCharacteristic->notify();

  // Debug (optional)
//  Serial.println(dataString);

  delay(10);
}
