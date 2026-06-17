// ============================================
// ESP32 with RFID Temperature Prediction System
// ============================================
// Reads temperature sensors and RFID tags
// Sends data to Flask server for predictions
//
// NOTE: RFID is OPTIONAL - System continues working normally if RFID fails
// If RFID hardware is not connected, system will detect and disable RFID
// All sensor data will still be sent to server every 60 seconds

// ============================================
// WIRING GUIDE FOR THIS CONFIG
// ============================================
// BME280 & OLED (I2C):
//   - SDA: GPIO 5    (pin 29)
//   - SCL: GPIO 4    (pin 32)
//   - 3V3: 3.3V
//   - GND: Ground
//
// MFRC522 RFID (SPI Hardware - HSPI pins, NOT flash pins) - OPTIONAL:
//   Follow this wiring if you have RFID (system works without it):
//   - RFID 3.3V   → ESP32 3V3
//   - RFID GND    → ESP32 GND
//   - RFID RST    → ESP32 GPIO 26
//   - RFID MOSI   → ESP32 GPIO 25
//   - RFID MISO   → ESP32 GPIO 12 (HSPI MISO)
//   - RFID CLK    → ESP32 GPIO 14 (HSPI CLK)
//   - RFID CS/SS  → ESP32 GPIO 15 (HSPI CS)
//
// PIR & LED:
//   - PIR Sensor: GPIO 13
//   - LED:        GPIO 2 (built-in)
// ============================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_BME280.h>
#include <Adafruit_SSD1306.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <SPI.h>        // RFID ENABLED (hardware SPI)
#include <MFRC522.h>    // RFID ENABLED

// ============================================
// CONFIGURATION
// ============================================
const char* ssid = "MERCUSYS_112E";
const char* password = "44288006";  // Open WiFi network
const char* server_url = "http://192.168.0.117:5001";  // UPDATED: Changed from 192.168.0.9 to 192.168.1.9

// GPIO Pins
const int PIR_PIN = 13;       // PIR sensor (GPIO 13 - better for interrupts)
const int LED_PIN = 2;        // Built-in LED

// RFID Pins (OPTIONAL - Using Hardware SPI: GPIO 12,14,15 only)
// NOTE: GPIO 13 moved to PIR since PIR is more critical than RFID
const int RFID_SS_PIN = 15;   // RFID CS/SS pin (HSPI CS)
const int RFID_RST_PIN = 26;  // RFID RST pin
const int RFID_MOSI_PIN = 25; // RFID MOSI (GPIO 25)
const int RFID_MISO_PIN = 12; // RFID MISO (HSPI MISO)
const int RFID_CLK_PIN = 14;  // RFID CLK (HSPI CLK)

// I2C Pins for BME280 and OLED
const int SDA_PIN = 5;        // I2C SDA
const int SCL_PIN = 4;        // I2C SCL

// Sensor objects
Adafruit_BME280 bme;
Adafruit_SSD1306 display(128, 64, &Wire, -1);

// RFID Reader
MFRC522 rfid(RFID_SS_PIN, RFID_RST_PIN);

// Motion counter with debouncing
volatile int motionCount = 0;
volatile unsigned long last_motion_time = 0;
const unsigned long MOTION_DEBOUNCE = 500;  // 500ms debounce to filter electrical noise

// Display status
bool oledFound = false;

// Timing
unsigned long last_reading = 0;
unsigned long last_rfid_check = 0;
unsigned long last_display_update = 0;
unsigned long last_rfid_test = 0;
const unsigned long READING_INTERVAL = 60000;    // 1 minute
const unsigned long RFID_CHECK_INTERVAL = 1000;  // 1 second
const unsigned long DISPLAY_UPDATE_INTERVAL = 2000;  // 2 seconds
const unsigned long RFID_TEST_INTERVAL = 10000;  // Test RFID every 10 seconds

bool rfidWorking = false;  // Track RFID status

// ============================================
// FORWARD DECLARATIONS
// ============================================
void scanI2CDevices();
void initializeDisplay();
void displayError(String error);
void displayServerStatus(String status, String detail);
void connectToWiFi();
void setupServer();
void displaySensorData();
void sendPredictionRequest();
bool testRFID();
void checkRFID();
void verifyRFID(String rfid_code);
void readSensors();
bool sendPredictionJSON();
void displayRFID(String uid);
void displayRFIDResult(String name, bool valid);

// Data storage
struct SensorData {
  float temperature;
  float humidity;
  float pressure;
  int movement;
};

SensorData current_data;
String last_rfid = "";
String last_rfid_person = "";
unsigned long last_rfid_time = 0;
bool server_connected = false;

