```bash
helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
helm repo update

# see available versions
helm search repo external-dns/external-dns --versions

# upgrade tailscale-operator
CHART_VERSION=""; : "${CHART_VERSION:?Set CHART_VERSION at the beginning of this command.}"; helm upgrade --install external-dns external-dns/external-dns --version "$CHART_VERSION" -n cloudflare --create-namespace -f 'helm/external-dns/values.yaml'
```
