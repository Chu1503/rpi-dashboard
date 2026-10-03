# Alfred Personal Dashboard

Alfred is a lightweight, always-on personal dashboard for a TV connected to an Arduino UNO Q running Debian. It combines your incomplete Google Tasks, upcoming Google Calendar events, recent Google Health measurements, and current Open-Meteo weather in one native page. The Calendar uses the water-and-duck idea from the old Calendar project; there are no iframes and no second website to run.

The backend uses Flask. The interface is built with React and Tailwind CSS through Vite, then committed as a small production bundle under `static/app/`. The UNO Q serves only those static files: Node.js, Vite, and Tailwind do not run on the device. Alfred still avoids Next.js, Docker, a database, and background workers.

## How it behaves

- The contextual greeting updates locally without reloading the page.
- Up to fourteen incomplete tasks are arranged in seven columns. Seven or fewer tasks use one row; additional tasks expand the section to a second row and move the pond down automatically.
- The browser requests one combined JSON update every 60 seconds.
- Calendar and Tasks refresh at most once per minute. Steps and the latest
  heart-rate measurement use separate lightweight requests every 2 minutes.
  Sleep and the full Health snapshot refresh every 10 minutes, as does weather.
  Health values are the latest data synced into Google Health rather than a live
  Bluetooth stream from the wearable.
- The Calendar panel preserves the original multi-day water-and-duck agenda and looks ahead 14 days by default.
- Each service has its own in-memory and on-disk cache under `data/cache/`.
- If an external API fails, Alfred retains the last successful value—even after a reboot—and clearly labels it as last known.
- If an API has never been configured, that section shows `--` or a subtle setup message. Other sections continue working.
- OAuth credentials and refresh tokens remain only on the Python backend. They are never included in HTML, frontend JavaScript, or API responses.

### Rebuild the frontend on the Windows development PC

The compiled files are already included, so this is needed only after editing `frontend/`:

```powershell
npm install
npm run build
```

Copy or commit the resulting `static/app/dashboard.js` and `static/app/style.css` with the project. The UNO Q does not need npm or Node.js.

## 1. Develop on Windows

### Install Python and create the environment

