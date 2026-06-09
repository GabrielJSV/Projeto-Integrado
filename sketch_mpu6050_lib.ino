// =====================================================================
// Versao ALTERNATIVA do firmware, usando a biblioteca MPU6050.h
// (jrowberg / Electronic Cats) -- para quando a lib Adafruit nao funciona.
//
// A saida e IDENTICA a versao Adafruit: "ax,ay,az,t" com ax,ay,az em m/s^2
// e t em ms. Por isso funciona com o mesmo menu.py / analisador.py, sem
// mudar nada no Python.
//
// Instale pelo Library Manager do Arduino:
//   - "MPU6050" (por Electronic Cats)  -> ja inclui I2Cdev e MPU6050.h
//
// DIFERENCA IMPORTANTE: esta biblioteca devolve os valores BRUTOS (int16)
// do sensor. Aqui a gente converte para m/s^2 usando a sensibilidade.
// =====================================================================

#include "Wire.h"
#include "I2Cdev.h"
#include "MPU6050.h"

MPU6050 mpu;

// Sensibilidade do acelerometro (LSB por g), depende da faixa escolhida:
//   +-2g  -> 16384      +-4g  -> 8192
//   +-8g  -> 4096       +-16g -> 2048
const float SENSIBILIDADE = 4096.0;   // combina com a faixa +-8g (no setup)
const float G = 9.80665;              // m/s^2 por g

const unsigned long PERIODO_MS = 10;  // ~100 Hz
unsigned long proximaLeitura = 0;

void setup() {
  Wire.begin();
  Serial.begin(115200);

  mpu.initialize();
  if (!mpu.testConnection()) {
    Serial.println("Sensor MPU6050 nao encontrado!");
    while (1) { delay(10); }
  }
  mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_8);  // +-8g (casa com SENSIBILIDADE)
  mpu.setDLPFMode(MPU6050_DLPF_BW_20);             // filtro interno ~20 Hz (menos ruido)
  Serial.println("MPU6050 Conectado!");
}

void loop() {
  unsigned long agora = millis();
  if (agora < proximaLeitura) return;
  proximaLeitura = agora + PERIODO_MS;

  int16_t rax, ray, raz;
  mpu.getAcceleration(&rax, &ray, &raz);   // valores BRUTOS (int16)

  // Converte bruto -> m/s^2 (mesma unidade da versao Adafruit)
  float ax = (rax / SENSIBILIDADE) * G;
  float ay = (ray / SENSIBILIDADE) * G;
  float az = (raz / SENSIBILIDADE) * G;

  // CSV: ace_x, ace_y, ace_z, t_ms  (a magnitude e calculada no Python)
  Serial.print(ax, 2); Serial.print(',');
  Serial.print(ay, 2); Serial.print(',');
  Serial.print(az, 2); Serial.print(',');
  Serial.println(agora);
}
