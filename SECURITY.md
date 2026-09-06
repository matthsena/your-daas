# Security Policy

## Current posture (MVP)

**There is no authentication.** The VNC server, noVNC page, and file API are
safe to run only because compose binds every port to `127.0.0.1`. Never
publish these ports to a network interface, and never run the base compose
file on a shared host.

Additional local-only sharp edges:

- The desktop user has passwordless `sudo` (MVP convenience only).
- The file API has no auth and must stay on loopback.

## Before exposing anything

- Put Cloudflare Zero Trust Access (or equivalent) in front — see `deploy/`.
- Remove passwordless sudo from the image.
- Add auth to the file API or bind it to the internal Docker network only.

## Reporting a vulnerability

Open a GitHub Security Advisory on this repo (preferred) or email the
maintainer. Please do not open a public issue for unpatched vulnerabilities.
Include steps to reproduce and the affected commit or image tag.
