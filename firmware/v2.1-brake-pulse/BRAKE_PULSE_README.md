# Timed open-loop brake pulse

This copy adds BRAKE_PULSE,<signed percent>,<duration ms> to the existing USB/BLE terminal command parser. No gyro or LDR is required. It is a motor pulse, NOT detection or confirmation that the body stopped.

## Example

With the mission idle and both body and wheel initially at rest:

```text
ADCS_MODE,MANUAL
ADCS_STRATEGY,REACTION
RW,20
```

After a short, repeatable spin-up interval, send:

```text
BRAKE_PULSE,-20,100
```

Response: ACK,BRAKE_PULSE,-20,100. The motor receives -20 percent for approximately 100 ms, then the existing rwStop() output. EVT,BRAKE_PULSE_COMPLETE reports pulse completion, not body settlement. STOP or RW_STOP cancels early with no completion event. BRAKE_STATUS reports ACTIVE/INACTIVE.

## Limits and behaviour

- Integer nonzero power: -100..100; integer duration: 1..2000 ms. These are software bounds, not hardware-qualified operating limits. Use your characterized motor range.
- Requires MANUAL mode, REACTION strategy, and inactive mission. Active/ready missions are rejected, not silently aborted. Use MISSION_ABORT or MISSION_RESET deliberately if required.
- While pulsing, only STOP, RW_STOP, PING, and BRAKE_STATUS are accepted. Conflicting commands return ERR,BRAKE_PULSE_BUSY.
- Duration uses millis() with wrap-safe arithmetic; no delay(duration). Optional loop work is skipped while active. Existing BLE callbacks and communication latency still mean this is not hard real-time timing. The existing reconnect delay was replaced with a non-blocking delay.
- Disconnect does not cancel a pulse; it expires locally. No automatic direction selection. An inappropriate sign/duration can accelerate or reverse the body.
- Completion uses the original motor STOP pin output; it does not implement coasting or wheel-speed holding. The body can move again as the wheel slows.
- Ground station: send the command in its existing raw TT&C terminal with a newline. No new GUI button is included.

## Build and verification

Open this folder as the PlatformIO project. Build using `pio run -e sunseek`. Hardware validation and motor-direction testing are still required; no firmware has been uploaded by this change.

Validation: the complete main.cpp translation unit (including all modified headers) compiled successfully to an object with the installed Xtensa ESP compiler and saved project include paths/defines. Full PlatformIO build/link could not run because the installed Python click package was unreadable. No bench test or upload performed. The pulse timing is approximate and shares the existing firmware's BLE/USB execution model.
