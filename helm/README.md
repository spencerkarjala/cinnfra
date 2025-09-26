helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update
helm upgrade --install tailscale-operator ./charts/tailscale-operator -n tailscale --create-namespace -f tailscale/values.yaml

