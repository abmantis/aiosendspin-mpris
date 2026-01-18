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
    from tunit.unit import Microseconds

_LOGGER = logging.getLogger(__name__)

# MPRIS is only available on Linux with mpris_api installed
MPRIS_AVAILABLE = False

if sys.platform == "linux":
    try:
        from mpris_api.adapter.IMprisAdapterPlayer import IMprisAdapterPlayer
        from mpris_api.adapter.IMprisAdapterPlayLists import IMprisAdapterPlayLists
        from mpris_api.adapter.IMprisAdapterRoot import IMprisAdapterRoot
        from mpris_api.adapter.IMprisAdapterTrackList import IMprisAdapterTrackList
        from mpris_api.common.DbusObject import DbusObject
        from mpris_api.model.MprisLoopStatus import MprisLoopStatus
        from mpris_api.model.MprisMetaData import MprisMetaData
        from mpris_api.model.MprisPlaybackStatus import MprisPlaybackStatus
        from mpris_api.model.MprisPlaylist import MprisPlaylist
        from mpris_api.model.MprisPlaylistOrdering import MprisPlaylistOrdering
        from tunit.unit import Microseconds

        MPRIS_AVAILABLE = True  # pyright: ignore[reportConstantRedefinition]
    except ImportError:
        pass

if not MPRIS_AVAILABLE:

    class _DummyIMprisAdapterRoot:
        """Dummy adapter base class when mpris_api is not installed."""

        def __init__(self) -> None:
            pass

    class _DummyIMprisAdapterPlayer:
        """Dummy adapter base class when mpris_api is not installed."""

        def __init__(self) -> None:
            pass

    class _DummyIMprisAdapterTrackList:
        """Dummy adapter base class when mpris_api is not installed."""

        def __init__(self) -> None:
            pass

    class _DummyIMprisAdapterPlayLists:
        """Dummy adapter base class when mpris_api is not installed."""

        def __init__(self) -> None:
            pass

    if not TYPE_CHECKING:  # otherwise pyright complains too much
        IMprisAdapterRoot = _DummyIMprisAdapterRoot
        IMprisAdapterPlayer = _DummyIMprisAdapterPlayer
        IMprisAdapterTrackList = _DummyIMprisAdapterTrackList
        IMprisAdapterPlayLists = _DummyIMprisAdapterPlayLists


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


class SendspinMprisAdapterRoot(IMprisAdapterRoot):
    """Adapter for the MPRIS Root interface (org.mpris.MediaPlayer2)."""

    _identity: str
    _desktop_entry: str | None

    def __init__(self, identity: str, desktop_entry: str | None = None) -> None:
        """Initialize the MPRIS root adapter."""
        self._identity = identity
        self._desktop_entry = desktop_entry

    @override
    def canRaise(self) -> bool:
        """Return whether raise window is supported."""
        return False

    @override
    def canQuit(self) -> bool:
        """Return whether quit is supported."""
        return False

    @override
    def canSetFullscreen(self) -> bool:
        """Return whether fullscreen is supported."""
        return False

    @override
    def getIdentity(self) -> str:
        """Return application identity."""
        return self._identity

    @override
    def getDesktopEntry(self) -> str | None:
        """Return desktop entry name."""
        return self._desktop_entry

    @override
    def getSupportedUriSchemes(self) -> list[str]:
        """Return supported URI schemes."""
        return ["ws", "wss"]

    @override
    def getSupportedMimeTypes(self) -> list[str]:
        """Return supported MIME types."""
        return ["audio/*"]

    @override
    def hasTracklist(self) -> bool:
        """Return whether tracklist is supported."""
        return False

    @override
    def isFullScreen(self) -> bool:
        """Return whether app is fullscreen."""
        return False

    @override
    def setFullScreen(self, value: bool) -> None:
        """Set fullscreen state (not supported)."""

    @override
    def quitApp(self) -> None:
        """Quit application (not supported)."""

    @override
    def raiseApp(self) -> None:
        """Raise application window (not supported)."""


