# SOPS setup

- If you don't have an existing sops key (fresh install), generate and install a new `age` key for `sops`:

```bash
python tools/init-sops.py --generate
```

- Otherwise, run the following and paste your key (including `AGE-SECRET-KEY-`):

```bash
python tools/init-sops.py
```

Once you're done, you can retrieve your key from `$XDG_CONFIG_HOME/.config/sops/age/keys.txt`. If you generated a new key, update `.sops.yaml` with the new public key.

