// AmazingHand controller for the Chestnut/TetherIA XIAO ESP32-S3 PCB.
// Uses eight Feetech SCS0009 servos (IDs 1..8) and starts torque-disabled.

#include <Arduino.h>
#include <Preferences.h>
#include <SCSCL.h>

namespace {

constexpr uint32_t HOST_BAUD = 921600;
constexpr uint32_t SERVO_BAUD = 1000000;
constexpr int SERVO_RX_PIN = 2;
constexpr int SERVO_TX_PIN = 3;
constexpr uint8_t SERVO_COUNT = 8;
constexpr uint8_t SERVO_IDS[SERVO_COUNT] = {1, 2, 3, 4, 5, 6, 7, 8};

// Every USB packet remains 16 bytes, matching the original TetherIA framing.
constexpr uint8_t OP_SET_ID = 0x02;
constexpr uint8_t OP_CALIBRATE_ZERO = 0x04;
constexpr uint8_t OP_RESET_CALIBRATION = 0x05;
constexpr uint8_t OP_CTRL_1_TO_7 = 0x11;
constexpr uint8_t OP_CTRL_8_COMMIT = 0x13;
constexpr uint8_t OP_ARM = 0x30;
constexpr uint8_t OP_DISARM = 0x31;
constexpr uint8_t OP_PING_ALL = 0x32;
constexpr uint8_t OP_SET_SPEED = 0x33;

constexpr uint8_t REG_ID = 5;
constexpr uint8_t BROADCAST_ID = 0xFE;
constexpr uint16_t DEFAULT_SPEED = 6;

SCSCL servos;
Preferences preferences;
bool armed = false;
int16_t target_centidegrees[SERVO_COUNT] = {0};
uint16_t zero_raw[SERVO_COUNT] = {511, 511, 511, 511, 511, 511, 511, 511};
uint16_t motion_speed = DEFAULT_SPEED;

uint16_t readU16(const uint8_t* data) {
  return static_cast<uint16_t>(data[0]) |
         (static_cast<uint16_t>(data[1]) << 8);
}

int16_t readI16(const uint8_t* data) {
  return static_cast<int16_t>(readU16(data));
}

void putU16(uint8_t* data, uint16_t value) {
  data[0] = static_cast<uint8_t>(value & 0xFF);
  data[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

void sendAck(uint8_t opcode, const uint16_t words[7]) {
  uint8_t frame[16] = {opcode, 0};
  for (uint8_t i = 0; i < 7; ++i) {
    putU16(&frame[2 + 2 * i], words[i]);
  }
  Serial.write(frame, sizeof(frame));
  Serial.flush();
}

void sendStatus(uint8_t opcode, uint16_t first, uint16_t second = 0) {
  uint16_t words[7] = {first, second, 0, 0, 0, 0, 0};
  sendAck(opcode, words);
}

bool servoPresent(uint8_t id) {
  (void)servos.Ping(id);
  return !servos.getLastError();
}

uint8_t scanSingleServo(uint8_t* found) {
  uint8_t count = 0;
  uint8_t first = 0xFF;
  for (uint16_t id = 0; id <= 253; ++id) {
    if (id == BROADCAST_ID) continue;
    if (servoPresent(static_cast<uint8_t>(id))) {
      if (count == 0) first = static_cast<uint8_t>(id);
      ++count;
      if (count > 1) break;
    }
  }
  if (found) *found = first;
  return count;
}

// Matches rustypot's SCS0009 conversion: 0 degrees is raw 511 and the
// full raw span represents 300 degrees.
uint16_t centidegreesToRaw(uint8_t servo_index, int16_t centidegrees) {
  float degrees = static_cast<float>(centidegrees) / 100.0f;
  degrees = constrain(degrees, -149.0f, 149.0f);
  int raw = static_cast<int>(lroundf(
      static_cast<float>(zero_raw[servo_index]) + (1024.0f * degrees / 300.0f)));
  return static_cast<uint16_t>(constrain(raw, 0, 1023));
}

// The original AmazingHand Python GUI passes levels 1..6 to rustypot as
// radians/second. Rustypot converts those SI values to the SCS0009 raw speed
// register using 300 degrees / 1024 counts. FTServo_Arduino expects that raw
// register value directly, so reproduce the conversion here.
uint16_t speedLevelToRaw(uint16_t level) {
  const float radians_per_count = radians(300.0f) / 1024.0f;
  return static_cast<uint16_t>(lroundf(static_cast<float>(level) / radians_per_count));
}

void loadCalibration() {
  preferences.begin("amazinghand", true);
  for (uint8_t i = 0; i < SERVO_COUNT; ++i) {
    char key[5];
    snprintf(key, sizeof(key), "z%u", static_cast<unsigned>(i + 1));
    zero_raw[i] = preferences.getUShort(key, 511);
    if (zero_raw[i] > 1023) zero_raw[i] = 511;
  }
  motion_speed = preferences.getUShort("speed", DEFAULT_SPEED);
  if (motion_speed < 1 || motion_speed > 6) motion_speed = DEFAULT_SPEED;
  preferences.end();
}

void saveZero(uint8_t index, uint16_t raw) {
  char key[5];
  snprintf(key, sizeof(key), "z%u", static_cast<unsigned>(index + 1));
  preferences.begin("amazinghand", false);
  preferences.putUShort(key, raw);
  preferences.end();
  zero_raw[index] = raw;
}

void saveSpeed() {
  preferences.begin("amazinghand", false);
  preferences.putUShort("speed", motion_speed);
  preferences.end();
}

void setTorque(bool enable) {
  for (uint8_t id : SERVO_IDS) {
    servos.EnableTorque(id, enable ? 1 : 0);
  }
  armed = enable;
}

void commitTargets() {
  if (!armed) return;
  uint16_t positions[SERVO_COUNT];
  uint16_t times[SERVO_COUNT] = {0};
  uint16_t speeds[SERVO_COUNT];
  for (uint8_t i = 0; i < SERVO_COUNT; ++i) {
    positions[i] = centidegreesToRaw(i, target_centidegrees[i]);
    speeds[i] = speedLevelToRaw(motion_speed);
  }
  servos.SyncWritePos(const_cast<uint8_t*>(SERVO_IDS), SERVO_COUNT,
                      positions, times, speeds);
}

// SET_ID ACK words: old ID, requested/new ID, status.
// Status: 0 success, 1 no servo, 2 multiple servos, 3 ID occupied,
// 4 EEPROM write/verification failed, 5 invalid requested ID.
void handleSetId(const uint8_t* payload) {
  const uint16_t requested = readU16(payload);
  uint16_t ack[7] = {0xFFFF, requested, 0, 0, 0, 0, 0};
  if (requested < 1 || requested > 8) {
    ack[2] = 5;
    sendAck(OP_SET_ID, ack);
    return;
  }

  setTorque(false);
  uint8_t old_id = 0xFF;
  const uint8_t found_count = scanSingleServo(&old_id);
  if (found_count == 0) {
    ack[2] = 1;
    sendAck(OP_SET_ID, ack);
    return;
  }
  if (found_count > 1) {
    ack[2] = 2;
    sendAck(OP_SET_ID, ack);
    return;
  }

  ack[0] = old_id;
  if (old_id != requested && servoPresent(static_cast<uint8_t>(requested))) {
    ack[2] = 3;
    sendAck(OP_SET_ID, ack);
    return;
  }

  if (old_id != requested) {
    servos.unLockEprom(old_id);       // SCS0009 lock register is address 48.
    const int write_result = servos.writeByte(old_id, REG_ID,
                                               static_cast<uint8_t>(requested));
    delay(20);
    servos.LockEprom(static_cast<uint8_t>(requested));
    delay(20);
    if (write_result < 0 || !servoPresent(static_cast<uint8_t>(requested))) {
      ack[2] = 4;
      sendAck(OP_SET_ID, ack);
      return;
    }
  }

  ack[0] = old_id;
  ack[1] = requested;
  ack[2] = 0;
  sendAck(OP_SET_ID, ack);
}

// A requested ID of 0 calibrates every responding servo in IDs 1..8.
// ACK words: calibrated bitmask, first raw position, status.
void handleCalibrateZero(const uint8_t* payload) {
  setTorque(false);
  const uint16_t requested = readU16(payload);
  uint16_t mask = 0;
  uint16_t first_raw = 0xFFFF;
  if (requested > 8) {
    uint16_t ack[7] = {0, 0xFFFF, 2, 0, 0, 0, 0};
    sendAck(OP_CALIBRATE_ZERO, ack);
    return;
  }

  for (uint8_t index = 0; index < SERVO_COUNT; ++index) {
    const uint8_t id = SERVO_IDS[index];
    if (requested != 0 && requested != id) continue;
    const int raw = servos.ReadPos(id);
    if (raw < 0 || raw > 1023) continue;
    saveZero(index, static_cast<uint16_t>(raw));
    if (first_raw == 0xFFFF) first_raw = static_cast<uint16_t>(raw);
    mask |= static_cast<uint16_t>(1u << index);
  }
  const uint16_t status = mask ? static_cast<uint16_t>(0) : static_cast<uint16_t>(1);
  uint16_t ack[7] = {mask, first_raw, status, 0, 0, 0, 0};
  sendAck(OP_CALIBRATE_ZERO, ack);
}

void handleResetCalibration() {
  setTorque(false);
  preferences.begin("amazinghand", false);
  for (uint8_t index = 0; index < SERVO_COUNT; ++index) {
    char key[5];
    snprintf(key, sizeof(key), "z%u", static_cast<unsigned>(index + 1));
    preferences.remove(key);
    zero_raw[index] = 511;
  }
  preferences.end();
  sendStatus(OP_RESET_CALIBRATION, 0);
}

void handleFrame(uint8_t opcode, const uint8_t* payload) {
  switch (opcode) {
    case OP_SET_ID:
      handleSetId(payload);
      break;
    case OP_CALIBRATE_ZERO:
      handleCalibrateZero(payload);
      break;
    case OP_RESET_CALIBRATION:
      handleResetCalibration();
      break;
    case OP_CTRL_1_TO_7:
      for (uint8_t i = 0; i < 7; ++i) {
        target_centidegrees[i] = readI16(&payload[2 * i]);
      }
      break;
    case OP_CTRL_8_COMMIT:
      target_centidegrees[7] = readI16(payload);
      commitTargets();
      break;
    case OP_ARM:
      setTorque(true);
      sendStatus(OP_ARM, 0);
      break;
    case OP_DISARM:
      setTorque(false);
      sendStatus(OP_DISARM, 0);
      break;
    case OP_PING_ALL: {
      uint16_t present_mask = 0;
      for (uint8_t i = 0; i < SERVO_COUNT; ++i) {
        if (servoPresent(SERVO_IDS[i])) present_mask |= (1u << i);
      }
      sendStatus(OP_PING_ALL, present_mask, 0x00FF);
      break;
    }
    case OP_SET_SPEED: {
      uint16_t requested = readU16(payload);
      motion_speed = static_cast<uint16_t>(constrain(requested, 1, 6));
      saveSpeed();
      sendStatus(OP_SET_SPEED, motion_speed);
      break;
    }
    default:
      break;
  }
}

}  // namespace

void setup() {
  Serial.begin(HOST_BAUD);
  Serial2.begin(SERVO_BAUD, SERIAL_8N1, SERVO_RX_PIN, SERVO_TX_PIN);
  servos.pSerial = &Serial2;
  delay(100);
  loadCalibration();
  setTorque(false);
}

void loop() {
  if (Serial.available() < 16) {
    delay(1);
    return;
  }

  const int op = Serial.read();
  uint8_t rest[15];
  const size_t received = Serial.readBytes(rest, sizeof(rest));
  if (op < 0 || received != sizeof(rest)) return;
  handleFrame(static_cast<uint8_t>(op), &rest[1]);  // rest[0] is filler.
}

