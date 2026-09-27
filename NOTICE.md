# Notice

## What this is

**Kestrel** is a derivative work of [Frigate NVR](https://frigate.video), maintained
by LocknAlert Pty Ltd. It is **not** an official Frigate product, and it is not
sponsored, endorsed by, or affiliated with Frigate, Inc.

Kestrel adds an intrusion-alarm engine on top of Frigate's detection pipeline —
arm modes, entry/exit delays, zone bypass, central-station reporting over SIA
DC-09 and Contact ID — plus ParkPow license-plate forwarding and TensorRT
inference on the x86 image.

## Upstream licence

The original software is Copyright (c) Frigate, Inc. (Frigate™) and is licensed
under the MIT License. That licence and copyright notice are retained in
[`LICENSE`](LICENSE), as the MIT terms require, and they cover both the original
code and the modifications in this repository.

## Trademarks

"Frigate", "Frigate NVR", "Frigate+" and the Frigate logo are trademarks of
Frigate, Inc. They are not licensed under the MIT License. See
[`TRADEMARK.md`](TRADEMARK.md) for the upstream policy.

This fork accordingly:

- is named **Kestrel**, not Frigate, and is not distributed under the Frigate name;
- ships its own logo and icon set (see `scripts/generate_brand_assets.py`) and
  does not redistribute the Frigate logo;
- refers to Frigate only to state truthfully what this software is derived from,
  which the upstream policy permits as referential use.

**"Frigate+" is deliberately left unrenamed throughout the UI and docs.** It is a
paid service operated by Frigate, Inc. that this software integrates with, so
naming it is both accurate and necessary — calling it anything else would be
wrong.

Some internal identifiers still use the name `frigate` — the Python package, the
`frigate.db` filename, the default MQTT topic prefix and the configuration keys.
These are not product branding, and renaming them would break every existing
deployment's configuration, Home Assistant integration and MQTT consumer for no
user-visible benefit.

## Questions

Trademark questions about the upstream marks go to help@frigate.video, per
`TRADEMARK.md` section 6. Questions about this fork go to LocknAlert Pty Ltd.
