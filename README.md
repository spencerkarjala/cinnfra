# Local k3s Flux + SOPS bootstrap guide

This README documents steps to bootstrap a local k3s cluster, configure Flux for GitOps, and manage secrets with SOPS.

Prerequisites
- Linux/macOS with Docker or other container runtime
- kubectl
- Flux CLI (optional; bootstrap can be done via manifests)
- sops
- git
- k3d or kind or a local k3s setup
- Optional: helm

Install required tooling
- k3d:
  - curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
- Flux:
  - flux installation is optional for bootstrapping; you can apply install manifests manually
- sops:
  - macOS: brew install sops
  - Ubuntu/Debian: sudo apt-get install -y sops
- kubectl: follow standard install instructions
- git: ensure git is installed

Cluster creation (local)
Option A: using k3d
- k3d cluster create local --agents 2
- export KUBECONFIG=$(k3d kubeconfig write local)
- kubectl get nodes

Option B: direct k3s install
- Refer to official k3s install instructions
- Note: This guide uses k3d for local development

Bootstrap Flux to Git repo
- The repo is the current repository; Flux CLI is not installed on this machine, so bootstrap will be performed using manifests rather than the flux bootstrap command.
- Ensure a path like clusters/local exists at the repo root for Flux to manage.
- Manually install Flux controllers into the cluster by applying the official Flux install manifest (no CLI required):
  - kubectl apply -f https://github.com/fluxcd/flux2/releases/latest/download/install.yaml
- Create or apply a GitRepository and Kustomization resources later to connect to the repo (see sections below).
- Verify Flux controllers are running:
  - kubectl get pods -n flux-system

- Note: When you install the Flux CLI later, you can bootstrap with:
  - flux bootstrap github ...

Prepare secrets encryption with SOPS
- Generate a GPG key
  - gpg --full-generate-key
  - gpg --list-secret-keys --keyid-format=long
  - Note the KEY_ID, e.g., 0123ABCD
- Export keys (for backup)
  - gpg --armor --export 0123ABCD > pubkey.asc
  - gpg --armor --export-secret-keys 0123ABCD > privkey.asc
- Create sops config
  - Create a .sops.yaml at the repo root or at the path where secrets are stored with:
creation_rules:
  - pgp: "0123ABCD"
- Create a plaintext secret.yaml
  - versioned under git, then encrypt:
  - sops --encrypt --output secret.enc.yaml secret.yaml
- Commit encrypted secret and sops.yaml
  - git add secret.enc.yaml .sops.yaml
  - git commit -m "Encrypt secret with sops"
  - git push

- In a Flux-managed workflow, decrypt for apply as needed:
  - sops --decrypt secret.enc.yaml > secret.yaml

Integrate encryption with Flux
- Add a SealedSecret or SOPS-Decrypter sidecar if you want in-cluster decryption
- Alternatively, decrypt on CI and apply plain manifests using a CI job that has decryption keys

Verify and operate
- Flux components:
  - kubectl get pods -n flux-system
- Cluster health:
  - kubectl get pods -A
- Secrets rotation:
  - Update plaintext, re-encrypt, commit, and push; Flux will pick changes

Security considerations
- Store GPG keys securely; back up
- Do not commit unencrypted secrets
- Rotate keys periodically

Rollback and recovery
- Restore from backed up private key
- Re-encrypt secrets as needed

Appendix
- Useful commands
- References
  - Flux: https://fluxcd.io
  - SOPS: https://github.com/mozilla/sops

This README should help document progress as you go.
