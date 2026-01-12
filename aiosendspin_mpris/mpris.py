"""SendspinMpris - MPRIS integration for aiosendspin applications."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, final, override

from .adapter import (
    MPRIS_AVAILABLE,
    MprisState,
    SendspinMprisAdapterPlayer,
    SendspinMprisAdapterRoot,
    SendspinMprisAdapterTrackList,
)

if TYPE_CHECKING:
    from aiosendspin.client import SendspinClient
    from aiosendspin.models.core import GroupUpdateServerPayload, ServerStatePayload
    from aiosendspin.models.types import MediaCommand, PlaybackStateType
    from mpris_api.MprisService import MprisService
    from mpris_api.MprisUpdateNotifier import MprisUpdateNotifier

_LOGGER = logging.getLogger(__name__)

if MPRIS_AVAILABLE:
    from mpris_api.MprisService import MprisService


@final
class _MprisErrorFilter(logging.Filter):
    """Filter to suppress expected MPRIS interface errors.

    Some MPRIS clients query for optional interfaces (like Playlists) which is not
    properly supported by the mpris-api lib. This filter suppresses the
    resulting D-Bus errors to avoid cluttering the output.
    """

    _SUPPRESSED_INTERFACES = ("org.mpris.MediaPlayer2.Playlists",)

    @override
    def filter(self, record: logging.LogRecord) -> bool:
        """Return False to suppress the log record, True to allow it."""
        if record.levelno != logging.ERROR:
            return True

        msg = record.getMessage()
        if "could not find an interface" not in msg:
            return True

        return not any(iface in msg for iface in self._SUPPRESSED_INTERFACES)


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
    _adapter_root: SendspinMprisAdapterRoot | None
    _adapter_player: SendspinMprisAdapterPlayer | None
    _adapter_tracklist: SendspinMprisAdapterTrackList | None
    _service: MprisService | None
    _update_notifier: MprisUpdateNotifier | None
    _running: bool
    _listener_removers: list[Callable[[], None]]
    _error_filter: _MprisErrorFilter | None

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

        self._adapter_root = None
        self._adapter_player = None
        self._adapter_tracklist = None
        self._service = None
        self._update_notifier = None
        self._running = False
        self._listener_removers = []
        self._error_filter = None

    def start(self) -> None:
        """Start the MPRIS D-Bus service and attach listeners to the client.

        This creates a background thread that runs the MPRIS server and registers
        listeners on the client to automatically update MPRIS state when metadata,
        playback state, or volume changes are received from the server.

        If MPRIS is not available (not on Linux or mpris_api not installed),
        this method does nothing.
        """
        if not MPRIS_AVAILABLE:
            _LOGGER.debug("MPRIS not available: mpris_api package not installed or not on Linux")
            return

        if self._running:
            _LOGGER.debug("MPRIS interface already running")
            return

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError as err:
            raise RuntimeError("MPRIS must be started from within a running event loop") from err

        # Add filter to suppress expected D-Bus errors for unimplemented interfaces
        self._error_filter = _MprisErrorFilter()
        logging.getLogger().addFilter(self._error_filter)

        self._adapter_root = SendspinMprisAdapterRoot(
            identity=self._name, desktop_entry=self._desktop_entry
        )
        self._adapter_player = SendspinMprisAdapterPlayer(self._client, self._loop, self._state)
        self._adapter_tracklist = SendspinMprisAdapterTrackList()

        self._service = MprisService(
            name=self._name,
            adapterRoot=self._adapter_root,
            adapterPlayer=self._adapter_player,
            adapterTrackList=self._adapter_tracklist,
        )
        self._service.start()
        self._update_notifier = self._service.updateNotifier

        self._running = True

        self._attach_client_listeners()

        _LOGGER.info("MPRIS interface started")

    def stop(self) -> None:
        """Stop the MPRIS D-Bus service and remove client listeners."""
        if not self._running:
            return

        self._running = False
        self._update_notifier = None

        for remover in self._listener_removers:
            try:
                remover()
            except Exception:
                _LOGGER.debug("Error removing listener", exc_info=True)
        self._listener_removers.clear()

        if self._service is not None:
            try:
                self._service.stop()
            except Exception:
                _LOGGER.debug("Error stopping MPRIS service", exc_info=True)
            self._service = None

        self._adapter_root = None
        self._adapter_player = None
        self._adapter_tracklist = None

        if self._error_filter is not None:
            logging.getLogger().removeFilter(self._error_filter)
            self._error_filter = None

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

        if self._update_notifier is None:
            _LOGGER.warning("MPRIS update notifier not initialized; cannot emit metadata change")
            return

        try:
            self._update_notifier.emitterPlayer.emitPropertyChangeAll()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS metadata change", exc_info=True)

    def set_progress(self, progress_ms: int | None) -> None:
        """Update track progress."""
        self._state.progress_ms = progress_ms

    def set_playback_state(self, state: PlaybackStateType) -> None:
        """Update playback state."""
        self._state.playback_state = state

        if self._update_notifier is None:
            _LOGGER.warning(
                "MPRIS update notifier not initialized; cannot emit playback state change"
            )
            return

        try:
            self._update_notifier.emitterPlayer.emitPropertyChangeAll()
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

        if self._update_notifier is None:
            _LOGGER.warning("MPRIS update notifier not initialized; cannot emit volume change")
            return

        try:
            self._update_notifier.emitterPlayer.emitPropertyChangeAll()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS volume change", exc_info=True)

    def set_supported_commands(self, commands: set[MediaCommand]) -> None:
        """Update supported media commands.

        This affects which controls are shown as available in MPRIS clients.
        """
        self._state.supported_commands = commands

        if self._update_notifier is None:
            _LOGGER.warning("MPRIS update notifier not initialized; cannot emit options change")
            return

        try:
            self._update_notifier.emitterPlayer.emitPropertyChangeAll()
        except Exception:
            _LOGGER.debug("Failed to emit MPRIS options change", exc_info=True)