class SendspinMprisAdapterPlayer(IMprisAdapterPlayer):
    """Adapter bridging Sendspin state to MPRIS Player interface.

    This adapter reads state from an internal MprisState dataclass and
    dispatches commands to the SendspinClient.
    """

    _client: SendspinClient
    _loop: asyncio.AbstractEventLoop
    _state: MprisState

    def __init__(
        self, client: SendspinClient, loop: asyncio.AbstractEventLoop, state: MprisState
    ) -> None:
        """Initialize the MPRIS player adapter."""
        self._client = client
        self._loop = loop
        self._state = state

    @override
    def canControl(self) -> bool:
        """Return whether the player can be controlled."""
        return True

    @override
    def canPlay(self) -> bool:
        """Return whether play is supported."""
        return MediaCommand.PLAY in self._state.supported_commands

    @override
    def canPause(self) -> bool:
        """Return whether pause is supported."""
        return MediaCommand.PAUSE in self._state.supported_commands

    @override
    def canGoNext(self) -> bool:
        """Return whether next track is supported."""
        return MediaCommand.NEXT in self._state.supported_commands

    @override
    def canGoPrevious(self) -> bool:
        """Return whether previous track is supported."""
        return MediaCommand.PREVIOUS in self._state.supported_commands

    @override
    def canSeek(self) -> bool:
        """Return whether seeking is supported."""
        return False

    @override
    def getMinimumRate(self) -> float:
        """Return minimum playback rate."""
        return 1.0

    @override
    def getMaximumRate(self) -> float:
        """Return maximum playback rate."""
        return 1.0

    @override
    def getRate(self) -> float:
        """Return current playback rate."""
        return 1.0

    @override
    def setRate(self, value: float) -> None:
        """Set playback rate (not supported)."""

    @override
    def getVolume(self) -> float:
        """Return current volume as 0.0-1.0."""
        if self._state.muted:
            return 0.0
        return self._state.volume / 100.0

    @override
    def setVolume(self, value: float) -> None:
        """Set volume from 0.0-1.0 value."""
        volume_int = max(0, min(100, int(value * 100)))
        self._dispatch_command(MediaCommand.VOLUME, volume=volume_int)

    @override
    def getMetadata(self) -> MprisMetaData:
        """Return current track metadata in MPRIS format."""
        duration_us = Microseconds((self._state.duration_ms or 0) * 1000)
        return MprisMetaData(
            trackId=DbusObject.fromName("sendspin_track_current"),
            length=duration_us,
            title=self._state.title or "",
            artists=[self._state.artist] if self._state.artist else None,
            album=self._state.album or "",
        )

    @override
    def getPlaybackStatus(self) -> MprisPlaybackStatus:
        """Return current playback state."""
        if self._state.playback_state == PlaybackStateType.PLAYING:
            return MprisPlaybackStatus.PLAYING
        if self._state.playback_state == PlaybackStateType.PAUSED:
            return MprisPlaybackStatus.PAUSED
        return MprisPlaybackStatus.STOPPED

    @override
    def getPosition(self) -> Microseconds:
        """Return current track position in microseconds."""
        return Microseconds((self._state.progress_ms or 0) * 1000)

    @override
    def getLoopStatus(self) -> MprisLoopStatus:
        """Return loop status (not supported, always None)."""
        return MprisLoopStatus.NONE

    @override
    def setLoopStatus(self, value: MprisLoopStatus) -> None:
        """Set loop status (not supported)."""

    @override
    def isShuffle(self) -> bool:
        """Return whether shuffle is enabled."""
        return False

    @override
    def setShuffle(self, value: bool) -> None:
        """Set shuffle state (not supported)."""

    @override
    def stop(self) -> None:
        """Stop playback."""
        self._dispatch_command(MediaCommand.STOP)

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
    def seek(self, position: Microseconds, trackId: str | None = None) -> None:
        """Seek to position (not supported)."""

    @override
    def openUri(self, uri: str) -> None:
        """Open URI (not supported)."""

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


class SendspinMprisAdapterTrackList(IMprisAdapterTrackList):
    """Stub adapter for the MPRIS TrackList interface.

    This provides an empty implementation to prevent D-Bus errors when
    clients query for the TrackList interface.
    """

    @override
    def getTracksMetadata(self, trackIds: list[str]) -> list[MprisMetaData]:
        """Return metadata for the given track IDs (empty - not supported)."""
        return []

    @override
    def addTrack(self, uri: str, goTo: bool = False, afterTrackId: str | None = None) -> None:
        """Add a track (not supported)."""

    @override
    def removeTrack(self, trackId: str) -> None:
        """Remove a track (not supported)."""

    @override
    def gotTo(self, trackId: str) -> None:
        """Go to a track (not supported)."""

    @override
    def canEditTracks(self) -> bool:
        """Return whether editing tracks is supported."""
        return False

    @override
    def getTracks(self) -> list[DbusObject]:
        """Return list of tracks (empty - not supported)."""
        return []


class SendspinMprisAdapterPlaylists(IMprisAdapterPlayLists):
    """Stub adapter for the MPRIS PlayLists interface.

    This provides an empty implementation to prevent D-Bus errors when
    clients query for the PlayLists interface.
    """

    @override
    def getPlaylistCount(self) -> int:
        return 0

    @override
    def getAvailableOrderings(self) -> list[MprisPlaylistOrdering]:
        return []

    @override
    def getActivePlaylist(self) -> MprisPlaylist | None:
        return None

    @override
    def activatePlaylist(self, playlistId: str) -> None:
        pass

    @override
    def getPlaylists(
        self, index: int, maxCount: int, order: MprisPlaylistOrdering, reverseOrder: bool
    ) -> list[MprisPlaylist]:
        return []
