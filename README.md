# Dinonaut CubeSAT — Mission to the Moon

Archive of the SunSeek firmware and ground-station versions used during the team's light-pointing CubeSat development. The platform rotates on a bearing using an internal reaction wheel, with LDR, gyro and magnetometer feedback.

## Version map

| Folder | Version / purpose |
| --- | --- |
| `firmware/v2.1-original-platformio` | Original supplied PlatformIO project |
| `firmware/v2.1-brake-pulse` | Adds timed open-loop BRAKE_PULSE command |
| `firmware/v2.1-auto-limit` | Retains brake pulse; adds AUTO PWM cap and damping within pointing deadband |
| `firmware/v3.0-original-arduino` | Original supplied Arduino v3.0 sketch |
| `firmware/v3.0-platformio` | Behaviour-preserving PlatformIO conversion of v3.0 |
| `firmware/v3.0-qp1` | PREPARE validates configuration without starting momentum bias |
| `firmware/v3.0-qp2` | QP1 plus QP_STATUS handshake and STOP mission cancellation |
| `ground-station/quiet-prepare-1.0` | New Python/PySide6/Bleak Windows app source, tests and build specification |
| `hardware` | Supplied board pinout reference; some component details are inferred |

## Downloads

See the **Releases** page for the delivered firmware ZIPs, the new Windows app, and the supplied MUT ground stations v1.9 and v1.10. The original MUT applications were supplied as packaged binaries; their editable source was not available. Download and extract the whole application folder, keeping `_internal` beside the EXE.

The new Quiet Prepare app requires **QP2** firmware. Earlier custom BRAKE_PULSE and ADCS_LIMIT features are not merged into v3.0/QP1/QP2. Do not assume commands are interchangeable between versions.

## Build

Firmware: open a PlatformIO version folder containing `platformio.ini`, review team identity and calibration, then Build and Upload. The original v3.0 Arduino version uses its `.ino` sketch. Settings supplied in each version are preserved; they are not guaranteed calibrated for your rig.

Ground station: see `ground-station/quiet-prepare-1.0/USER_GUIDE.txt`, `requirements.txt`, and `build.bat`. Windows build uses PyInstaller. Tests: `python -m unittest discover -s ground-station/quiet-prepare-1.0 -p test_protocol.py` after installing requirements.

## Validation and known issues

- The derived firmware translation units compiled to object files with an installed Xtensa compiler. Full PlatformIO linking was not verified in the development environment.
- The new app passed 10 protocol/workflow tests and a packaged GUI launch check. Physical Bluetooth/control operation has not been certified.
- **Open issue:** the user reported `ERR,UNKNOWN_COMMAND` and disabled RUN with the new app. QP_STATUS exists in the archived QP2 source, but the rejected command and actually flashed firmware remain unconfirmed pending a TX/RX log. Do not treat this issue as resolved.
- Sensor calibration, control direction, PD gains and momentum profiles require rig testing. Motor PWM is not wheel RPM or body rotation rate. STOP does not guarantee immediate physical rest.
- Ground-station camera support sends CAPTURE only; image viewing/downloading is not implemented in the new app.

## Provenance

Original SunSeek/MUT materials retain their original authorship and notices. This archive does not assign a new license to third-party code or binaries. Derived changes were prepared during the Dinonaut CubeSat development chat. `release-assets.json` lists downloadable archive sizes and SHA-256 hashes.

Source folders are normalized to one project per version; nested extracted project copies are omitted there. The release ZIPs preserve the delivered archives.