// ============================================
// ISR for motion detection
// ============================================
void IRAM_ATTR motionISR() {
  unsigned long now = millis();
  // Only count if enough time has passed since last motion (debounce)
  if (now - last_motion_time > MOTION_DEBOUNCE) {
    motionCount++;
    last_motion_time = now;
  }
}

// ============================================
// SETUP
// ============================================
void setup() {
  Serial.begin(115200);
  delay(2000);  // Long delay for serial to be ready
  
  Serial.println("\n\n[INFO] ESP32 RFID Temperature System Starting...");
  Serial.flush();
  
  // Initialize I2C (SDA=5, SCL=4)
  Serial.println("[I2C] Initializing Wire library...");
  Serial.print("  SDA: GPIO "); Serial.println(SDA_PIN);
  Serial.print("  SCL: GPIO "); Serial.println(SCL_PIN);
  Serial.flush();
  delay(100);
  yield();
  
  // Configure I2C with specific frequency
  Wire.begin(SDA_PIN, SCL_PIN, 100000);  // 100kHz is standard
  delay(200);
  yield();
  
  Serial.println("[I2C] Wire library initialized!");
  Serial.flush();
  delay(50);
  yield();
  
  // Scan I2C devices with timeout protection
  Serial.println("[I2C] Scanning for devices...");
  Serial.flush();
  delay(100);
  yield();
  
  scanI2CDevices();
  delay(100);
  yield();
  
  Serial.println("[I2C] Scan complete");
  Serial.flush();
  
  // Initialize pins
  Serial.println("[INFO] Configuring GPIO pins...");
  Serial.flush();
  delay(50);
  yield();
  
  pinMode(LED_PIN, OUTPUT);
  pinMode(PIR_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIR_PIN), motionISR, RISING);
  
  Serial.println("[INFO] GPIO pins configured");
  Serial.flush();
  delay(50);
  yield();
  
  // SPI initialization for RFID - ENABLED with Hardware SPI
  Serial.println("[INFO] Initializing hardware SPI for RFID...");
  Serial.flush();
  delay(100);
  yield();
  
  // Configure SPI pins (Hardware SPI)
  Serial.println("  Configuring Hardware SPI pins (CLK=GPIO14, MOSI=GPIO25, MISO=GPIO12, CS=GPIO15, RST=GPIO26)");
  Serial.flush();
  
  SPI.begin(RFID_CLK_PIN, RFID_MISO_PIN, RFID_MOSI_PIN, RFID_SS_PIN);
  delay(100);
  yield();
  
  // Initialize RST pin
  pinMode(RFID_RST_PIN, OUTPUT);
  digitalWrite(RFID_RST_PIN, HIGH);
  delay(100);
  
  // Initialize RFID
  Serial.println("[RFID] Initializing MFRC522 reader on hardware SPI...");
  Serial.flush();
  rfid.PCD_Init();
  delay(100);
  yield();
  
  // Initialize OLED display with better diagnostics
  Serial.println("[OLED] Initializing display...");
  Serial.flush();
  delay(300);
  yield();
  
  // Try address 0x3C first (most common for SSD1306)
  Serial.println("[OLED] Trying address 0x3C...");
  Serial.flush();
  delay(100);
  yield();
  
  if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("[OLED] ✓ Display found at 0x3C!");
    oledFound = true;
  } else {
    Serial.println("[OLED] ✗ Not found at 0x3C");
    Serial.flush();
    delay(100);
    yield();
    
    // Try address 0x3D (alternative SSD1306)
    Serial.println("[OLED] Trying address 0x3D...");
    Serial.flush();
    delay(100);
    if (display.begin(SSD1306_SWITCHCAPVCC, 0x3D)) {
      Serial.println("[OLED] ✓ Display found at 0x3D!");
      oledFound = true;
    } else {
      Serial.println("[OLED] ✗ Not found at 0x3D");
      Serial.flush();
    }
  }
  
  delay(200);
  yield();
  
  if (oledFound) {
    Serial.println("[OLED] Initializing display content...");
    Serial.flush();
    delay(100);
    initializeDisplay();
    Serial.println("[OLED] Display initialized successfully!");
    Serial.flush();
  } else {
    Serial.println("[ERROR] OLED display not responding!");
    Serial.println("[OLED] Troubleshooting:");
    Serial.println("  • Check GPIO 5 (SDA) and GPIO 4 (SCL) are connected");
    Serial.println("  • Check OLED has 3.3V power");
    Serial.println("  • Try checking I2C scan output above for detected addresses");
    Serial.flush();
  }
  
  delay(200);
  yield();
  
  // Initialize BME280 sensor
  Serial.println("[INFO] Initializing BME280 sensor...");
  Serial.flush();
  delay(100);
  yield();
  
  if (!bme.begin(0x76)) {
    Serial.println("[WARNING] BME280 sensor not found at 0x76!");
    Serial.println("[INFO] Continuing without BME280 sensor...");
    Serial.flush();
  } else {
    Serial.println("[INFO] BME280 sensor initialized");
    Serial.flush();
  }
  
  delay(100);
  yield();
  
  // Connect to WiFi
  Serial.println("[INFO] Connecting to WiFi...");
  Serial.flush();
  delay(100);
  yield();
  
  connectToWiFi();
  delay(200);
  yield();
  
  // Verify server
  Serial.println("[INFO] Setting up server...");
  Serial.flush();
  delay(100);
  yield();
  
  setupServer();
  delay(100);
  yield();
  
  Serial.println("\n[INFO] Setup complete!");
  Serial.println("[PIN CONFIGURATION]");
  Serial.println("  I2C Bus (BME280 + OLED):");
  Serial.println("    - SDA (I2C): GPIO 5");
  Serial.println("    - SCL (I2C): GPIO 4");
  Serial.println("  RFID Hardware SPI: OPTIONAL");
  Serial.println("    - CLK:  GPIO 14 (HSPI CLK)");
  Serial.println("    - MOSI: GPIO 25");
  Serial.println("    - MISO: GPIO 12 (HSPI MISO)");
  Serial.println("    - CS:   GPIO 15 (HSPI CS)");
  Serial.println("    - RST:  GPIO 26");
  Serial.println("  Sensors:");
  Serial.println("    - PIR:  GPIO 13");
  Serial.println("    - LED:  GPIO 2");
  Serial.println("\n[SYSTEM] Testing RFID connection (system works with or without RFID)...");
  Serial.flush();
  
  // Initial RFID test
  rfidWorking = testRFID();
  
  delay(500);
}

