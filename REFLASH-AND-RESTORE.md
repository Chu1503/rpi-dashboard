# Alfred UNO Q reflash and restore

Arduino identifies missing HDMI audio as a symptom of older or damaged UNO Q
Linux images. Reflashing erases the Linux filesystem, so finish the credential
backup before starting.

## 1. Before flashing

1. Confirm that a timestamped folder exists under
   `C:\Users\Ryuga\Documents\Alfred-UNO-Backups`.
2. It must contain `Alfred\.env` and these files under
   `Alfred\data\secrets`:
   - `client_secret.json`
   - `google_health_token.json`
   - `google_workspace_token.json`
3. Keep that folder private. The files grant access to Alfred's Google data.
4. The Windows Alfred source, Android APK, deployment SSH key, and MCU sketch
   already remain on Windows and are not erased by the Linux reflash.

## 2. Flash the latest official image

The official stable Arduino Flasher CLI v0.5.3 is already staged at
`C:\Users\Ryuga\Downloads\Arduino-Flasher-CLI-v0.5.3\tool\arduino-flasher-cli.exe`.

1. Install or update Arduino App Lab on Windows from
   <https://www.arduino.cc/en/software/#app-lab-section>. It will be used for
   fresh-board setup after flashing.
2. Disconnect the USB microphone and IR jumper wires from the UNO Q. Keep a
   note that the transmitter uses `DAT -> D3`, `VCC -> 5V`, and `GND -> GND`.
3. Connect the UNO Q directly to the Windows PC using a reliable USB-C **data**
   cable. Avoid an unpowered hub during flashing.
4. With the UNO powered off, use the **Preparing the hardware** diagram in the
   official guide to bridge the correct two JCTL EDL pins. Do not guess them.
5. Open PowerShell and run:

   ```powershell
   cd "$env:USERPROFILE\Downloads\Arduino-Flasher-CLI-v0.5.3\tool"
   .\arduino-flasher-cli.exe flash latest
   ```

6. Confirm the erase when prompted and wait for success. Do not disconnect
   power or USB while the image is being written.
7. If it stops at `Waiting for EDL Device`, follow Arduino's Windows EDL/QDL
   driver instructions before retrying; do not disconnect it mid-write.
8. After success, disconnect power, remove the EDL jumper, and reconnect the
   UNO normally.

Official guide: <https://docs.arduino.cc/software/app-lab/configure/flash/>

## 3. Complete the fresh-board setup

1. Keep the USB microphone disconnected for this first setup.
2. In App Lab, configure the Linux user as `arduino`.
3. Name the board `alfred` so the phone continues to use `alfred.local`.
4. Reconnect it to the same Wi-Fi network used by the phone and Windows PC.
5. Install every board-software update offered by App Lab before restoring
   Alfred.
6. Confirm Windows can reach the board:

   ```powershell
   ping alfred.local
   ```

   If mDNS does not resolve, obtain the UNO's new address with `hostname -I`
   from its local terminal.

## 4. Restore Alfred

From Windows, double-click:

`D:\Projects\Alfred\restore-after-reflash.bat`

The restore will:

- install the existing deployment SSH key (one UNO password prompt);
- restore `.env` and Google OAuth credentials;
- deploy the latest dashboard and speech/wake-word code;
- ask once for sudo to recreate `alfred.service`;
- recreate Chromium kiosk autostart;
- restore the no-lock/no-blank configuration;
- disable Wi-Fi power saving; and
- verify the backend health endpoint.

If `alfred.local` does not resolve, open Command Prompt and use the address
shown by `hostname -I`:

```bat
D:\Projects\Alfred\restore-after-reflash.bat -Target arduino@NEW_IP_ADDRESS -FallbackAddress NEW_IP_ADDRESS
```

## 5. Verify HDMI before reconnecting the microphone

On the UNO:

```bash
cat /proc/asound/cards
```

Do not continue unless `ArduinoImolaHPH` appears. Then reconnect the USB
microphone and run:

```bash
/home/arduino/Alfred/scripts/configure-tv-audio.sh
sudo systemctl restart alfred.service
sleep 10
cat /proc/asound/cards
curl -s http://127.0.0.1:8080/api/voice/status
wpctl get-volume @DEFAULT_AUDIO_SINK@
```

Expected results:

- both `ArduinoImolaHPH` and `USB Audio Device` exist;
- voice status contains `"listening":true`; and
- the default HDMI volume is `1.00`.

## 6. Verify IR and the phone

1. Reconnect the IR transmitter: `DAT -> D3`, `VCC -> 5V`, `GND -> GND`.
2. Open the existing phone APK. It should reconnect through
   `http://alfred.local:8080`.
3. Test the power icon, typed assistant query, and voice input.
4. Say `Computer, calendar for today` and confirm one beep followed by the
   response through the TV.
5. If the power button reports that `tv_power` is unavailable, upload
   `D:\Projects\Alfred\hardware\alfred_ir\alfred_ir.ino` using Arduino IDE.
