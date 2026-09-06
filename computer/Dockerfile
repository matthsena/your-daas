FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    autocutsel \
    xfce4-session \
    xfwm4 \
    xfce4-panel \
    xfdesktop4 \
    xfce4-settings \
    xfce4-terminal \
    thunar \
    mousepad \
    xdotool \
    x11-utils \
    imagemagick \
    novnc \
    websockify \
    python3 \
    ca-certificates \
    procps \
    bash \
    wget \
    papirus-icon-theme \
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
  && rm -rf /var/lib/apt/lists/* \
  && apt-get update \
  && wget -q -O /tmp/google-chrome.deb \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
  && apt-get install -y --no-install-recommends /tmp/google-chrome.deb \
  && rm -f /tmp/google-chrome.deb \
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 1000 user \
  && useradd --uid 1000 --gid user --create-home --shell /bin/bash user \
  && echo "user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/user \
  && chmod 440 /etc/sudoers.d/user \
  && rm -f /usr/share/applications/google-chrome.desktop \
    /usr/share/applications/com.google.Chrome.desktop \
    /usr/share/applications/thunar.desktop \
    /usr/share/applications/xfce4-terminal.desktop \
  && (update-desktop-database /usr/share/applications || rm -f /usr/share/applications/mimeinfo.cache)

ENV DISPLAY=:1
ENV HOME=/home/user
WORKDIR /home/user

COPY --chmod=755 start.sh /usr/local/bin/yourdaas-computer
COPY --chmod=755 file-api.py /usr/local/bin/yourdaas-file-api
COPY --chmod=644 viewer.html /usr/share/novnc/yourdaas.html
COPY --chmod=644 xfce/panel-default.xml /etc/xdg/xfce4/panel/default.xml
COPY --chmod=644 xfce/xfwm4.xml /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml
COPY --chmod=644 xfce/xsettings.xml /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml
COPY --chmod=644 desktop-files/google-chrome.desktop /usr/share/applications/google-chrome.desktop
COPY --chmod=644 desktop-files/thunar.desktop /usr/share/applications/thunar.desktop
COPY --chmod=644 desktop-files/xfce4-terminal.desktop /usr/share/applications/xfce4-terminal.desktop
RUN sed -i 's/\r$//' /usr/local/bin/yourdaas-computer /usr/local/bin/yourdaas-file-api \
  && (update-desktop-database /usr/share/applications || rm -f /usr/share/applications/mimeinfo.cache)

EXPOSE 6080 5900 7071
USER 1000:1000
CMD ["/usr/local/bin/yourdaas-computer"]
