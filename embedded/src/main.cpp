#include "env.h"
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>

#define TEMP_PIN 4
#define PIR_PIN 15
#define LIGHT_PIN 22
#define FAN_PIN 23

OneWire oneWire(TEMP_PIN);
DallasTemperature tempSensor(&oneWire);

unsigned long lastRequest = 0;
const unsigned long interval = 5000;

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("Connecting to WiFi");

  WiFi.begin(WIFI_SSID, WIFI_PASS);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi connected");
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("ESP32 STARTED");

  pinMode(PIR_PIN, INPUT);
  pinMode(LIGHT_PIN, OUTPUT);
  pinMode(FAN_PIN, OUTPUT);

  digitalWrite(LIGHT_PIN, LOW);
  digitalWrite(FAN_PIN, LOW);

  tempSensor.begin();

  connectWiFi();
}

void sendSensorData(float temperature, bool presence) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Reconnecting...");
    connectWiFi();
    return;
  }

  HTTPClient http;

  String url = String(SERVER_BASE_URL) + "/data";

  http.begin(url);
  http.setTimeout(3000);
  http.addHeader("Content-Type", "application/json");

  JsonDocument doc;
  doc["temperature"] = temperature;
  doc["presence"] = presence;

  String json;
  serializeJson(doc, json);

  int responseCode = http.POST(json);

  Serial.print("POST /data response: ");
  Serial.println(responseCode);

  http.end();
}

void getStateAndControlOutputs() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected. Reconnecting...");
    connectWiFi();
    return;
  }

  HTTPClient http;

  String url = String(SERVER_BASE_URL) + "/state";

  http.begin(url);
  http.setTimeout(3000);

  int responseCode = http.GET();

  Serial.print("GET /state response: ");
  Serial.println(responseCode);

  if (responseCode > 0) {
    String payload = http.getString();

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload);

    if (!error) {
      bool fan = doc["fan"];
      bool light = doc["light"];

      Serial.print("Fan from server: ");
      Serial.println(fan ? "true" : "false");

      Serial.print("Light from server: ");
      Serial.println(light ? "true" : "false");

      digitalWrite(FAN_PIN, fan ? HIGH : LOW);
      digitalWrite(LIGHT_PIN, light ? HIGH : LOW);
    } else {
      Serial.print("JSON parse error: ");
      Serial.println(error.c_str());
    }
  }

  http.end();
}

void loop() {
  if (millis() - lastRequest > interval) {
    lastRequest = millis();

    tempSensor.requestTemperatures();
    float temperature = tempSensor.getTempCByIndex(0);

    if (temperature == DEVICE_DISCONNECTED_C ||
        temperature <= -100 ||
        temperature >= 100) {
      Serial.println("Invalid temperature reading ignored");
      getStateAndControlOutputs();
      return;
    }

    bool presence = digitalRead(PIR_PIN);

    Serial.print("Temperature: ");
    Serial.println(temperature);

    Serial.print("Presence: ");
    Serial.println(presence ? "true" : "false");

    sendSensorData(temperature, presence);
    getStateAndControlOutputs();
  }
}