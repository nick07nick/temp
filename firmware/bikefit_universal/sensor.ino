/*
 * BikeFit Universal Node v5.1 (Production Candidate)
 * Hardware: Seeed XIAO nRF52840 Sense
 * * FIXES:
 * - Disabled Bluefruit AutoLED (no more ghost blinking).
 * - Clear definitions of Sleep Modes.
 * - todo: use 2 in 1 resistor to switch 3 light levels - low med height
 */

#include <bluefruit.h>
#include <LSM6DS3.h>
#include <Wire.h>

// --- КОНФИГУРАЦИЯ ---
#define DEVICE_NAME       "BF_Node"
#define MANUFACTURER_ID   0xFFFF

// Настройки чувствительности и таймингов
#define MOTION_THRESHOLD  0.15f    // Порог пробуждения (G)
#define TIME_TO_STANDBY   10000    // 10 сек покоя -> STANDBY
#define TIME_TO_SLEEP     300000   // 5 мин покоя -> DEEP SLEEP

// Настройки мигания Синим (мс)
#define BLINK_INTERVAL_ACTIVE  500  // Быстро
#define BLINK_INTERVAL_STANDBY 2000 // Редко
#define BLINK_DURATION         50   // Короткая вспышка

// --- ОБЪЕКТЫ ---
BLEDfu  bledfu;
BLEUart bleuart;
LSM6DS3 myIMU(I2C_MODE, 0x6A);

// --- СОСТОЯНИЕ ---
enum State { ST_ACTIVE, ST_STANDBY, ST_SLEEP };
State current_state = ST_ACTIVE;

bool is_master = false;       
uint8_t command_state = 0;    // 0=OFF, 1=ON
unsigned long last_move_time = 0;

void setup() {
  // 1. Настройка LED (Инверсия: LOW=ON, HIGH=OFF)
  pinMode(LED_RED, OUTPUT);
  digitalWrite(LED_RED, HIGH); 
  
  pinMode(LED_BLUE, OUTPUT);
  digitalWrite(LED_BLUE, HIGH);

  Serial.begin(115200);

  // 2. Инициализация IMU
  if (myIMU.begin() != 0) {
    // Ошибка: Попеременное мигание (Panic Mode)
    while(1) { 
      digitalWrite(LED_RED, LOW); digitalWrite(LED_BLUE, HIGH); delay(100); 
      digitalWrite(LED_RED, HIGH); digitalWrite(LED_BLUE, LOW); delay(100); 
    }
  }

  // 3. Bluetooth Init
  Bluefruit.configPrphBandwidth(BANDWIDTH_AUTO); // Оптимизация скорости
  Bluefruit.begin(1, 1); 
  Bluefruit.setTxPower(4); 
  Bluefruit.setName(DEVICE_NAME);
  
  // ВАЖНО: Отключаем вмешательство библиотеки в работу диода
  Bluefruit.autoConnLed(false); 

  Bluefruit.Periph.setConnectCallback(connect_callback);
  Bluefruit.Periph.setDisconnectCallback(disconnect_callback);

  bledfu.begin();
  bleuart.begin();

  // Сканер
  Bluefruit.Scanner.setRxCallback(scan_callback);
  Bluefruit.Scanner.restartOnDisconnect(true);
  Bluefruit.Scanner.setInterval(160, 80); 
  Bluefruit.Scanner.useActiveScan(true);

  // Старт
  last_move_time = millis();
  startActiveRadio(); 
}

// --- УПРАВЛЕНИЕ РАДИО ---

void startActiveRadio() {
  // Режим ACTIVE: Максимальная отзывчивость
  Bluefruit.Advertising.stop();
  Bluefruit.Scanner.stop();
  
  Bluefruit.Advertising.clearData();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  
  if (is_master) {
     // Мастер включает ПРИКАЗ в пакет
     uint8_t data[3] = { (uint8_t)(MANUFACTURER_ID & 0xFF), (uint8_t)((MANUFACTURER_ID >> 8) & 0xFF), command_state };
     Bluefruit.Advertising.addManufacturerData(data, 3);
  }
  
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.addService(bleuart);
  Bluefruit.Advertising.setInterval(160, 160); // 100ms
  Bluefruit.Advertising.setFastTimeout(0);     
  Bluefruit.Advertising.start(0);
  
  if (!is_master) Bluefruit.Scanner.start(0);
}

void startStandbyRadio() {
  // Режим STANDBY: Экономия, редкие пинги
  Bluefruit.Scanner.stop(); // Сканер выключаем!
  Bluefruit.Advertising.stop();
  
  Bluefruit.Advertising.clearData();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.addService(bleuart);
  
  Bluefruit.Advertising.setInterval(1600, 1600); // 1000ms
  Bluefruit.Advertising.setFastTimeout(0);
  Bluefruit.Advertising.start(0);
}

