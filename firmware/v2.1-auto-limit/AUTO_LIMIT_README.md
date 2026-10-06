# AUTO damping and command limit update

Includes the previous BRAKE_PULSE feature. No firmware was uploaded by this update.

Changes:
- Gyro damping stays active inside the 2-degree pointing deadband.
- AUTO defaults to a 30% maximum PWM command instead of the previous 80% ceiling.
- ADCS_LIMIT,<integer 1..80> changes the AUTO cap in MANUAL mode. STATUS reports the current cap as MAX_RW_COMMAND.
- The cap applies to both REACTION and MOMENTUM AUTO output, including momentum startup bias. Manual RW/BRAKE_PULSE commands are unchanged.
- Limits reset to 30 on reboot. Gain defaults remain Kp=2.0, Kd=0.5; previous runtime tuning is not saved by the original firmware.
- This limits motor PWM, not rotation speed. It does not guarantee accuracy, prevent overshoot, or overcome gyro bias, wrong control sign, compass interference or motor dead zone. No minimum 30% drive is forced near the target.

Build and upload this project in PlatformIO after checking your team-specific settings. Then, with the gyro offset and direction verified, send commands one line at a time:

```
STOP
ADCS_MODE,MANUAL
ADCS_STRATEGY,REACTION
ADCS_REFERENCE,MAG
ADCS_LIMIT,30
ADCS_TUNE,0.5,1.0,40
SET_TARGET,90
ADCS_MODE,AUTO
```

90 means absolute magnetic heading, not a relative 90-degree turn. Gains above are initial trial values, not calibrated values. Prefer a nearby target for the first bench test. If the motor cannot start at the computed output, report STATUS rather than increasing gains blindly. STOP cancels control; the body may continue moving.

Validation: 10 compile-time regression assertions passed for PD damping and clamping. Full main.cpp translation unit compiled to an object using the installed Xtensa compiler and saved project build settings. Full PlatformIO link/build and physical testing remain unverified; the installed PlatformIO Python package was previously unreadable.
