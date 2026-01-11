"""SendspinMpris - MPRIS integration for aiosendspin applications."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from .adapter import MPRIS_AVAILABLE, MprisState, SendspinMprisAdapter

if TYPE_CHECKING:
    from aiosendspin.client import SendspinClient
    from aiosendspin.models.core import GroupUpdateServerPayload, ServerStatePayload
    from aiosendspin.models.types import MediaCommand, PlaybackStateType

_LOGGER = logging.getLogger(__name__)

if MPRIS_AVAILABLE:
    from mpris_server.events import EventAdapter
    from mpris_server.interfaces.interface import MprisInterface
    from mpris_server.server import Server


class SendspinMpris:
    """MPRIS integration for aiosendspin applications.

    Provides desktop media control integration on Linux systems, using MPRIS.

    When started, this class automatically registers listeners on the provided
    SendspinClient to update MPRIS state when metadata, playback state, or volume
    changes are received from the server.

    Example usage:
        ```python
        from aiosendspin import SendspinClient
        from aiosendspin_mpris import SendspinMpris, MPRIS_AVAILABLE

        client = SendspinClient(...)
        mpris = SendspinMpris(client)
        mpris.start()  # Starts MPRIS and attaches listeners to client

        # Later
        mpris.stop()
        ```
    """

    _client: SendspinClient
    _name: str
    _desktop_entry: str | None
    _loop: asyncio.AbstractEventLoop | None
    _state: MprisState
    _adapter: SendspinMprisAdapter | None
    _server: Server[SendspinMprisAdapter, EventAdapter, MprisInterface[SendspinMprisAdapter]] | None
    _event_adapter: EventAdapter | None
    _thread: threading.Thread | None
    _running: bool
    _listener_removers: list[Callable[[], None]]

    def __init__(
        self, client: SendspinClient, name: str = "Sendspin", desktop_entry: str | None = None
    ) -> None:
        """Initialize the MPRIS interface.

        Args:
            client: SendspinClient instance for sending commands and receiving state updates.
            name: Application name shown in MPRIS (default: "Sendspin").
            desktop_entry: The .desktop file name, with the '.desktop' extension stripped, or None.

        """
        self._client = client
        self._name = name
        self._desktop_entry = desktop_entry
        self._loop = None

        self._state = MprisState()

        self._adapter = None
        self._server = None
        self._event_adapter = None
        self._thread = None
        self._running = False
        self._listener_removers = []

    def start(self) -> None:
        """Start the MPRIS D-Bus service and attach listeners to the client.

        This creates a background thread that runs the MPRIS server and registers
        listeners on the client to automatically update MPRIS state when metadata,
        playback state, or volume changes are received from the server.

        If MPRIS is not available (not on Linux or mpris_server not installed),
        this method does nothing.
        """
        if not MPRIS_AVAILABLE:
            _LOGGER.debug("MPRIS not available: mpris_server package not installed or not on Linux")
            return

        if self._running:
            _LOGGER.debug("MPRIS interface already running")
            return

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError as err:
            raise RuntimeError("MPRIS must be started from within a running event loop") from err

        self._adapter = SendspinMprisAdapter(
            self._client, self._loop, self._state, desktop_entry=self._desktop_entry
        )

        self._server = Server(name=self._name, adapter=self._adapter)  # pyright: ignore [reportPossiblyUnboundVariable]

        self._event_adapter = EventAdapter(  # pyright: ignore [reportPossiblyUnboundVariable]
            root=self._server.root,
            player=self._server.player,
            playlists=self._server.playlists,
            tracklist=self._server.tracklist,
        )

        # Copy server instance to local variable for thread, since self._server may be None
        server = self._server

        def run_loop() -> None:
            try:
                server.loop()
            except Exception:
                _LOGGER.exception("MPRIS server loop error")

        self._thread = threading.Thread(target=run_loop, daemon=True, name="mpris-server")
        self._thread.start()
        self._running = True

        self._attach_client_listeners()

        _LOGGER.info("MPRIS interface started")

    def stop(self) -> None:
        """Stop the MPRIS D-Bus service and remove client listeners."""
        if not self._running:
            return

        self._running = False
        self._event_adapter = None

        for remover in self._listener_removers:
            try:
                remover()
            except Exception:
                _LOGGER.debug("Error removing listener", exc_info=True)
        self._listener_removers.clear()

        if self._server is not None:
            try:
                self._server.quit()
            except Exception:
                _LOGGER.debug("Error stopping MPRIS server", exc_info=True)
            self._server = None

        if self._thread is not None:
            _LOGGER.debug("Waiting for MPRIS server thread to exit")
            self._thread.join(timeout=1)
            self._thread = None

        _LOGGER.info("MPRIS interface stopped")

    def _attach_client_listeners(self) -> None:
        """Attach event listeners to the client for MPRIS state updates."""
        self._listener_removers.append(self._client.add_metadata_listener(self._on_metadata_update))
        self._listener_removers.append(
            self._client.add_group_update_listener(self._on_group_update)
        )
        self._listener_removers.append(
            self._client.add_controller_state_listener(self._on_controller_state)
        )

        _LOGGER.debug("Attached MPRIS listeners to SendspinClient")

    def _on_metadata_update(self, payload: ServerStatePayload) -> None:
        """Handle metadata updates from the client."""
        from aiosendspin.models.types import UndefinedField

        metadata = payload.metadata
        if metadata is None:
            return

        # Extract metadata fields
        title = (
            metadata.title if not isinstance(metadata.title, UndefinedField) else self._state.title
        )
        artist = (
            metadata.artist
            if not isinstance(metadata.artist, UndefinedField)
            else self._state.artist
        )
        album = (
            metadata.album if not isinstance(metadata.album, UndefinedField) else self._state.album
        )

        # Extract duration from progress if available
        duration_ms = self._state.duration_ms
        progress_ms = self._state.progress_ms

        if not isinstance(metadata.progress, UndefinedField) and metadata.progress is not None:
            duration_ms = metadata.progress.track_duration
            progress_ms = metadata.progress.track_progress

        self.set_metadata(title=title, artist=artist, album=album, duration_ms=duration_ms)

        if progress_ms is not None:
            self.set_progress(progress_ms)

    def _on_group_update(self, payload: GroupUpdateServerPayload) -> None:
        """Handle group update (playback state) from the client."""
        if payload.playback_state is not None:
            self.set_playback_state(payload.playback_state)

    def _on_controller_state(self, payload: ServerStatePayload) -> None:
        """Handle controller state updates from the client."""
        controller = payload.controller
        if controller is None:
            return
        self.set_supported_commands(set(controller.supported_commands))
        self.set_volume(controller.volume, muted=controller.muted)

    def set_metadata(
        self,
        title: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        """Update track metadata."""
        self._state.title = title
        self._state.artist = artist
        self._state.album = album
        self._state.duration_ms = duration_ms

        if self._event_adapter is None:
            _LOGGER.warning("MPRIS event adapter not initialized; cannot emit metadata change")
            return

        try:
            self._event_adapter.on_title()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS metadata change", exc_info=True)

    def set_progress(self, progress_ms: int | None) -> None:
        """Update track progress."""
        self._state.progress_ms = progress_ms

    def set_playback_state(self, state: PlaybackStateType) -> None:
        """Update playback state."""
        self._state.playback_state = state

        if self._event_adapter is None:
            _LOGGER.warning(
                "MPRIS event adapter not initialized; cannot emit playback state change"
            )
            return

        try:
            self._event_adapter.on_playpause()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS playback state change", exc_info=True)

    def set_volume(self, volume: int, *, muted: bool = False) -> None:
        """Update group volume.

        Args:
            volume: Volume level (0-100).
            muted: Whether the volume is muted.

        """
        self._state.volume = volume
        self._state.muted = muted

        if self._event_adapter is None:
            _LOGGER.warning("MPRIS event adapter not initialized; cannot emit volume change")
            return

        try:
            self._event_adapter.on_volume()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS volume change", exc_info=True)

    def set_supported_commands(self, commands: set[MediaCommand]) -> None:
        """Update supported media commands.

        This affects which controls are shown as available in MPRIS clients.
        """
        self._state.supported_commands = commands

        if self._event_adapter is None:
            _LOGGER.warning("MPRIS event adapter not initialized; cannot emit options change")
            return

        try:
            self._event_adapter.on_options()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS options change", exc_info=True)