// ============================================
// RFID TEST & DIAGNOSTIC - WITH TIMEOUT
// ============================================
bool testRFID() {
  Serial.println("\n[RFID TEST] Checking RFID connection (timeout: 1 second)...");
  Serial.flush();
  
  unsigned long start = millis();
  unsigned long timeout = 1000; // 1 second timeout - if RFID doesn't respond, skip it
  
  // Try to read RFID version register with timeout
  while (millis() - start < timeout) {
    byte ver = rfid.PCD_ReadRegister(MFRC522::VersionReg);
    
    if (ver == 0x92 || ver == 0x91 || ver == 0x88) {
      Serial.println("✅ RFID IS WORKING!");
      Serial.print("   Firmware Version: 0x");
      Serial.println(ver, HEX);
      return true;
    } else if (ver == 0x00) {
      Serial.println("❌ RFID NOT WORKING - Possible reasons:");
      Serial.println("   1. RFID module has NO POWER (check 3.3V supply)");
      Serial.println("   2. SPI wires are disconnected or loose");
      Serial.println("   3. Check: CLK=GPIO14, MOSI=GPIO25, MISO=GPIO12, CS=GPIO15, RST=GPIO26");
      Serial.println("   System will continue WITHOUT RFID");
      return false;
    } else if (ver == 0xFF) {
      Serial.println("❌ RFID NOT WORKING - Possible reasons:");
      Serial.println("   1. RFID module is NOT powered");
      Serial.println("   2. CS pin (GPIO 15) may be held LOW");
      Serial.println("   3. RST pin (GPIO 26) may need to pulse");
      Serial.println("   System will continue WITHOUT RFID");
      return false;
    } else if (ver != 0) {
      // Got some response, try to work with it
      Serial.print("⚠️  RFID Version unknown: 0x");
      Serial.println(ver, HEX);
      Serial.println("   Treating as working. If RFID fails, it will be disabled on next test.");
      return true;
    }
    
    delay(50);  // Small delay before retry
  }
  
  // Timeout reached - no response from RFID
  Serial.println("⏱️  RFID initialization TIMEOUT - RFID disabled");
  Serial.println("   System will continue normally WITHOUT RFID");
  return false;
}