void stopRadio() {
  // Режим SLEEP: Полная тишина
  Bluefruit.Advertising.stop();
  Bluefruit.Scanner.stop();
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_BLUE, HIGH); 
}

// --- ГЛАВНЫЙ ЦИКЛ ---

void loop() {
  unsigned long now = millis();
  
  // 1. ОПРОС АКСЕЛЕРОМЕТРА
  // В режиме SLEEP проверяем раз в 500мс, иначе раз в 100мс
  int poll_interval = (current_state == ST_SLEEP) ? 500 : 100;
  
  static unsigned long last_poll = 0;
  static float prev_total = 1.0;
  
  if (now - last_poll > poll_interval) {
     last_poll = now;
     float x = myIMU.readFloatAccelX();
     float y = myIMU.readFloatAccelY();
     float z = myIMU.readFloatAccelZ();
     float total = sqrt(x*x + y*y + z*z);
     
     if (abs(total - prev_total) > MOTION_THRESHOLD) {
        last_move_time = now; // Сброс таймера сна при движении
     }
     prev_total = total;
  }

  // 2. ОПРЕДЕЛЕНИЕ РЕЖИМА
  State next_state = current_state;
  unsigned long time_idle = now - last_move_time;

  if (Bluefruit.connected()) {
     next_state = ST_ACTIVE; // Подключен = Активен
  } 
  else if (time_idle < TIME_TO_STANDBY) {
     next_state = ST_ACTIVE;
  } 
  else if (time_idle < TIME_TO_SLEEP) {
     next_state = ST_STANDBY;
  } 
  else {
     next_state = ST_SLEEP;
  }

  // 3. ПЕРЕКЛЮЧЕНИЕ
  if (next_state != current_state) {
     if (next_state == ST_ACTIVE) {
        startActiveRadio();
        if (command_state == 1) digitalWrite(LED_RED, LOW); 
     }
     else if (next_state == ST_STANDBY) {
        startStandbyRadio();
        digitalWrite(LED_RED, HIGH); 
     }
     else if (next_state == ST_SLEEP) {
        stopRadio();
     }
     current_state = next_state;
  }

  // 4. ИНДИКАЦИЯ (СИНИЙ LED)
  handleBlueLed(now);

  // 5. ЛОГИКА МАСТЕРА
  if (is_master && bleuart.available()) {
     uint8_t ch = (uint8_t) bleuart.read();
     if (ch == '1' || ch == '0') {
        command_state = (ch == '1') ? 1 : 0;
        digitalWrite(LED_RED, (command_state) ? LOW : HIGH);
        startActiveRadio(); 
        last_move_time = millis(); 
     }
  }
}

// --- УПРАВЛЕНИЕ СИНИМ LED ---
void handleBlueLed(unsigned long now) {
  // Не мигать, если подключены или спим
  if (Bluefruit.connected() || current_state == ST_SLEEP) {
    digitalWrite(LED_BLUE, HIGH); 
    return;
  }

  unsigned long interval = (current_state == ST_ACTIVE) ? BLINK_INTERVAL_ACTIVE : BLINK_INTERVAL_STANDBY;
  static unsigned long last_blink_time = 0;
  
  if (now - last_blink_time > interval) {
    digitalWrite(LED_BLUE, LOW); // Вспышка
    last_blink_time = now;
  }
  else if (now - last_blink_time > BLINK_DURATION) {
    digitalWrite(LED_BLUE, HIGH); // Гасим
  }
}

// --- CALLBACKS ---
void connect_callback(uint16_t conn_handle) {
  is_master = true;
  last_move_time = millis(); 
  digitalWrite(LED_BLUE, HIGH); 
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason) {
  is_master = false;
  command_state = 0; 
  digitalWrite(LED_RED, HIGH);
  // После разрыва связь переходим в ACTIVE, чтобы быстро найтись снова
  current_state = ST_ACTIVE; 
  last_move_time = millis();
}

void scan_callback(ble_gap_evt_adv_report_t* report) {
  if (is_master) return;
  uint8_t buffer[32];
  uint8_t len = Bluefruit.Scanner.parseReportByType(report, BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC_DATA, buffer, sizeof(buffer));
  if (len >= 3) {
    uint16_t mfg_id = buffer[0] + (buffer[1] << 8);
    if (mfg_id == MANUFACTURER_ID) {
        uint8_t cmd = buffer[2];
        digitalWrite(LED_RED, (cmd == 1) ? LOW : HIGH);
        if (cmd == 1) last_move_time = millis(); 
    }
  }
  Bluefruit.Scanner.resume();
}