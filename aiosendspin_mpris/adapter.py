"""Internal MPRIS adapter implementation."""

# pyright: reportPossiblyUnboundVariable=false

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, override

from aiosendspin.models.types import MediaCommand, PlaybackStateType

if TYPE_CHECKING:
    from aiosendspin.client import SendspinClient

_LOGGER = logging.getLogger(__name__)

# MPRIS is only available on Linux with mpris_server installed
MPRIS_AVAILABLE = False

if sys.platform == "linux":
    try:
        from mpris_server.adapters import MprisAdapter
        from mpris_server.base import DEFAULT_DESKTOP, PlayState, Volume
        from mpris_server.mpris.metadata import MetadataObj, ValidMetadata

        MPRIS_AVAILABLE = True  # pyright: ignore[reportConstantRedefinition]
    except ImportError:
        pass

if not MPRIS_AVAILABLE:

    class _DummyMprisAdapter:
        """Dummy adapter base class when mpris_server is not installed."""

        def __init__(self) -> None:
            pass

    if not TYPE_CHECKING:  # otherwise pyright complains too much
        MprisAdapter = _DummyMprisAdapter


@dataclass
class MprisState:
    """Internal state for MPRIS adapter."""

    supported_commands: set[MediaCommand] = field(default_factory=set)
    playback_state: PlaybackStateType | None = None
    volume: int = 100
    muted: bool = False
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    duration_ms: int | None = None
    progress_ms: int | None = None


class SendspinMprisAdapter(MprisAdapter):
    """Adapter bridging Sendspin state to MPRIS interface.

    This adapter reads state from an internal MprisState dataclass and
    dispatches commands to the SendspinClient.
    """

    _client: SendspinClient
    _loop: asyncio.AbstractEventLoop
    _state: MprisState
    _desktop_entry: str | None

    def __init__(
        self,
        client: SendspinClient,
        loop: asyncio.AbstractEventLoop,
        state: MprisState,
        desktop_entry: str | None,
    ) -> None:
        """Initialize the MPRIS adapter."""
        super().__init__()
        self._client = client
        self._loop = loop
        self._state = state
        self._desktop_entry = desktop_entry

    @override
    def get_uri_schemes(self) -> list[str]:
        """Return supported URI schemes."""
        return ["ws", "wss"]

    @override
    def get_mime_types(self) -> list[str]:
        """Return supported MIME types."""
        return ["audio/*"]

    @override
    def get_desktop_entry(self) -> str:
        """Return desktop entry name."""
        return self._desktop_entry or DEFAULT_DESKTOP

    @override
    def metadata(self) -> ValidMetadata:
        """Return current track metadata in MPRIS format."""
        duration_us = (self._state.duration_ms or 0) * 1000
        return MetadataObj(
            track_id="/org/sendspin/track/current",
            length=duration_us,
            title=self._state.title or "",
            artists=[self._state.artist] if self._state.artist else [],
            album=self._state.album or "",
        )

    @override
    def get_playstate(self) -> PlayState:
        """Return current playback state."""
        if self._state.playback_state == PlaybackStateType.PLAYING:
            return PlayState.PLAYING
        if self._state.playback_state == PlaybackStateType.PAUSED:
            return PlayState.PAUSED
        return PlayState.STOPPED

    @override
    def get_current_position(self) -> int:
        """Return current track position in microseconds."""
        return (self._state.progress_ms or 0) * 1000

    @override
    def get_volume(self) -> Volume:
        """Return current volume as 0.0-1.0."""
        if self._state.muted:
            return Volume(0.0)
        return Volume(self._state.volume / 100.0)

    @override
    def set_volume(self, value: Volume) -> None:
        """Set volume from 0.0-1.0 value."""
        volume_int = max(0, min(100, int(value * 100)))
        self._dispatch_command(MediaCommand.VOLUME, volume=volume_int)

    @override
    def is_mute(self) -> bool:
        """Return whether player is muted."""
        return self._state.muted

    @override
    def set_mute(self, value: bool) -> None:
        """Set mute state."""
        if value != self._state.muted:
            self._dispatch_command(MediaCommand.MUTE, mute=value)

    @override
    def can_control(self) -> bool:
        """Return whether the player can be controlled."""
        return True

    @override
    def can_play(self) -> bool:
        """Return whether play is supported."""
        return MediaCommand.PLAY in self._state.supported_commands

    @override
    def can_pause(self) -> bool:
        """Return whether pause is supported."""
        return MediaCommand.PAUSE in self._state.supported_commands

    @override
    def can_go_next(self) -> bool:
        """Return whether next track is supported."""
        return MediaCommand.NEXT in self._state.supported_commands

    @override
    def can_go_previous(self) -> bool:
        """Return whether previous track is supported."""
        return MediaCommand.PREVIOUS in self._state.supported_commands

    @override
    def can_seek(self) -> bool:
        """Return whether seeking is supported."""
        return False

    @override
    def can_quit(self) -> bool:
        """Return whether quit is supported."""
        return False

    @override
    def can_raise(self) -> bool:
        """Return whether raise window is supported."""
        return False

    @override
    def can_fullscreen(self) -> bool:
        """Return whether fullscreen is supported."""
        return False

    @override
    def get_active_playlist(self) -> tuple[bool, tuple[str, str, str]]:
        """Return active playlist info. We don't support playlists."""
        return (False, ("/", "", ""))

    @override
    def get_playlist_count(self) -> int:
        """Return number of playlists."""
        return 0

    @override
    def get_playlists(
        self, index: int, max_count: int, order: str, reverse: bool
    ) -> list[tuple[str, str, str]]:
        """Return list of playlists."""
        return []

    @override
    def play(self) -> None:
        """Start playback."""
        self._dispatch_command(MediaCommand.PLAY)

    @override
    def pause(self) -> None:
        """Pause playback."""
        self._dispatch_command(MediaCommand.PAUSE)

    @override
    def next(self) -> None:
        """Skip to next track."""
        self._dispatch_command(MediaCommand.NEXT)

    @override
    def previous(self) -> None:
        """Skip to previous track."""
        self._dispatch_command(MediaCommand.PREVIOUS)

    @override
    def stop(self) -> None:
        """Stop playback."""
        self._dispatch_command(MediaCommand.STOP)

    @override
    def get_stream_title(self) -> str:
        """Return stream title."""
        return self._state.title or ""

    def _dispatch_command(
        self, command: MediaCommand, *, volume: int | None = None, mute: bool | None = None
    ) -> None:
        """Dispatch command to async handler via thread-safe mechanism."""
        try:
            _ = asyncio.run_coroutine_threadsafe(
                self._client.send_group_command(command, volume=volume, mute=mute),
                self._loop,
            )
        except RuntimeError:
            _LOGGER.debug("Failed to dispatch MPRIS command: event loop not available")
