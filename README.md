# aiosendspin-mpris

MPRIS integration for [aiosendspin](https://github.com/Sendspin-Protocol/aiosendspin) applications.

This package provides MPRIS (Media Player Remote Interfacing Specification) support, allowing desktop environments on Linux to display playback information and control Sendspin playback through standard media controls.

## Installation

```bash
pip install aiosendspin-mpris
```

The library depends on aiosendspin-mpris when installing on Linux. Without it (on other operating systems), the library gracefully degrades: MPRIS features are disabled, and methods like `set_metadata()`, `set_playback_state()`, etc. become no-ops that log warnings.



## License

Apache-2.0
