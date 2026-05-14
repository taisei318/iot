/*
  sender.ino
  Spresense + KX126 加速度センサのデータを常時シリアル送信する。
  形式: "x,y,z\n"  単位: G  ボーレート: 115200  サンプリング: 約20Hz
*/
#include <Wire.h>
#include "KX126.h"

KX126 kx126(KX126_DEVICE_ADDRESS_1F);

void setup() {
  byte rc;
  Serial.begin(115200);
  Wire.begin();

  rc = kx126.init();
  if (rc != 0) {
    Serial.println("KX126 initialization failed");
    Serial.flush();
  }
}

void loop() {
  byte rc;
  float acc[3];

  rc = kx126.get_val(acc);
  if (rc == 0) {
    Serial.print(acc[0]);
    Serial.print(",");
    Serial.print(acc[1]);
    Serial.print(",");
    Serial.println(acc[2]);
  }

  delay(50);
}
