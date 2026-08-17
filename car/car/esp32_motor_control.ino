#include <WiFi.h>

// Replace these with your lab Wi‑Fi SSID and password.
const char* ssid = "EE303_0";
const char* password = "EE5040701";

const uint8_t ENA = 14;
const uint8_t IN1 = 27;
const uint8_t IN2 = 26;
const uint8_t IN3 = 25;
const uint8_t IN4 = 33;
const uint8_t ENB = 32;

WiFiServer server(8888);

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void enableMotorDrivers() {
  digitalWrite(ENA, HIGH);
  digitalWrite(ENB, HIGH);
}

void setMotorPair(bool left_a, bool left_b, bool right_a, bool right_b) {
  digitalWrite(IN1, left_a);
  digitalWrite(IN2, left_b);
  digitalWrite(IN3, right_a);
  digitalWrite(IN4, right_b);
}

void moveForward() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void moveBackward() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void turnLeft() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void turnRight() {
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void setup() {
  Serial.begin(115200);

  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENB, OUTPUT);

  enableMotorDrivers();
  stopMotors();

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.print("ESP32 connected to WiFi: ");
  Serial.println(WiFi.SSID());
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  server.begin();
  Serial.println("TCP server started on port 8888");
}

void loop() {
  WiFiClient client = server.available();
  if (!client) {
    return;
  }

  String request = "";
  while (client.connected()) {
    if (client.available()) {
      char c = client.read();
      if (c == '\n') {
        break;
      }
      request += c;
    }
  }

  request.trim();
  if (request.length() > 0) {
    Serial.print("Received: ");
    Serial.println(request);

    if (request == "F") {
      moveForward();
    } else if (request == "B") {
      moveBackward();
    } else if (request == "L") {
      turnLeft();
    } else if (request == "R") {
      turnRight();
    } else if (request == "S") {
      stopMotors();
    }

    client.println("OK");
  }

  client.stop();
}
