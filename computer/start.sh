#!/usr/bin/env bash
# Computer XFCE: sessão completa, sem apps abertos no boot (tudo pela dock).
set -uo pipefail
export DISPLAY="${DISPLAY:-:1}"
export HOME="${HOME:-/home/rakazo}"
AGENT_HOME="$HOME"
mkdir -p "$AGENT_HOME" /tmp/rakazo /tmp/.X11-unix
cd "$AGENT_HOME"

rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# Chrome trava o perfil (Singleton*) se o container caiu com ele aberto; o lock
# stale no home persistente impede qualquer janela nova (processo sem janela).
rm -f "$AGENT_HOME/.config/google-chrome/SingletonSocket" \
  "$AGENT_HOME/.config/google-chrome/SingletonCookie" \
  "$AGENT_HOME/.config/google-chrome/SingletonLock"

Xvfb :1 -screen 0 1280x800x24 -ac +extension RANDR +render -noreset >/tmp/rakazo/xvfb.log 2>&1 &
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
  cat /tmp/rakazo/xvfb.log >&2 || true
  exit 1
fi

if command -v dbus-launch >/dev/null 2>&1; then
  eval "$(dbus-launch --sh-syntax)"
fi

# Sessão XFCE completa (wm + painel + desktop) no HOME persistente.
xfce4-session >/tmp/rakazo/xfce.log 2>&1 &

# Ponte de clipboard (igual ao MVP). Sem -fork: com & explícito o shell nunca
# espera por ele (o -fork falha às vezes no boot e trava o PID 1 em do_wait).
setsid autocutsel -selection CLIPBOARD >/dev/null 2>&1 < /dev/null &
setsid autocutsel -selection PRIMARY >/dev/null 2>&1 < /dev/null &

# Dock plank com os 3 apps pinados (browser, arquivos, terminal).
# Lançadores iniciais no home persistente; não sobrescreve os pins do usuário.
mkdir -p "$AGENT_HOME/.config/plank/dock1/launchers"
for app in google-chrome thunar xfce4-terminal; do
  item="$AGENT_HOME/.config/plank/dock1/launchers/$app.dockitem"
  if [[ ! -e "$item" ]]; then
    printf '[PlankDockItemPreferences]\nLauncher=file:///usr/share/applications/%s.desktop\n' "$app" > "$item"
  fi
done
if command -v dconf >/dev/null 2>&1; then
  # dconf direto no arquivo (síncrono, sem depender do bus).
  DOCK=/net/launchpad/plank/docks/dock1/
  dconf write ${DOCK}position "'bottom'" >/dev/null 2>&1 || true
  dconf write ${DOCK}alignment "'center'" >/dev/null 2>&1 || true
  dconf write ${DOCK}icon-size 40 >/dev/null 2>&1 || true
  dconf write ${DOCK}hide-mode "'none'" >/dev/null 2>&1 || true
fi
plank >/tmp/rakazo/plank.log 2>&1 &

x11vnc -display :1 -forever -shared -nopw -listen 127.0.0.1 -rfbport 5900 -xkb -ncache 0 \
  >/tmp/rakazo/x11vnc.log 2>&1 &

NOVNC_ROOT=/usr/share/novnc
websockify --heartbeat=30 --web="$NOVNC_ROOT" 0.0.0.0:6080 127.0.0.1:5900 \
  >/tmp/rakazo/novnc.log 2>&1 &

python3 /usr/local/bin/rakazo-file-api >/tmp/rakazo/file-api.log 2>&1 &

while kill -0 "$XVFB_PID" 2>/dev/null; do
  sleep 2
done
echo "Xvfb exited" >&2
exit 1
