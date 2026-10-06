# SunSeek v3.0 - PlatformIO project

Conversion of the supplied SunSeek_Platform_Firmware_v3_0.zip for the existing ESP32-S3 board and CP210x USB-UART connection.

## Use
1. Extract this folder and open the folder containing platformio.ini in VS Code / PlatformIO.
2. Set TEAM_NAME in include/Config_System.h (the supplied v3.0 value is Team_DekMUT). Copy your verified sensor calibration and team settings as needed.
3. Connect USB. Build, then Upload; monitor at 115200 baud. Close other serial monitors before upload. If needed specify upload_port = COMx; reduce upload_speed to 460800 if uploads fail.
4. Reconnect the BLE ground station to SUNSEEK-<TEAM_NAME>.

CLI: `pio run -e sunseek`, `pio run -e sunseek -t upload`, `pio device monitor -b 115200`.

## Layout and compatibility
- src/main.cpp is the original sketch with an explicit Arduino.h include.
- Original Config_*.h files are in include/; Module_*.h and System_*.h are in src/.
- Original documentation is preserved in docs/.
- All original headers and their configuration values are preserved byte-for-byte. No control tuning, custom BRAKE_PULSE, ADCS_LIMIT, calibration or prior v2.1 modifications were merged into this v3.0 conversion.
- The pinned pioarduino platform matches the previous PlatformIO project (Arduino ESP32 3.3.x). Board configuration uses the prior project's 4 MB flash setting and UART0 console; check against your actual module if different.
- v3.0 changes momentum AUTO to use configured momentum profiles: see docs/README_v3_0.md and docs/Interface_Contract_v3_0.md.

This project has not been uploaded or tested on hardware by this conversion.

## Validation
All 17 original headers verified byte-for-byte against the source ZIP. Complete main.cpp translation unit compiled to an object using the installed Xtensa compiler and existing ESP32-S3 SDK include paths/defines. A full PlatformIO build/link remains unverified because the installed PlatformIO Python environment previously failed reading its click package. First-time PlatformIO setup needs internet access for its pinned platform and toolchain.
