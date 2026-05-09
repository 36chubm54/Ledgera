from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from tkinter import TclError
from typing import Any, Protocol, cast


class AfterOwner(Protocol):
    def after(
        self, ms: int | str, func: Callable[..., object] | None = None, *args: object
    ) -> str: ...

    def after_idle(self, func: Callable[..., object], *args: object) -> str: ...

    def after_cancel(self, id: str) -> None: ...


class UiRuntimeCoordinator:
    def __init__(self, owner: Any, *, max_workers: int = 2) -> None:
        self._owner = cast(AfterOwner, owner)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._after_jobs: dict[str, str] = {}

    @property
    def after_jobs(self) -> dict[str, str]:
        return self._after_jobs

    def shutdown(self) -> None:
        self.cancel_all_after_jobs()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def cancel_all_after_jobs(self) -> None:
        for key in list(self._after_jobs):
            self.cancel_after_job(key)

    def cancel_after_job(self, key: str) -> None:
        job_id = self._after_jobs.pop(key, None)
        if not job_id:
            return
        try:
            self._owner.after_cancel(job_id)
        except TclError:
            return

    def schedule_after(self, key: str, delay_ms: int, callback: Callable[[], None]) -> str:
        self.cancel_after_job(key)

        def _run() -> None:
            self._after_jobs.pop(key, None)
            callback()

        job_id = self._owner.after(delay_ms, _run)
        self._after_jobs[key] = str(job_id)
        return str(job_id)

    def schedule_after_idle(self, key: str, callback: Callable[[], None]) -> str:
        self.cancel_after_job(key)

        def _run() -> None:
            self._after_jobs.pop(key, None)
            callback()

        job_id = self._owner.after_idle(_run)
        self._after_jobs[key] = str(job_id)
        return str(job_id)

    def run_background(
        self,
        task: Callable[[], Any],
        *,
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None] | None,
        busy_message: str,
        block_ui: bool,
        is_busy: Callable[[], bool],
        set_busy: Callable[[bool, str], None],
        show_info: Callable[[str], None],
        show_error: Callable[[str], None],
        logger: logging.Logger,
    ) -> None:
        if block_ui and is_busy():
            show_info("wait")
            return
        if block_ui:
            set_busy(True, busy_message)
        future: Future[Any] = self._executor.submit(task)
        poll_job_key = f"background_poll:{id(future)}"

        def _poll() -> None:
            if not future.done():
                self.schedule_after(poll_job_key, 100, _poll)
                return
            if block_ui:
                set_busy(False, "")
            error = future.exception()
            if error is not None:
                if on_error is not None:
                    on_error(error)
                else:
                    logger.exception("Background operation failed", exc_info=error)
                    show_error(str(error))
                return
            result = future.result()
            try:
                on_success(result)
            except Exception as callback_error:
                logger.exception("Background success callback failed", exc_info=callback_error)
                show_error(str(callback_error))

        self.schedule_after(poll_job_key, 100, _poll)
