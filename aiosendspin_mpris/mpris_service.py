"""Patched MPRIS service."""

from __future__ import annotations

import logging
from typing import Any, override

from dbus_next.aio.message_bus import MessageBus
from dbus_next.errors import InvalidAddressError
from mpris_api.adapter.IMprisAdapterPlayer import IMprisAdapterPlayer
from mpris_api.adapter.IMprisAdapterPlayLists import IMprisAdapterPlayLists
from mpris_api.adapter.IMprisAdapterRoot import IMprisAdapterRoot
from mpris_api.adapter.IMprisAdapterTrackList import IMprisAdapterTrackList
from mpris_api.interface.MprisInterfacePlayLists import MprisInterfacePlayLists
from mpris_api.model.MprisConstant import MprisConstant
from mpris_api.MprisService import MprisService

_LOGGER = logging.getLogger(__name__)


class PatchedMprisInterfacePlayLists(MprisInterfacePlayLists):
    """Patched MprisInterfacePlayLists to return lists instead of tuples for D-Bus STRUCT types."""

    @override
    def activePlaylist(self) -> list[Any]:  # pyright: ignore[reportExplicitAny, reportIncompatibleMethodOverride]
        """Return active playlist as a list.

        The upstream definition seems to be wrong since DBus requires a list, not tuple.
        """
        return []


class PatchedMprisService(MprisService):
    """Patched MprisService to handle InvalidAddressError gracefully."""

    def __init__(  # noqa: D107
        self,
        name: str,
        adapterRoot: IMprisAdapterRoot,  # noqa: N803
        adapterPlayer: IMprisAdapterPlayer,  # noqa: N803
        adapterTrackList: IMprisAdapterTrackList,  # noqa: N803
        adapterPlayLists: IMprisAdapterPlayLists,  # noqa: N803
    ) -> None:
        super().__init__(
            name=name,
            adapterRoot=adapterRoot,
            adapterPlayer=adapterPlayer,
            adapterTrackList=adapterTrackList,
            adapterPlayLists=adapterPlayLists,
        )
        self._interfacePlayLists: MprisInterfacePlayLists | None = PatchedMprisInterfacePlayLists(
            adapter=adapterPlayLists
        )

    @override
    async def _loop(self) -> None:
        try:
            self._messageBus = messageBus = await MessageBus().connect()  # noqa: N806  # pyright: ignore[reportUnannotatedClassAttribute]

            messageBus.export(MprisConstant.PATH, self._interfaceRoot)
            messageBus.export(MprisConstant.PATH, self._interfacePlayer)
            if self._interfaceTrackList:
                messageBus.export(MprisConstant.PATH, self._interfaceTrackList)
            if self._interfacePlayLists:
                messageBus.export(MprisConstant.PATH, self._interfacePlayLists)

            _ = await messageBus.request_name(self._name)

            await messageBus.wait_for_disconnect()

        except InvalidAddressError:
            _LOGGER.warning("MPRIS not available: DBus address error")
        finally:
            self._disconnect()