// ============================================
// MAIN LOOP
// ============================================
void loop() {
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WARNING] WiFi disconnected, reconnecting...");
    connectToWiFi();
  }
  
  // Test RFID periodically (try to reconnect if it failed before)
  if (millis() - last_rfid_test >= RFID_TEST_INTERVAL) {
    last_rfid_test = millis();
    Serial.println("\n[PERIODIC CHECK] Testing RFID connection...");
    rfidWorking = testRFID();
  }
  
  // Check for RFID tags ONLY if RFID is working
  if (rfidWorking && millis() - last_rfid_check >= RFID_CHECK_INTERVAL) {
    last_rfid_check = millis();
    checkRFID();
  }
  
  // Update OLED display with sensor data
  if (millis() - last_display_update >= DISPLAY_UPDATE_INTERVAL) {
    last_display_update = millis();
    if (oledFound) {
      displaySensorData();
    }
  }
  
  // Read sensors at regular interval (works with or without RFID)
  if (millis() - last_reading >= READING_INTERVAL) {
    last_reading = millis();
    
    readSensors();
    
    if (server_connected) {
      sendPredictionRequest();
    } else {
      Serial.println("[ERROR] Server not connected");
      displayError("Server Error");
    }
  }
  
  delay(100);
}

// ============================================
// RFID FUNCTIONS - ENABLED WITH AUTO-RECONNECT
// ============================================
void checkRFID() {
  // Look for new cards
  if (!rfid.PICC_IsNewCardPresent())
    return;
  
  // Select one of the cards
  if (!rfid.PICC_ReadCardSerial())
    return;
  
  // Read RFID UID
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10)
      uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  
  uid.toUpperCase();
  
  // Display on OLED
  displayRFID(uid);
  
  Serial.print("[RFID] Tag detected: ");
  Serial.println(uid);
  
  // Send to server for verification
  verifyRFID(uid);
  
  // Halt PICC
  rfid.PICC_HaltA();
  
  // Stop encryption
  rfid.PCD_StopCrypto1();
}

void verifyRFID(String rfid_code) {
  if (!server_connected)
    return;
  
  HTTPClient http;
  http.begin(String(server_url) + "/api/rfid/verify");
  http.addHeader("Content-Type", "application/json");
  
  // Create JSON payload
  StaticJsonDocument<200> doc;
  doc["rfid_code"] = rfid_code;
  
  String payload;
  serializeJson(doc, payload);
  
  Serial.println("[RFID] Sending verification request: " + payload);
  
  int httpCode = http.POST(payload);
  
  if (httpCode == 200) {
    String response = http.getString();
    
    Serial.println("[RFID] Response: " + response);
    
    // Parse response
    StaticJsonDocument<200> responseDoc;
    deserializeJson(responseDoc, response);
    
    if (responseDoc["valid"]) {
      String person_name = responseDoc["person_name"].as<String>();
      last_rfid = rfid_code;
      last_rfid_person = person_name;
      last_rfid_time = millis();
      
      digitalWrite(LED_PIN, HIGH);
      delay(500);
      digitalWrite(LED_PIN, LOW);
      
      Serial.println("[RFID] ✓ VALID: " + person_name);
      displayRFIDResult(person_name, true);
    } else {
      Serial.println("[RFID] ✗ INVALID");
      displayRFIDResult("Not Authorized", false);
    }
  } else {
    Serial.print("[ERROR] HTTP Error: ");
    Serial.println(httpCode);
  }
  
  http.end();
}

// ============================================
// DISPLAY FUNCTIONS
// ============================================

// Scan I2C bus for connected devices
void scanI2CDevices() {
  byte error, address;
  int nDevices = 0;
  
  Serial.println("[I2C] Scanning addresses 0x00-0x7F (with 100ms timeout per address)...");
  
  for(address = 0x00; address < 0x80; address++) {
    // Reset I2C bus on each try
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    
    if (error == 0) {
      Serial.print("[I2C] Found device at 0x");
      if (address < 0x10) Serial.print("0");
      Serial.println(address, HEX);
      
      // Identify common devices
      if (address == 0x3C || address == 0x3D) {
        Serial.println("       └─ Likely OLED display (SSD1306)");
      } else if (address == 0x76 || address == 0x77) {
        Serial.println("       └─ Likely BME280 sensor");
      }
      nDevices++;
    } else if (error == 4) {
      Serial.print("[I2C] Unknown error at 0x");
      if (address < 0x10) Serial.print("0");
      Serial.println(address, HEX);
    }
  }
  
  if (nDevices == 0) {
    Serial.println("[I2C] ⚠️  No devices found!");
    Serial.println("[I2C] Possible causes:");
    Serial.println("  - Wires not connected properly");
    Serial.println("  - Pull-up resistors missing (OLED/BME280 may need them)");
    Serial.println("  - Check GPIO 5 (SDA) and GPIO 4 (SCL) connections");
  } else {
    Serial.print("[I2C] Found ");
    Serial.print(nDevices);
    Serial.println(" device(s)");
  }
  
  Serial.println("[I2C] ---");
}

