FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    autocutsel \
    xclip \
    xfce4-session \
    xfwm4 \
    xfce4-panel \
    xfdesktop4 \
    xfce4-settings \
    xfce4-terminal \
    thunar \
    xdotool \
    x11-utils \
    novnc \
    websockify \
    python3 \
    ca-certificates \
    procps \
    bash \
    wget \
    curl \
    git \
    openssh-client \
    rsync \
    unzip \
    zip \
    iputils-ping \
    iproute2 \
    dnsutils \
    jq \
    tree \
    tmux \
    nano \
    plank \
    libglib2.0-bin \
    dconf-cli \
    dconf-gsettings-backend \
    dconf-service \
    adwaita-icon-theme \
    fonts-liberation \
    fonts-dejavu-core \
    dbus-x11 \
    xdg-utils \
    sudo \
    pulseaudio \
    pulseaudio-utils \
    ffmpeg \
    python3-websockets \
  && rm -rf /var/lib/apt/lists/* \
  && wget -q -O /usr/share/keyrings/brave-browser-archive-keyring.gpg \
    https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg \
  && wget -q -O /etc/apt/sources.list.d/brave-browser-release.sources \
    https://brave-browser-apt-release.s3.brave.com/brave-browser.sources \
  && apt-get update \
  && apt-get install -y --no-install-recommends brave-origin \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 1000 user \
  && useradd --uid 1000 --gid user --create-home --shell /bin/bash user \
  && echo "user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/user \
  && chmod 440 /etc/sudoers.d/user \
  && rm -f /usr/share/applications/brave-origin.desktop \
    /usr/share/applications/com.brave.Origin.desktop \
    /usr/share/applications/thunar.desktop \
    /usr/share/applications/xfce4-terminal.desktop \
    /usr/share/applications/xfce4-mail-reader.desktop \
  && (update-desktop-database /usr/share/applications || rm -f /usr/share/applications/mimeinfo.cache)

ENV DISPLAY=:1
ENV HOME=/home/user
# PulseAudio runtime lives under the service tmp dir (no /run/user/<uid> for
# an unprivileged user). As ENV (not just start.sh export) it also covers
# `docker exec` sessions, so every process finds the daemon.
ENV XDG_RUNTIME_DIR=/tmp/yourdaas/run
WORKDIR /home/user

COPY --chmod=755 start.sh /usr/local/bin/yourdaas-computer
COPY --chmod=755 file-api.py /usr/local/bin/yourdaas-file-api
COPY --chmod=755 audio-ws.py /usr/local/bin/yourdaas-audio-ws
COPY --chmod=644 viewer.html /usr/share/novnc/yourdaas.html
COPY --chmod=644 xfce/panel-default.xml /etc/xdg/xfce4/panel/default.xml
COPY --chmod=644 xfce/xfwm4.xml /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml
COPY --chmod=644 xfce/xsettings.xml /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml
COPY --chmod=644 xfce/brave-origin-helper.desktop /usr/share/xfce4/helpers/brave-origin.desktop
COPY --chmod=644 desktop-files/brave-origin.desktop /usr/share/applications/brave-origin.desktop
COPY --chmod=644 desktop-files/thunar.desktop /usr/share/applications/thunar.desktop
COPY --chmod=644 desktop-files/xfce4-terminal.desktop /usr/share/applications/xfce4-terminal.desktop
RUN sed -i 's/\r$//' /usr/local/bin/yourdaas-computer /usr/local/bin/yourdaas-file-api /usr/local/bin/yourdaas-audio-ws \
  && (update-desktop-database /usr/share/applications || rm -f /usr/share/applications/mimeinfo.cache)

EXPOSE 6080 5900 7071 7072
USER 1000:1000
CMD ["/usr/local/bin/yourdaas-computer"]
