"""Rich-based progress display utilities.

Provides two single-responsibility context managers:

- ``OperationSpinner`` — indeterminate spinner for opaque blocking operations
  such as ``docker compose up -d`` or ``docker compose down``, where the total
  duration is unknown and no per-step progress can be observed.

- ``DownloadProgressBar`` — deterministic progress bar for batch file
  downloads where the total number of items is known at the start. Accepts an
  optional per-completion callback (see ``make_callback``) so that async
  callers can advance the bar from inside ``asyncio.gather`` task wrappers.

Both classes accept an optional ``console`` parameter so they slot in cleanly
alongside an existing ``rich.console.Console`` instance without creating a
second output stream.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.status import Status

if TYPE_CHECKING:
    pass


class OperationSpinner:
    """Indeterminate spinner for a single named blocking operation.

    Wraps ``console.status()`` as a context manager with a consistent
    ``spinner="dots"`` style. Intended for docker compose commands where the
    subprocess duration is unknown.

    Usage::

        with OperationSpinner("Deploying pihole-unbound…", console=console):
            deploy_project_stack(compose_file, slug, env_files)
    """

    def __init__(self, message: str, *, console: Console | None = None) -> None:
        self._message = message
        self._console = console or Console()
        self._status: Status | None = None

    def __enter__(self) -> "OperationSpinner":
        self._status = self._console.status(self._message, spinner="dots")
        self._status.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._status is not None:
            self._status.__exit__(exc_type, exc_val, exc_tb)

    def update(self, message: str) -> None:
        """Update the spinner label while the operation is in progress."""
        if self._status is not None:
            self._status.update(message)


class DownloadProgressBar:
    """Deterministic progress bar for a batch of file downloads.

    The ``total`` number of items must be known at construction time. Each
    call to ``advance()`` moves the bar forward by one step. Use
    ``make_callback()`` to obtain a zero-argument callable suitable for
    passing to async task wrappers.

    Usage::

        with DownloadProgressBar("Pulling project files", total=len(jobs), console=console) as bar:
            asyncio.run(_download_jobs(jobs, on_job_complete=bar.make_callback()))
    """

    def __init__(
        self,
        description: str,
        total: int,
        *,
        console: Console | None = None,
    ) -> None:
        self._description = description
        self._total = total
        self._console = console or Console()
        self._progress: Progress | None = None
        self._task_id: TaskID | None = None

    def __enter__(self) -> "DownloadProgressBar":
        self._progress = Progress(
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self._console,
        )
        self._progress.__enter__()
        self._task_id = self._progress.add_task(self._description, total=self._total)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._progress is not None:
            self._progress.__exit__(exc_type, exc_val, exc_tb)

    def advance(self, n: int = 1) -> None:
        """Advance the progress bar by *n* steps."""
        if self._progress is not None and self._task_id is not None:
            self._progress.advance(self._task_id, n)

    def make_callback(self) -> Callable[[], None]:
        """Return a zero-argument callable that advances the bar by one step.

        Intended to be passed as ``on_job_complete`` to ``_download_jobs`` so
        that each concurrent download task advances the bar when it finishes::

            bar.make_callback()  # → lambda: self.advance()
        """
        return lambda: self.advance()
