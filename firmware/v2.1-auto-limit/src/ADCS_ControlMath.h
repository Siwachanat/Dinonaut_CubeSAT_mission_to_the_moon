#pragma once
// Pure helpers shared by the controller and compile-time regression checks.
constexpr float adcsPDCommand(float error, float rate, float kp, float kd, float deadband) {
  return ((error >= deadband || error <= -deadband) ? kp * error : 0.0f) - kd * rate;
}
constexpr float adcsClampCommand(float value, float low, float high) {
  return value < low ? low : (value > high ? high : value);
}