Install current Python 3 from [python.org](https://www.python.org/downloads/windows/) and enable **Add Python to PATH** during installation. Open PowerShell in the `Alfred` folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```dotenv
DISPLAY_NAME=Chu
WEATHER_LAT=your_decimal_latitude
WEATHER_LON=your_decimal_longitude
```

Open-Meteo needs no API key. Coordinates can be copied from a maps application. Use `ALFRED_HOST=0.0.0.0` for the protected phone remote; Alfred still blocks LAN access to the personal dashboard and its data endpoints.

Start the development server:

```powershell
python app.py
```

Open `http://127.0.0.1:8080`. The page starts even before Google is configured. For a temporary populated visual preview, set `ALFRED_DEMO_MODE=true`; change it back to `false` before real use.

### One-click Windows launcher

After the virtual environment and `.env` have been created, double-click:

```text
start-alfred.bat
```

It starts Waitress in the background, waits for `/healthz`, and opens Alfred in the default browser. Clicking it again only opens the page; it does not create a duplicate server. Logs are stored in `data/logs/`, and the launcher records its process ID under `data/run/`.

To shut down the background server cleanly, double-click:

```text
stop-alfred.bat
```

Run the built-in tests:

```powershell
python -m unittest discover -s tests -v
```

## 2. Configure Google Cloud and the APIs

Google changes its consoles occasionally, but the required objects are stable:

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project, for example **Alfred Dashboard**.
2. In **APIs & Services → Library**, enable **Google Calendar API** and **Google Tasks API**.
3. Enable **Google Health API** if it is available to your project/account.
4. Open **Google Auth Platform** (formerly OAuth consent screen). Configure an app name and support email.
5. Choose the appropriate audience. If the app is External and remains in **Testing**, add your Google account as a test user.
6. Under **Clients**, create an OAuth client of type **Desktop app**. Do not create a web client.
7. Download the client JSON and save it as `data/secrets/client_secret.json`.

Alfred requests only read-only scopes:

- Calendar events and calendar-list metadata (the latter preserves your Google event colors)
- Google Tasks
- Google Health activity/fitness, health metrics/measurements, and sleep

### Important Health and OAuth limitation

The current Google Health API v4 is the successor path for Fitbit/Google health integrations, but its health scopes are classified as **Restricted**. Google may require application verification and a security review before general use. Access also depends on the API being enabled/available for your project and your Fitbit/Google Health data being synced. Alfred handles unavailable Health access safely, but code cannot bypass Google's approval rules.

Google also states that refresh tokens for an External OAuth app in **Testing** can expire after seven days when non-basic scopes are requested. For a genuinely unattended dashboard, move the consent configuration to **In production** and satisfy any verification requirements Google presents. Even with valid OAuth, health values are only as recent as the wearable's last sync; heart rate is therefore shown as the **latest measurement**, never as live.

Official references: [Google Calendar scopes](https://developers.google.com/workspace/calendar/api/auth), [Google Tasks authorization](https://developers.google.com/workspace/tasks/auth), [Google Health API](https://developers.google.com/health), [Google Health scopes and data listing](https://developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list), and [OAuth publishing status](https://support.google.com/cloud/answer/15549945).

## 3. Perform the one-time OAuth authorization

Do this on the Windows PC while a browser is available. The setup scripts request offline access and save refreshable tokens. They never ask for or store your Google password.

Authorize Calendar and Tasks:

```powershell
python auth\setup_google_auth.py
```

Sign in, review the read-only permissions, and approve. The script then confirms that Calendar and Tasks each respond and saves:

```text
data/secrets/google_workspace_token.json
```

Authorize Health separately:

```powershell
python auth\setup_health_auth.py
```

It saves:

```text
data/secrets/google_health_token.json
```

If the Health test fails after authorization, read the limitation above and confirm the Health API, scopes, OAuth publishing state, account access, and device sync. Calendar, Tasks, and weather will still work.

If the script reports `ACCOUNT_NOT_LINKED`, open `https://fitbit.google.com/auth/signup` and complete Google Health/Fitbit setup using the same Google account selected in the OAuth window. Confirm that the Google Health mobile app and Fitbit Air use that account, allow the wearable to sync, and then run `setup_health_auth.py` again.

Restart `python app.py` and confirm:

1. `/api/calendar` contains today's remaining events.
2. `/api/tasks` contains incomplete tasks.
3. `/api/weather` contains Celsius temperature and a condition.
4. `/api/health` contains values where Google has made synced data available.

The JSON endpoints contain data plus freshness metadata, never OAuth tokens or client secrets.

## 4. Copy or clone to the Arduino UNO Q

Copy the complete `Alfred` folder to the UNO Q, including `.env` and `data/secrets/`. These contain private credentials, so use your private LAN, SSH/SCP, or a private removable drive—not a public repository.

On Debian, open a terminal in the copied folder:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
chmod 700 data/secrets
chmod 600 data/secrets/*.json
chmod +x start-dashboard.sh install-kiosk-autostart.sh
```

All paths in the Python application are based on the project directory with `pathlib`; there are no hardcoded Windows or Linux project paths.

## 5. Start Alfred and Chromium kiosk mode

From a graphical desktop terminal:

```bash
./start-dashboard.sh
```

The script starts Waitress (a small production WSGI server), polls `/healthz` until it responds, and then starts Chromium with:

- `--kiosk`
- `--no-first-run`
- `--disable-session-crashed-bubble`
- `--disable-infobars`

Server logs go to `data/logs/alfred.log`. The script does not disable GPU rendering or browser features required by the calendar artwork.

## 6. Start automatically with the graphical desktop

Do not configure this until `./start-dashboard.sh` works manually. Then run the opt-in installer once:

```bash
./install-kiosk-autostart.sh
```

The installer creates `~/.config/autostart/alfred.desktop` using Alfred's real absolute path. It makes no system-wide changes. Log out and back in, or reboot, to test it. To disable autostart later, remove that one file.

Graphical-session autostart is preferable to a system service here because Chromium needs the active display session. Alfred's refresh tokens allow the backend to renew normal access tokens after reboots; routine interactive login is not required unless Google expires/revokes the refresh token or requires new consent.

## One-click updates from Windows

After the initial UNO installation, double-click `deploy-to-uno.bat` on the Windows development computer. It packages the current project, excludes `.env`, OAuth tokens, cache, logs, virtual environments, and Git data, uploads the update to `arduino@alfred.local`, installs changed Python requirements, restarts only `alfred.service`, and asks the existing kiosk to reload. It deliberately does **not** reboot Linux, because rebooting while the television is not fully ready can leave the UNO Q with no HDMI sound card until the next good boot.

If Windows cannot resolve `alfred.local`, the same launcher automatically tries
`192.168.1.41`. It prints a warning showing the selected address and otherwise
continues normally. Override the fallback later, if needed, with
`-FallbackAddress NEW_IP`; no source-file edit is required.

To stop repeated SSH password prompts, run `setup-uno-ssh-key.bat` once. Leave
the new key's passphrase blank when prompted, then enter the UNO account password
once to install its public half. The private key stays in the Windows user's `.ssh`
folder and the UNO password is never saved. Subsequent normal deployments use that
key and require neither repeated password prompts nor a sudo password.

The launcher uses normal Windows OpenSSH authentication. Without the optional SSH
key, Windows may ask for the UNO password during upload and installation. It does
not save passwords or change sudo permissions automatically.

To use a different address without editing the script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-to-uno.ps1 -Target arduino@NEW_IP
```

A full reboot is never needed for an ordinary code update. If one is intentionally
required for system maintenance, keep the TV powered on and HDMI selected, then run
the PowerShell script with `-Reboot`; this explicit mode may request the UNO sudo
password.

If `/proc/asound/cards` says `--- no soundcards ---`, keep the TV powered on and
double-click `recover-uno-audio.bat`. It performs only the required recovery reboot,
asks for the UNO password once, and does not deploy or change Alfred.

## Internal endpoints

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Local readiness check |
| `GET /api/tasks` | Incomplete Google Tasks |
| `GET /api/calendar` | Today's unfinished/upcoming Calendar events |
| `GET /api/health` | Steps, most recent sleep, latest heart-rate measurement |
| `GET /api/steps` | Independently cached current-day step rollup |
| `POST /api/steps/refresh` | Force only the step rollup to refresh |
| `GET /api/heart-rate` | Independently cached latest heart-rate measurement |
| `POST /api/heart-rate/refresh` | Force only the heart-rate measurement to refresh |
| `GET /api/weather` | Open-Meteo current Celsius weather |
| `GET /api/dashboard` | All four sections, fetched concurrently |
| `GET /remote` | Phone-sized Sony television remote |
| `GET /api/tv/status` | UNO Q Router Bridge availability |
| `POST /api/tv/power` | Protected Sony IR power toggle |
| `POST /api/display/refresh` | Protected phone command that refreshes and reloads the TV dashboard |
| `GET /api/display/control` | Loopback-only one-shot command feed consumed by the kiosk |
| `POST /api/assistant/query` | Protected grounded phone question or command |
| `GET /api/assistant/latest` | Loopback-only TV response feed |
| `GET /api/voice/status` | Loopback-only USB microphone/wake-word status |

## Phone TV remote and IR transmitter

Alfred includes a phone interface at `http://UNO_IP:8080/remote`. The phone sends
only a small authenticated command over Wi-Fi; the UNO Q's STM32 microcontroller
generates the time-sensitive Sony SIRC infrared signal. The private Tasks,
Calendar, Health, and Weather routes remain accessible only from the UNO Q itself.

With the UNO Q powered off, connect the HX-53 transmitter:

| HX-53 | UNO Q MCU header |
|---|---|
| `DAT` | `D3` |
| `VCC` | `5V` |
| `GND` | `GND` |

Do not use the 1.8 V MPU/JCTL header. Initially place the clear IR LED 5–15 cm
from the TV's infrared sensor. The receiver board is not needed for this test.

Flash `hardware/alfred_ir/alfred_ir.ino` to the UNO Q MCU once using Arduino IDE
2 or Arduino App Lab. Select **Arduino UNO Q** and the UNO Q network/USB port,
then upload the sketch. It registers the `tv_power` Bridge RPC and persists over
normal reboots. The Linux `arduino-router` service starts automatically.

Set a private 12+ character `TV_REMOTE_TOKEN` in the Windows `.env`. The one-click
deployment script safely merges `ALFRED_HOST=0.0.0.0` and that access key into the
UNO Q's existing `.env` without replacing its Google tokens or other settings.
After deployment, open this on a phone connected to the same trusted Wi-Fi:

```text
http://alfred.local:8080/remote
```

Expand **Remote access key**, enter the `TV_REMOTE_TOKEN` once, and save it. The
large button works over normal LAN HTTP. Android keyboard dictation works in the
command field. A one-tap Listen button is shown where Web Speech is available;
browsers may require HTTPS before granting direct microphone permission.

The normal Sony power command is a toggle. Use it while the TV is in standby,
because sending it while the TV is on can turn the TV off.

## Alfred Android voice companion

The native Android companion under `android-companion/` is the recommended phone
interface. It contains one large Sony IR power toggle, one microphone button, one
text field with an Enter button, the grounded Alfred response beneath them, and a
small reload icon at the top-right. The reload icon tells the kiosk to force-refresh
all dashboard sources and then reload Chromium once; it does not reboot the UNO or
change its display, sleep, lock-screen, or kiosk settings.

The companion does not run an LLM and never receives Google tokens. It sends an
authenticated question to the UNO Q, where Alfred reads the dashboard's frequently
refreshed cache for a fast response. The answer returns to the phone and is
also displayed and spoken by the TV dashboard through its HDMI audio output.

Supported questions include:

```text
What are my tasks?
How does my day look?
What is my next event?
What is on my calendar today?
How much did I sleep?
How many steps do I have?
What is my latest heart rate?
What is the weather?
Turn the TV on
Turn the TV off
```

### Install the companion on an Android phone

1. Deploy the latest backend by double-clicking `deploy-to-uno.bat`. The normal
   deployment restarts Alfred and reloads Chromium without rebooting Linux or
   disturbing HDMI audio. It does not change XFCE screensaver, Light Locker, DPMS,
   suspend, or the existing never-lock configuration.
2. The verified APK is at
   `android-companion/app/build/outputs/apk/debug/app-debug.apk`.
3. Copy the APK to the phone with USB, Google Drive, or another private method.
4. Open it. Android may ask you to allow installing unknown apps for that file
   manager or Drive once. Approve that source and install **Alfred**.
5. On first launch, leave the UNO address as `http://alfred.local:8080` and enter
   the exact `TV_REMOTE_TOKEN` value from Alfred's `.env`.
6. Keep the phone and UNO Q on the same trusted Wi-Fi. Test a typed question, then
   tap the microphone and grant microphone access once. Recognition stays inside
   Alfred instead of opening Google's full-screen prompt. Android's speech service
   may use the internet unless an offline English recognition pack is installed.
7. To change the UNO address or access key later, long-press **ALFRED**.

To rebuild after editing the Android code, open `android-companion/` in Android
Studio, wait for Gradle sync, and select **Build → Build APK(s)**. Android tooling is
not installed or run on the UNO Q.

### Confirm TV speech

After deploying and rebooting, ask a typed question while the TV is on. The answer
should appear on the TV and play through its speakers. If the card appears without
audio, first confirm that the UNO's selected audio output is HDMI:

```bash
wpctl status
speaker-test -c 2 -t wav
```

Alfred normally uses Microsoft's free Edge neural speech service with the
conversational British male `en-GB-RyanNeural` voice. This produces natural speech,
but the reply text is sent to Microsoft's service and it requires internet access.
You can change `ALFRED_TTS_VOICE` in `.env`; Microsoft's current voice catalog is
linked below. If it is unavailable, Alfred automatically falls back to the local
Piper `en_GB-semaine-medium` Obadiah voice, then to `espeak-ng`. The one-click
deployment downloads Piper's approximately 77 MB fallback model once.

Voice catalogs:

- Microsoft neural voices: https://learn.microsoft.com/azure/ai-services/speech-service/language-support
- Piper local voices and samples: https://rhasspy.github.io/piper-samples/

To try another Microsoft voice, add or change `ALFRED_TTS_VOICE` in the Windows
project's `.env`, then run `deploy-to-uno.bat`. For example,
`en-GB-RyanNeural`, `en-GB-AlfieNeural`, or `en-GB-OliverNeural`.

Install the small fallback voice once if it is not already present:

```bash
sudo apt update
sudo apt install -y espeak-ng
sudo reboot
```

Chromium polls for a reply four times per second and progressively plays Microsoft's
MP3 stream as its first chunks arrive. If streaming fails, Alfred automatically
falls back to the proven, HDMI-friendly 48 kHz stereo WAV path. The kiosk keeps its
HDMI stream warm, and `scripts/configure-tv-audio.sh` restores the real HDMI sink to
100% volume after login without touching the TV's own volume. The local Piper voice
and eSpeak remain offline fallbacks.

The browser fallback remains at `http://alfred.local:8080/remote`. Plain HTTP can
block direct browser microphone access, but typing and Android keyboard dictation
continue to work.

## Always-on USB microphone and “Alfred” wake word

The UNO listener uses the free, offline `vosk-model-small-en-us-0.15` model at
16 kHz mono. It automatically selects the first ALSA capture card whose sysfs path
belongs to USB, so it never mistakes the UNO's built-in HDMI device for a microphone.
The model is downloaded once by `deploy-to-uno.bat`. No microphone audio leaves the
UNO; only Alfred's spoken reply uses the separately configured Microsoft voice.

Connect the Movo microphone's 3.5 mm TRS plug to its supplied USB audio adapter,
then connect that adapter to a data-capable USB-A port on the powered USB-C hub. The
UNO Q must be operating as a USB host. Check detection on the UNO with:

```bash
cd /home/arduino/Alfred
./scripts/check-microphone.sh
```

A successful result names a device such as `plughw:CARD=Device,DEV=0`. To record
five seconds and play it back through the television:

```bash
./scripts/check-microphone.sh --record
```

After deployment, inspect the unattended listener with:

```bash
curl -s http://127.0.0.1:8080/api/voice/status
journalctl -u alfred.service -n 40 --no-pager
```

When `listening` is `true`, either speak the command in one sentence—“Alfred, show
my calendar for today”—or say “Alfred”, pause, and speak the command within seven
seconds. Supported requests are the same as the phone companion. The listener
stops recording while the television speaks, preventing Alfred's own answer from
triggering another command. If the adapter is unplugged, it retries automatically
every five seconds.

If `lsusb` and `arecord -l` do not show a separate USB audio device, the problem is
below Alfred: reconnect the USB adapter, try another data-capable hub port, and
ensure the hub has external USB-C Power Delivery. Do not configure the built-in
`Arduino-Imola-HPH-LOUT` card as the microphone; that is the HDMI audio path.

## Security and maintenance

- `.env`, `data/secrets/*`, cached runtime data, and logs are excluded from Git.
- `ALFRED_HOST=0.0.0.0` allows the protected phone remote to work. Alfred rejects LAN access to the personal dashboard and data endpoints; still use it only on a trusted LAN and keep `TV_REMOTE_TOKEN` private.
- Back up `.env` and `data/secrets/` privately. Without them, rerun the one-time authorization scripts.
- Update occasionally with `source .venv/bin/activate` and `python -m pip install --upgrade -r requirements.txt`, then restart Alfred.
- Alfred needs no n8n, database, Docker daemon, cron job, or manual daily process. The local server only needs to remain running; Chromium polls it automatically.
