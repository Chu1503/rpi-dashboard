// Alfred Sony TV IR controller for Arduino UNO Q.
// HX-53 wiring: DAT -> D3, VCC -> 5V, GND -> GND.

#include "Arduino_RouterBridge.h"
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/pwm.h>

constexpr uint8_t IR_SEND_PIN = D3;
constexpr uint16_t SONY_CARRIER_HZ = 40000;
constexpr uint8_t SONY_TV_ADDRESS = 0x01;
constexpr uint8_t SONY_POWER_COMMAND = 0x15;
constexpr uint32_t IR_PERIOD_NS = PWM_HZ(SONY_CARRIER_HZ);
constexpr uint32_t IR_PULSE_NS = IR_PERIOD_NS / 3;  // ~33% carrier duty cycle

// In the UNO Q Zephyr devicetree, D2 is PWM index 0 and D3 is index 1.
static const pwm_dt_spec IR_PWM =
    PWM_DT_SPEC_GET_BY_IDX(DT_PATH(zephyr_user), 1);
bool irPwmReady = false;

bool mark(uint32_t duration_us) {
  if (!irPwmReady || pwm_set_dt(&IR_PWM, IR_PERIOD_NS, IR_PULSE_NS) != 0) {
    return false;
  }
  delayMicroseconds(duration_us);
  pwm_set_dt(&IR_PWM, IR_PERIOD_NS, 0);
  return true;
}

void space(uint32_t duration_us) {
  pwm_set_dt(&IR_PWM, IR_PERIOD_NS, 0);
  delayMicroseconds(duration_us);
}

bool sendSonyBit(bool one) {
  if (!mark(one ? 1200 : 600)) return false;
  space(600);
  return true;
}

void waitForNextFrame(uint32_t frame_started_us) {
  constexpr uint32_t FRAME_PERIOD_US = 45000;
  const uint32_t elapsed = micros() - frame_started_us;
  if (elapsed >= FRAME_PERIOD_US) return;
  const uint32_t remaining = FRAME_PERIOD_US - elapsed;
  delay(remaining / 1000);
  delayMicroseconds(remaining % 1000);
}

bool sendSonyFrame(uint8_t command, uint8_t address, uint8_t addressBits = 5) {
  const uint32_t frame_started_us = micros();
  if (!mark(2400)) return false;
  space(600);

  // Sony SIRC: seven command bits followed by five address bits, all LSB first.
  for (uint8_t bit = 0; bit < 7; ++bit) {
    if (!sendSonyBit((command >> bit) & 0x01)) return false;
  }
  for (uint8_t bit = 0; bit < addressBits; ++bit) {
    if (!sendSonyBit((address >> bit) & 0x01)) return false;
  }

  waitForNextFrame(frame_started_us);
  return true;
}

bool tvPower() {
  if (!irPwmReady) return false;
  // Three frames emulate a deliberate remote-control button press.
  for (uint8_t repeat = 0; repeat < 3; ++repeat) {
    if (!sendSonyFrame(SONY_POWER_COMMAND, SONY_TV_ADDRESS)) return false;
  }
  pwm_set_dt(&IR_PWM, IR_PERIOD_NS, 0);
  return true;
}

bool sendTvCommand(uint8_t command, uint8_t address, uint8_t addressBits) {
  if (!irPwmReady) return false;
  for (uint8_t repeat = 0; repeat < 3; ++repeat) {
    if (!sendSonyFrame(command, address, addressBits)) return false;
  }
  pwm_set_dt(&IR_PWM, IR_PERIOD_NS, 0);
  return true;
}

bool tvVolumeUp() { return sendTvCommand(18, 1, 5); }
bool tvVolumeDown() { return sendTvCommand(19, 1, 5); }
// Direct HDMI selection uses Sony's 15-bit device 26 commands.
bool tvHdmi1() { return sendTvCommand(90, 26, 8); }
bool tvHdmi2() { return sendTvCommand(91, 26, 8); }

void setup() {
  // analogWrite performs the UNO Q core's D3 alternate-function pin setup.
  // We then drive the same timer directly because tone() is tick-limited and
  // cannot generate the 40 kHz carrier required by Sony SIRC on this board.
  analogWriteResolution(8);
  analogWrite(IR_SEND_PIN, 0);
  irPwmReady = pwm_is_ready_dt(&IR_PWM);
  if (irPwmReady) {
    pwm_set_dt(&IR_PWM, IR_PERIOD_NS, 0);
  }
  Bridge.begin();
  Bridge.provide_safe("tv_power", tvPower);
  Bridge.provide_safe("tv_volume_up", tvVolumeUp);
  Bridge.provide_safe("tv_volume_down", tvVolumeDown);
  Bridge.provide_safe("tv_hdmi_1", tvHdmi1);
  Bridge.provide_safe("tv_hdmi_2", tvHdmi2);
}

void loop() {
  // Bridge.provide_safe dispatches tvPower in this safe loop context.
  delay(10);
}
