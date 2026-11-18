# Docker Hub description (paste into the repository "Overview"; manual until automated)

**homematic-exporter**: Prometheus exporter for Homematic IP heating (rooms, valves, humidity, battery/accumulator status).

- Source: https://github.com/zbitmanis/homematic_exporter
- Tags: `X.Y.Z`, `X.Y`, `latest` (releases); `v<next>-pr.<n>.<sha>` and `pr-<n>` (pull requests, short-lived)
- Platforms: `linux/amd64`, `linux/arm64`; runs rootless under Podman
- Configuration: environment variables (see the repository docs); the Homematic IP token is supplied as a secret, never baked into the image

**Licences:** the exporter's own code is MIT. The image bundles the `homematicip` library (GPL-3.0-or-later; https://github.com/hahn-th/homematicip-rest-api), so the combined image is distributed under GPL-3.0-or-later terms for that component. Licence texts and notices are in `/licenses/` inside the image. Other Python dependencies keep their own permissive licences (list: the CycloneDX SBOM attached to each release).
