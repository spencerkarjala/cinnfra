```bash
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update

# see available versions
helm search repo tailscale/tailscale-operator --versions

# upgrade tailscale-operator
CHART_VERSION=""; : "${CHART_VERSION:?Set CHART_VERSION at the beginning of this command.}"; helm upgrade --install tailscale-operator tailscale/tailscale-operator --version "$CHART_VERSION" -n tailscale --create-namespace
```
