# SunSeek Platform Firmware v2.1 — PlatformIO (VS Code)

Port of the organisers' Arduino starter `SunSeek_Platform_Firmware_v2_1` to PlatformIO for the
competition kit (GY-89 IMU, TB6612FNG flywheel, paired LDRs, ESP32-CAM). 18 of the 21 source
files are byte-identical to the organisers' code; the three small changes are listed in
`Log_Dev.md` → *v2.1-pio*.

## Open, build, flash

1. VS Code + **PlatformIO IDE** extension. CP210x driver installed (macOS 12+ has it built in).
2. PlatformIO → **Open Project** → this folder. First open downloads the toolchain (~400 MB).
3. ✓ **Build** → → **Upload** → 🔌 **Monitor** (115200). CLI: `pio run -t upload -t monitor`
4. Upload fails to connect: hold **BOOT**, tap **RESET**, release BOOT, upload again.
5. In the monitor type `STATUS` and Enter. Expect `TM,SENSOR_ACCEL,READY`,
   `TM,SENSOR_MAG,READY`, `TM,SENSOR_GYRO,READY` from the GY-89.

## Where things are

```
platformio.ini          board, core, upload/monitor settings
include/Config_*.h      ← learner files: pins, gains, calibration, Sun model
src/main.cpp            setup() / loop()  (was the .ino)
src/Module_*.h          IMU, sun sensor, wheel, estimator, ADCS, mission, payload
src/System_*.h          BLE/USB TT&C, command router, telemetry
```

All modules are header-only and compiled in one translation unit (`main.cpp`), the same
way the Arduino IDE built them. Add new modules as `Module_X.h` and include them in
`main.cpp` before `System_CommandRouter.h`.

## First things to set for the competition kit

| File | Setting | Why |
|---|---|---|
| `Config_System.h` | `TEAM_NAME` | becomes the BLE name `SUNSEEK-<team>` |
| `Config_Sensor.h` | `IMU_BODY_RATE_AXIS` / `_SIGN` | GY-89 mounting decides which axis is the flywheel Z |
| `Config_Sensor.h` | `GYRO_BIAS_*_DPS` | run `GYRO_OFFSET` with the stack still, paste the result |
| `Config_Sensor.h` | `MAG_OFFSET_*`, `MAG_SCALE_*` | `MAG_CAL_START`, rotate slowly 360°, `MAG_CAL_STOP`, paste |
| `Config_Sensor.h` | `estimateSunAngle()` | your calibrated NDV→angle model (default is `90·NDV`) |
| `Config_ADCS.h` | `ADCS_CONTROL_SIGN` | verify with `RW,20` / `RW,-20` before AUTO |

## Telecommands worth knowing (USB monitor or Ground Station BLE)

`STATUS` · `HELP` · `STOP` (safe) · `RW,<-100..100>` · `RW_STOP` · `IMU_STATUS` ·
`GYRO_OFFSET` · `MAG_CAL_START/STOP` · `SUN_RAW` · `GYRO_RAW` · `TM_STREAM,SUN|GYRO|ADCS,ON|OFF` · `TM_RATE,<1..20>` ·
`ADCS_REFERENCE,SUN` · `SET_TARGET,<deg>` · `ADCS_TUNE,<Kp>,<Kd>,<bias>` · `ADCS_MODE,AUTO|MANUAL` ·
`PAYLOAD_STATUS` · `CAPTURE` · `MISSION_*`. Full list: `Interface_Contract.md`.

## Known limits inherited from v2.1

- **Mission stops at `CAPTURING`.** It does not send `CAPTURE`, wait for `IMAGE_READY`,
  or move to the next target. That transaction is yours to add in `Module_Mission.h`.
- **MAG heading needs calibration** before `ADCS_REFERENCE,MAG` is useful; the flywheel
  motor and battery sit near the LSM303D, so calibrate on the assembled stack.
- **LDRs on GPIO16/17 are ADC2.** Don't start Wi-Fi on the ESP32-S3 (BLE already runs alongside them in the organisers' firmware).
- Sun sensor reads one raw `analogRead()` per side, no averaging. Use the estimator's
  moving average or add averaging in `Module_SunSensor.h`.
