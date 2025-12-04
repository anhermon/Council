"""Terminal spinner for async operations."""

import asyncio
import shutil
import sys


class Spinner:
    """Manages spinner display for async operations."""

    SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    DEFAULT_TERMINAL_WIDTH = 80
    SPINNER_REFRESH_RATE = 0.15  # seconds between spinner updates
    SPINNER_CLEANUP_TIMEOUT = 1.0  # seconds to wait for spinner task cleanup

    def __init__(self, enabled: bool | None = None) -> None:
        """
        Initialize the spinner.

        Args:
            enabled: Whether spinner is enabled. If None, auto-detect based on TTY.
        """
        self.current_status = "Analyzing code structure..."
        self.spinner_idx = 0
        self.active = False
        # Auto-detect if enabled is None: only enable if stderr is a TTY
        if enabled is None:
            self.enabled = self._is_tty()
        else:
            self.enabled = enabled

    @staticmethod
    def _is_tty() -> bool:
        """Check if stderr is a TTY (interactive terminal)."""
        try:
            return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
        except Exception:
            return False

    def show_status(self, message: str | None = None) -> None:
        """Show current status with spinner (only if enabled)."""
        if not self.enabled:
            return
        if message:
            self.current_status = message
        status_msg = (
            f"\r🤖 {self.current_status} "
            f"{self.SPINNER_CHARS[self.spinner_idx % len(self.SPINNER_CHARS)]}"
        )
        self._safe_stderr_write(status_msg)
        self.spinner_idx += 1

    @staticmethod
    def _safe_stderr_write(message: str) -> None:
        """Safely write to stderr with fallback."""
        try:
            if hasattr(sys.stderr, "write") and sys.stderr.writable():
                sys.stderr.write(message)
                sys.stderr.flush()
        except OSError:
            # Specific I/O errors - try stdout as fallback
            try:
                sys.stdout.write(message)
                sys.stdout.flush()
            except OSError:
                # Both stderr and stdout failed, silently ignore
                pass
        except AttributeError as e:
            # Handle missing methods gracefully
            # Log to stderr if possible, but don't fail
            try:
                if hasattr(sys.stderr, "write"):
                    sys.stderr.write(f"Warning: stderr attribute error: {e}\n")
            except Exception:
                pass  # If even logging fails, silently ignore

    async def run(self) -> None:
        """Run the spinner loop (only if enabled)."""
        if not self.enabled:
            return
        self.active = True
        try:
            while self.active:
                self.show_status()
                await asyncio.sleep(self.SPINNER_REFRESH_RATE)
        except asyncio.CancelledError:
            # Expected when cancelling the task
            pass
        except OSError as e:
            # Handle OS-level errors (e.g., terminal issues)
            if self.enabled:
                Spinner._safe_stderr_write(f"\nSpinner OS error: {e}\n")
        except Exception as e:
            # Log unexpected errors but don't crash
            if self.enabled:
                Spinner._safe_stderr_write(f"\nUnexpected spinner error: {e}\n")
        finally:
            self.active = False

    def stop(self) -> None:
        """Stop the spinner and clear the line."""
        self.active = False
        if not self.enabled:
            return
        # Get terminal width or use default
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = self.DEFAULT_TERMINAL_WIDTH
        self._safe_stderr_write("\r" + " " * width + "\r")
