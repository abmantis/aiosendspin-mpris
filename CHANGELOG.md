# CHANGELOG


## v2.1.1 (2026-01-18)

### Bug Fixes

- Override MprisService to properly handle dbus errors
  ([`43b238c`](https://github.com/abmantis/aiosendspin-mpris/commit/43b238cae2539255f5fc9c559e763b7895bcc414))


## v2.1.0 (2026-01-12)


## v2.0.1 (2026-01-11)

### Features

- Migrate MPRIS implementation from mpris_server to mpris-api
  ([`d697bd9`](https://github.com/abmantis/aiosendspin-mpris/commit/d697bd9af86a548d9166d15ed8c6a7c2f16b5c27))

mpris_server depends on pygobject which in turn depends on pycairo. mpris-api has simpler
  dependencies.


## v2.0.0 (2026-01-11)

### Bug Fixes

- Move mpris_server import to conditional imports
  ([`c0bd490`](https://github.com/abmantis/aiosendspin-mpris/commit/c0bd490e90857ef4fc72738809c6113af9297075))

### Chores

- Fix basedpyright
  ([`ff4fc0a`](https://github.com/abmantis/aiosendspin-mpris/commit/ff4fc0ab1d21a9af0286c95728ccf6cbcc3bd944))

- Fix CI missing deps
  ([`1ecdf52`](https://github.com/abmantis/aiosendspin-mpris/commit/1ecdf52eead95611f6f695f8696fd47cfe540a46))

- Fix CI missing deps v2
  ([`33b2a9e`](https://github.com/abmantis/aiosendspin-mpris/commit/33b2a9e26cdabb3261ffbcbd758c94d70da0bbb2))

### Features

- Automatically subscribe to client
  ([`9f23e6a`](https://github.com/abmantis/aiosendspin-mpris/commit/9f23e6a8c85ebce932c8a72e380c527cc4ba7d4c))


## v1.0.0 (2025-12-31)

### Chores

- Add README and LICENSE
  ([`6c86ed6`](https://github.com/abmantis/aiosendspin-mpris/commit/6c86ed6206f9653f8860bc40b04e7970b9232316))

### Features

- Initial release
  ([`3d66130`](https://github.com/abmantis/aiosendspin-mpris/commit/3d661307833a7df05d896d0dabb1ff60360ee1ce))
