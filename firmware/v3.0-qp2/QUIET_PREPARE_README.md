# v3.0-QP1: PREPARE without wheel spin-up

ADCS_PREPARE now validates configuration without applying momentum bias or enabling AUTO. MISSION_PREPARE also requires manual/stopped actuator state. Both strategies are supported. Momentum still requires its full valid profile. ADCS_READY / MISSION_READY are configuration readiness only, not proof of physical rest or stabilized bias. There is no wheel-speed sensor.

Start with both body and wheel stationary. In the raw TT&C terminal:
```
STOP
ADCS_MODE,MANUAL
ADCS_STRATEGY,REACTION
ADCS_PREPARE
```
Expected: ACK,ADCS_PREPARE and EVT,ADCS_READY, motor stays at zero command.

For MOMENTUM, configure the v3.0 profile first, then ADCS_PREPARE. It reports the configured bias but does not apply it. Bias is applied by the existing explicit ADCS_MODE,AUTO start, or by MISSION_START followed by missionUpdate. RUN may therefore produce the original bias-start transient.

PREPARE rejects existing AUTO/nonzero motor command with REQUIRES_MANUAL_STOPPED; it does not automatically stop a spinning wheel. STOP changes motor output and can itself move the body. Wait for physical rest before testing PREPARE.

Ground station v1.10.4 button command sequence has not been inspected. This change guarantees the firmware PREPARE commands do not start the motor. If its PREPARE button separately sends ADCS_MODE,AUTO or RW_BIAS, those remain explicit movement commands; inspect the TX log and use the raw terminal test above. A UI expecting pre-spun bias stability before enabling RUN may need updating for this workflow.

Open this project in PlatformIO, check TEAM_NAME (source default Team_DekMUT) and calibration, build and upload. Boot banner: v3.0-QP1. No earlier BRAKE_PULSE or ADCS_LIMIT changes are merged. Control gains and RUN behaviour are unchanged. No upload or physical testing has been performed here.

Validation: complete main.cpp compiled to an object with the installed Xtensa compiler. Source contract checks confirmed PREPARE has no actuator writes and explicit AUTO still applies profile bias. Full PlatformIO linking, ground-station button integration and hardware testing remain unverified.
