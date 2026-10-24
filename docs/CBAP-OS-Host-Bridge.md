# CBAP OS VM → host desktop: safe CBAP test

**Status**: tested with QEMU/KVM, 4G guest cap, 2026-10-24
**Protocol**: CBAP-U over TCP, same Kernel lease/audit path
**Host devices**: `host://desktop`, `host://fs`, `host://display`,
`host://input/mouse`, `host://input/keyboard`
**Host action**: create `~/Desktop/CBAP-Host-Test/hello-from-vm.txt`

---

## Architecture

```text
CBAP OS (guest, 10.0.2.15)
  CBAP Control Center / CBAPClient
        │ CBAP-U over TCP
        ▼
QEMU user network 10.0.2.2:18765
        ▼
host KernelServer (127.0.0.1 only)
        ▼
HostDesktopDriver / HostDisplayDriver / HostInputDriver (CBAP-D)
        ▼
~/Desktop/CBAP-Host-Test/  (filesystem + screenshots)
X11/XWayland input          (mouse/keyboard, opt-in only)
```

The VM does **not** get a shell on the host. It gets CBAP device IDs with a
small, explicit action surface.

## Host side

```bash
# host repo
python3 tools/cbap_host_bridge.py \
  --root "$HOME/Desktop/CBAP-Host-Test" \
  --socket /tmp/cbap-host-test/cbap.sock \
  --tcp-port 18765 \
  --token cbap-host-test-2026
```

TCP binds `127.0.0.1` only. The token is a **test-only shared token** injected
into the CBAP OS ISO; do not reuse it outside this local test.

## Device IDs

Kernel welcome lists:

```text
host://desktop         filesystem compatibility API
host://fs              allowlisted filesystem
host://display         read-only Wayland screenshot into allowlist
host://input/mouse     opt-in X11/XWayland pointer
host://input/keyboard  opt-in X11/XWayland keyboard
```

Input devices are **closed by default**. Starting the bridge with
`--enable-input` is an explicit host decision; without it every input action
returns `E_SAFETY`.

The input backend is X11/XWayland (`xdotool`). It is not a native Wayland
input injection service; a native Wayland portal/uinput backend would be a
separate, higher-risk feature.

## Guest side

The ISO has:

```text
CBAP Control Center   /usr/local/bin/cbap-control
host config           /etc/cbap-os/host-test.json
CBAP v1.4.0 + 3.13    /opt/cbap-os/...
```

The Control Center calls the normal CBAP sequence:

```text
hello
open host://desktop mode=exclusive
lease
write {"op":"write_file", "args":{"path":"from-control-center.txt", ...}}
stat
release
```

The GUI is convenient; the same protocol was also exercised from the guest
terminal with `CBAPClient`.

## Observed test

Host Desktop after the guest test:

```text
~/Desktop/CBAP-Host-Test/hello-from-vm.txt
```

Content:

```text
Hello from CBAP OS VM
This file was created through CBAP, not a shell.
```

The CBAP result contained:

```text
ok=true
path=/home/.../Desktop/CBAP-Host-Test/hello-from-vm.txt
bytes=71
sha256=d4f41106f04fc7fab04aa9542628ee9e888614ade91a9eac7bfee5b8b228cd22
```

## Safety invariants

```text
TCP only on 127.0.0.1
token required
5 device IDs, each with its own lease/safety state
filesystem actions: write_file / list / stat / ping
display actions: screenshot / stat (read-only)
input actions: gated by --enable-input; default E_SAFETY
input backend: X11/XWayland only; native Wayland not claimed
write_file only under ~/Desktop/CBAP-Host-Test
absolute paths rejected
.. escapes rejected
symlinked components rejected
max 64 KiB
no executable creation
no subprocess / no shell
atomic temp file + fsync + os.replace
CBAP lease required before write
CBAP audit chain at /tmp/cbap-host-test/audit.jsonl
```

The driver's `estop` sets a latched safe flag; subsequent host actions return
`E_SAFETY`.

## What this is not

```text
not remote administration
not a general host shell
not a production host agent
not TLS/mTLS protected (test bridge is loopback + shared token)
not independent hardware attestation
```

For production, put the bridge behind a real authenticated transport, use a
per-test secret, and add an explicit operator approval policy. The VM must not
be given a broader device surface just because this test worked.

## Files

```text
drivers/host_desktop/driver.py       host allowlisted driver
tools/cbap_host_bridge.py            Kernel + TCP bridge
tools/test_host_desktop.py           host-driver safety tests
docs/CBAP-OS-Host-Bridge.md          this document
```

DSH/CBAP OS side:

```text
cbap-os/bin/cbap-control
cbap-os/etc/host-test.json
cbap-os/cbap-control.desktop
```

## P0–P6 parity

See [`DEVICE-PARITY.md`](DEVICE-PARITY.md) for the device contract,
default-deny policy, per-device quotas, trust labels, safe-state evidence and
native-Wayland portal backend.
