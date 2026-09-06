#!/usr/bin/env bash
# XFCE computer: full session, no apps open at boot (everything via the dock).
set -uo pipefail
export DISPLAY="${DISPLAY:-:1}"
export HOME="${HOME:-/home/user}"
USER_HOME="$HOME"
mkdir -p "$USER_HOME" /tmp/yourdaas /tmp/.X11-unix
cd "$USER_HOME"

rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# Brave locks the profile (Singleton*) if the container died with it open; the
# stale lock in the persistent home blocks any new window (windowless process).
rm -f "$USER_HOME"/.config/BraveSoftware/*/SingletonSocket \
  "$USER_HOME"/.config/BraveSoftware/*/SingletonCookie \
  "$USER_HOME"/.config/BraveSoftware/*/SingletonLock

Xvfb :1 -screen 0 1280x800x24 -ac +extension RANDR +render -noreset >/tmp/yourdaas/xvfb.log 2>&1 &
XVFB_PID=$!

ready=0
for _ in $(seq 1 100); do
  if xdpyinfo -display :1 >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Xvfb failed to start" >&2
  cat /tmp/yourdaas/xvfb.log >&2 || true
  exit 1
fi

if command -v dbus-launch >/dev/null 2>&1; then
  eval "$(dbus-launch --sh-syntax)"
fi

# Headless audio: PulseAudio with a virtual speaker (default sink) and a
# virtual microphone fed by the browser (default source). See docs/AUDIO.md.
# No system bus and no /run/user/<uid> here (unprivileged user), so the
# PulseAudio runtime lives under the service tmp dir.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/yourdaas/run}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
pulseaudio --exit-idle-time=-1 --disallow-exit >/tmp/yourdaas/pulseaudio.log 2>&1 &
for _ in $(seq 1 50); do
  if pactl info >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done
pactl load-module module-null-sink sink_name=yd_out sink_properties=device.description=YourDaaS_Speakers >/dev/null || true
pactl set-default-sink yd_out >/dev/null || true
pactl load-module module-null-sink sink_name=yd_mic sink_properties=device.description=YourDaaS_MicIn >/dev/null || true
pactl load-module module-remap-source master=yd_mic.monitor source_name=yd_mic_in source_properties=device.description=YourDaaS_Microphone >/dev/null || true
pactl set-default-source yd_mic_in >/dev/null || true

# Full XFCE session (wm + panel + desktop) on the persistent HOME.
xfce4-session >/tmp/yourdaas/xfce.log 2>&1 &

# Clipboard bridge. No -fork: with an explicit & the shell never waits on it
# (-fork sometimes fails at boot and wedges PID 1 in do_wait).
setsid autocutsel -selection CLIPBOARD >/dev/null 2>&1 < /dev/null &
setsid autocutsel -selection PRIMARY >/dev/null 2>&1 < /dev/null &

# Plank dock with 3 pinned apps (browser, files, terminal).
# Seed launchers in the persistent home; never overwrite the user's pins.
mkdir -p "$USER_HOME/.config/plank/dock1/launchers"
for app in brave-origin thunar xfce4-terminal; do
  item="$USER_HOME/.config/plank/dock1/launchers/$app.dockitem"
  if [[ ! -e "$item" ]]; then
    printf '[PlankDockItemPreferences]\nLauncher=file:///usr/share/applications/%s.desktop\n' "$app" > "$item"
  fi
done
if command -v dconf >/dev/null 2>&1; then
  # dconf straight to the file (synchronous, no bus needed).
  DOCK=/net/launchpad/plank/docks/dock1/
  dconf write ${DOCK}position "'bottom'" >/dev/null 2>&1 || true
  dconf write ${DOCK}alignment "'center'" >/dev/null 2>&1 || true
  dconf write ${DOCK}icon-size 40 >/dev/null 2>&1 || true
  dconf write ${DOCK}hide-mode "'none'" >/dev/null 2>&1 || true
fi
plank >/tmp/yourdaas/plank.log 2>&1 &

# Boot-time OS tuning (idempotent; applies to pre-existing home volumes too).
if command -v xfconf-query >/dev/null 2>&1; then
  # Compositor off: no transparency/shadows/animations taxing the VNC encode.
  for _ in $(seq 1 50); do
    xfconf-query -c xfwm4 -p /general/use_compositing >/dev/null 2>&1 && break
    sleep 0.2
  done
  xfconf-query -c xfwm4 -p /general/use_compositing -s false >/dev/null 2>&1 || true
fi
# Brave Origin as the web browser: exo preferred-apps entry plus
# x-scheme-handler/text-html defaults (merged, never clobbers the file).
mkdir -p "$USER_HOME/.config/xfce4"
printf 'WebBrowser=brave-origin\n' > "$USER_HOME/.config/xfce4/helpers.rc"
if command -v xdg-mime >/dev/null 2>&1; then
  xdg-mime default brave-origin.desktop x-scheme-handler/http x-scheme-handler/https text/html >/dev/null 2>&1 || true
fi

# Throughput-tuned for motion: tight poll + minimal defer (see docs/VIDEO.md).
x11vnc -display :1 -forever -shared -nopw -listen 127.0.0.1 -rfbport 5900 -xkb -ncache 0 \
  -deferupdate 5 -wait 5 -threads \
  >/tmp/yourdaas/x11vnc.log 2>&1 &

NOVNC_ROOT=/usr/share/novnc
websockify --heartbeat=30 --web="$NOVNC_ROOT" 0.0.0.0:6080 127.0.0.1:5900 \
  >/tmp/yourdaas/novnc.log 2>&1 &

python3 /usr/local/bin/yourdaas-file-api >/tmp/yourdaas/file-api.log 2>&1 &

AUDIO_PORT="${AUDIO_PORT:-7072}"
python3 /usr/local/bin/yourdaas-audio-ws >/tmp/yourdaas/audio-ws.log 2>&1 &

while kill -0 "$XVFB_PID" 2>/dev/null; do
  sleep 2
done
echo "Xvfb exited" >&2
exit 1
