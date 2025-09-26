# SOPS setup (Age)

- Requirements: sops and age-keygen installed on this machine.

- Generate and install a new Age key for SOPS (recommended):
  python tools/init-sops.py --generate

- Or import an existing private key (you will be prompted to paste the line starting with AGE-SECRET-KEY-):
  python tools/init-sops.py

The script writes keys to ${XDG_CONFIG_HOME:-$HOME/.config}/sops/age/keys.txt and prints your Age public key (age1...). Use that public key in your .sops.yaml creation_rules.

