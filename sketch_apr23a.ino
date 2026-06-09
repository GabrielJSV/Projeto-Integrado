#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

Adafruit_MPU6050 mpu;

const unsigned long PERIODO_MS = 10;  // ~100 Hz
unsigned long proximaLeitura = 0;

void setup() {
  Serial.begin(115200);
  if (!mpu.begin()) {
    Serial.println("Sensor MPU6050 nao encontrado!");
    while (1) { delay(10); }
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  Serial.println("MPU6050 Conectado!");
}

void loop() {
  unsigned long agora = millis();
  if (agora < proximaLeitura) return;
  proximaLeitura = agora + PERIODO_MS;

  sensors_event_t a, g, temp;
  if (!mpu.getEvent(&a, &g, &temp)) return;

  float ax = a.acceleration.x;
  float ay = a.acceleration.y;
  float az = a.acceleration.z;

  // CSV: ace_x, ace_y, ace_z, t_ms  (a magnitude e calculada no Python)
  Serial.print(ax, 2); Serial.print(',');
  Serial.print(ay, 2); Serial.print(',');
  Serial.print(az, 2); Serial.print(',');
  Serial.println(agora);
}