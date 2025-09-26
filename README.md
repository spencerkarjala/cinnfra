# Bootstrap Flux and SOPS with Age

This guide provides the essential steps to bootstrap a local Kubernetes cluster with Flux and manage secrets using SOPS with Age.

## Prerequisites

- Kubernetes cluster (e.g., k3d, k3s)
- `kubectl` installed
- `sops` installed
- `age` installed

## Steps

1. **Create a Kubernetes Cluster** (if not already created):
   ```bash
   k3d cluster create mycluster
   ```

2. **Install Flux:**
   ```bash
   kubectl apply -f https://github.com/fluxcd/flux2/releases/latest/download/install.yaml
   ```

3. **Generate and Add Age Key for SOPS:**

   - Generate an Age key:
     ```bash
     age-keygen -o sops-age-key.txt
     ```

   - Extract the public key:
     ```bash
     cat sops-age-key.txt | grep "public key" | cut -d " " -f 4
     ```

   - Add the Age key to your Kubernetes cluster as a secret:
     ```bash
     kubectl create secret generic sops-age --namespace=flux-system --from-file=age.agekey=sops-age-key.txt
     ```

4. **Configure SOPS:**

   - Create a `.sops.yaml` configuration file:
     ```yaml
     creation_rules:
       - age: "your-age-public-key"
     ```

5. **Encrypt a Secret:**

   - Create a plaintext `secret.yaml` and encrypt it:
     ```bash
     sops --encrypt --output secret.enc.yaml secret.yaml
     ```

6. **Commit Encrypted Secret:**

   - Add and commit the encrypted secret and `.sops.yaml`:
     ```bash
     git add secret.enc.yaml .sops.yaml
     git commit -m "Add encrypted secret"
     git push
     ```

This concise guide should help you quickly set up Flux and SOPS with Age on a fresh cluster.
