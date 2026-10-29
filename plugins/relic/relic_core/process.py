"""Shared creation flags for Relic's subprocesses, including children of pythonw."""
import os

WINDOWS = os.name == "nt"


def creation_flags(flags=0):
    """Keep process-group flags, but never allocate a Windows console.

    CREATE_NEW_CONSOLE and DETACHED_PROCESS override CREATE_NO_WINDOW, so remove
    them even when a caller supplies flags. Native UI is opened only by explicit
    user actions (for example launching Windows Terminal), never by auto-wake.
    """
    return (flags & ~(0x00000010 | 0x00000008)) | 0x08000000 if WINDOWS else 0