// Initialize display
void initializeDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Initializing RFID...");
  display.display();
}

void displayError(String error) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(error);
  display.display();
}

void displaySensorData() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  
  display.print("T: ");
  display.print(current_data.temperature, 1);
  display.println(" C");
  
  display.print("H: ");
  display.print(current_data.humidity, 1);
  display.println(" %");
  
  display.print("P: ");
  display.print(current_data.pressure, 0);
  display.println(" hPa");
  
  display.print("M: ");
  display.println(current_data.movement);
  
  display.display();
}

void displayRFID(String uid) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("RFID Detected:");
  display.setTextSize(2);
  display.println(uid);
  display.display();
}

void displayRFIDResult(String name, bool valid) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  
  if (valid) {
    display.println("Access Granted");
    display.setTextSize(2);
    display.println(name);
  } else {
    display.println("Access Denied");
    display.setTextSize(2);
    display.println(name);
  }
  
  display.display();
}

void displayServerStatus(String status, String detail) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(status);
  display.println(detail);
  display.display();
}

// ============================================
// WIFI FUNCTIONS
// ============================================
void connectToWiFi() {
  Serial.print("[INFO] Connecting to WiFi: ");
  Serial.println(ssid);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[SUCCESS] WiFi connected!");
    Serial.print("[INFO] IP: ");
    Serial.println(WiFi.localIP());
    digitalWrite(LED_PIN, HIGH);
  } else {
    Serial.println("\n[ERROR] Failed to connect to WiFi");
    digitalWrite(LED_PIN, LOW);
  }
}

void setupServer() {
  Serial.println("\n[SETUP] Attempting to connect to server...");
  
  HTTPClient http;
  http.begin(String(server_url) + "/api/status");
  
  int httpCode = http.GET();
  
  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("[SUCCESS] Server is running!");
    Serial.println("Response: " + response);
    server_connected = true;
    displayServerStatus("Server OK", "Ready");
  } else {
    Serial.println("[ERROR] Server not responding (Code: " + String(httpCode) + ")");
    server_connected = false;
    displayError("Server Not Found");
  }
  
  http.end();
}

// ============================================
// SENSOR FUNCTIONS
// ============================================
void readSensors() {
  // Read BME280
  current_data.temperature = bme.readTemperature();
  current_data.humidity = bme.readHumidity();
  current_data.pressure = bme.readPressure() / 100.0;
  
  // Read motion sensor
  noInterrupts();
  current_data.movement = motionCount;
  motionCount = 0;
  interrupts();
  
  Serial.println("\n[SENSOR DATA]");
  Serial.print("Temp: ");
  Serial.print(current_data.temperature);
  Serial.println(" C");
  Serial.print("Humidity: ");
  Serial.print(current_data.humidity);
  Serial.println(" %");
  Serial.print("Pressure: ");
  Serial.print(current_data.pressure);
  Serial.println(" hPa");
  Serial.print("Movement: ");
  Serial.println(current_data.movement);
  
  displaySensorData();
}

// ============================================
// PREDICTION FUNCTIONS
// ============================================
void sendPredictionRequest() {
  Serial.println("\n[REQUEST] Sending prediction request to server...");
  
  if (sendPredictionJSON()) {
    return;
  }
  
  Serial.println("[FALLBACK] Simple endpoint failed");
}

bool sendPredictionJSON() {
  HTTPClient http;
  http.begin(String(server_url) + "/predict");
  http.addHeader("Content-Type", "application/json");
  
  // Create JSON payload
  StaticJsonDocument<200> doc;
  doc["temp"] = current_data.temperature;
  doc["hum"] = current_data.humidity;
  doc["pressure"] = current_data.pressure;
  doc["movement"] = current_data.movement;
  
  String payload;
  serializeJson(doc, payload);
  
  Serial.println("[JSON] Payload: " + payload);
  
  int httpCode = http.POST(payload);
  String response = http.getString();
  
  Serial.print("[RESPONSE] HTTP Code: ");
  Serial.println(httpCode);
  Serial.print("[RESPONSE] Body: ");
  Serial.println(response);
  
  if (httpCode != 200) {
    http.end();
    return false;
  }
  
  // Parse response
  StaticJsonDocument<500> doc_response;
  deserializeJson(doc_response, response);
  
  float prediction = doc_response["prediction"];
  Serial.print("[RESULT] Prediction: ");
  Serial.print(prediction);
  Serial.println(" C");
  
  http.end();
  return true;
}
