# 0) Create and export an AGE key for SOPS
mkdir -p ~/.config/sops
age-keygen -o ~/.config/sops/age-key.txt
export SOPS_AGE_KEY_FILE=~/.config/sops/age-key.txt

# 1) Initialize repo
cd repo
git init

# 2) Configure SOPS to auto-encrypt the Tailscale secret
cat > .sops.yaml <<'YAML'
creation_rules:
  - path_regex: kubernetes/secrets/.*\.ya?ml$
    age: [publickey:REPLACE_WITH_YOUR_AGE_PUBLIC_KEY]
YAML
# Get your AGE public key:
#   age-keygen -y ~/.config/sops/age-key.txt

# 3) Write the Kubernetes Secret manifest (will be encrypted with SOPS)
mkdir -p kubernetes/secrets
cat > kubernetes/secrets/tailscale-operator.yaml <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: operator-oauth
  namespace: tailscale
type: Opaque
stringData:
  client_id: tsc_XXXXXXXXXXXXXXXX      # from Tailscale OAuth client
  client_secret: tsc_secret_XXXXXXXX   # from Tailscale OAuth client
YAML

# 4) Encrypt it
sops -e -i kubernetes/secrets/tailscale-operator.yaml

# 5) Commit everything
git add .
git commit -m Bootstrap Tailscale operator chart + SOPS secret

