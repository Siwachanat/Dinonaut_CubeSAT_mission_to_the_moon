/* SunSeek Platform Firmware v2.1 — PlatformIO port (v2.1-pio)
   Reorganized training architecture: Config / Module / System.
   Runtime baseline: T07 FIX6 Estimator Continuous + MA500.

   Port notes
   - This file is the original SunSeek_Platform_Firmware_v2_1.ino plus
     #include <Arduino.h> (PlatformIO compiles .cpp, not .ino).
   - Config_*.h live in include/ (learner-editable); Module_*.h and System_*.h
     live in src/. All modules are header-only and are compiled in this single
     translation unit, exactly as the Arduino IDE did.
   - Functional changes are listed in Log_Dev.md under "v2.1-pio". */
#include <Arduino.h>
#include "Module_ReactionWheel.h"
#include "System_TTC.h"
#include "Module_IMU.h"
#include "Module_SunSensor.h"
#include "Module_Estimator.h"
#include "System_TelemetryManager.h"
#include "Module_Mission.h"
#include "Module_ADCS.h"
#include "System_Telemetry.h"
#include "Module_Payload.h"
#include "System_CommandRouter.h"

static void boardParkUnusedOutputs(){
#if BOARD_PARK_ULN2003_PINS
  const uint8_t uln[4] = {15, 6, 7, 18};
  for (uint8_t i = 0; i < 4; ++i) { pinMode(uln[i], OUTPUT); digitalWrite(uln[i], LOW); }
#endif
}

void setup(){
  boardParkUnusedOutputs();
  Serial.begin(115200);
  delay(1000);
  rwBegin();
  imuBegin();
  sunSensorBegin();
  adcsBegin();
  payloadUARTBegin();
  communicationBegin(processTelecommand);
  Serial.println("SUNSEEK PLATFORM v2.1 — Training Firmware (PlatformIO port v2.1-pio)");
  Serial.println("Spacecraft ID: "+getSpacecraftID());
  Serial.println("Payload UART: TX=GPIO41 RX=GPIO42 @115200");
  sensorSendHealth();
  ttcSendADCSConfig();
  payloadSendCommand("STATUS");
}

void loop(){
  communicationUpdate();
  payloadUARTUpdate();
  rwUpdate();
  adcsUpdate();
  sensorUpdate();
  sensorADCSUpdate();
  sensorTelemetryUpdate();
  missionUpdate();
  if(rwTakeManeuverCompleteEvent()){
    sendTelemetry("EVT,RW_MANEUVER_COMPLETE,"+String(rwGetCurrentBias()));
    ttcSendRWTelemetry();
  }
}
