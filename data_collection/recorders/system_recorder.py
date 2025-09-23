"""System metrics recorder.

The :class:`SystemRecorder` class samples CPU, GPU and memory statistics and
emits structured events via the shared :class:`JsonlWriter`.  The sampler runs
on a background thread so that it can operate alongside the other recorders
without blocking the main session flow.

Only a minimal dependency footprint is required – ``psutil`` is used for
general system information and GPU telemetry is attempted through optional
providers (NVML via ``pynvml`` or ``GPUtil``).  If GPU inspection is
unavailable the recorder gracefully degrades and still emits CPU / memory
metrics alongside a metadata notice.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from core.events import Event

from ..event_writer import JsonlWriter


def _event_dump(event: Event) -> Dict[str, Any]:
    """Return a serialisable representation of ``event``.

    The project still mixes pydantic v1/v2 helpers in different places.  This
    helper provides a single call site that works with either implementation by
    preferring :meth:`model_dump` (v2) and falling back to :meth:`dict` (v1).
    """

    if hasattr(event, "model_dump"):
        return event.model_dump()  # type: ignore[return-value]
    return event.dict()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GPU collectors (optional dependencies)
# ---------------------------------------------------------------------------


class _GPUBackend:
    """Internal protocol for GPU inspectors."""

    name: str = ""

    def describe(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def sample(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def shutdown(self) -> None:  # pragma: no cover - backends may be no-op
        pass


class _NvmlBackend(_GPUBackend):
    """GPU metrics via ``pynvml`` (NVIDIA)."""

    name = "pynvml"

    def __init__(self) -> None:
        import pynvml

        self._nvml = pynvml
        self._nvml.nvmlInit()
        self._handles = [
            self._nvml.nvmlDeviceGetHandleByIndex(i)
            for i in range(self._nvml.nvmlDeviceGetCount())
        ]

    def describe(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        for idx, handle in enumerate(self._handles):
            with contextlib.suppress(self._nvml.NVMLError):
                name = self._nvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                mem = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                gpus.append(
                    {
                        "index": idx,
                        "name": name,
                        "memory_total": int(mem.total),
                    }
                )
        return gpus

    def sample(self) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        for idx, handle in enumerate(self._handles):
            try:
                name = self._nvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                util = self._nvml.nvmlDeviceGetUtilizationRates(handle)
                mem = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                try:
                    temp = self._nvml.nvmlDeviceGetTemperature(
                        handle, self._nvml.NVML_TEMPERATURE_GPU
                    )
                except self._nvml.NVMLError:
                    temp = None
                try:
                    fan = self._nvml.nvmlDeviceGetFanSpeed(handle)
                except self._nvml.NVMLError:
                    fan = None
            except self._nvml.NVMLError as exc:  # pragma: no cover - defensive
                raise RuntimeError(str(exc)) from exc

            samples.append(
                {
                    "index": idx,
                    "name": name,
                    "utilization": {
                        "gpu": int(util.gpu),
                        "memory": int(util.memory),
                    },
                    "memory": {
                        "total": int(mem.total),
                        "used": int(mem.used),
                        "free": int(mem.free),
                    },
                    "temperature": temp,
                    "fan_speed": fan,
                }
            )
        return samples

    def shutdown(self) -> None:  # pragma: no cover - trivial
        with contextlib.suppress(self._nvml.NVMLError):
            self._nvml.nvmlShutdown()


class _GPUtilBackend(_GPUBackend):
    """GPU metrics via :mod:`GPUtil` (if installed)."""

    name = "gputil"

    def __init__(self) -> None:
        import GPUtil

        self._gputil = GPUtil

    def _current(self):
        return self._gputil.getGPUs()

    def describe(self) -> List[Dict[str, Any]]:
        gpus: List[Dict[str, Any]] = []
        for gpu in self._current():
            gpus.append(
                {
                    "index": gpu.id,
                    "name": gpu.name,
                    "memory_total": int(gpu.memoryTotal * 1024 * 1024),
                }
            )
        return gpus

    def sample(self) -> List[Dict[str, Any]]:
        samples: List[Dict[str, Any]] = []
        for gpu in self._current():
            samples.append(
                {
                    "index": gpu.id,
                    "name": gpu.name,
                    "utilization": {
                        "gpu": float(gpu.load * 100.0),
                        "memory": float(gpu.memoryUtil * 100.0),
                    },
                    "memory": {
                        "total": int(gpu.memoryTotal * 1024 * 1024),
                        "used": int(gpu.memoryUsed * 1024 * 1024),
                        "free": int(gpu.memoryFree * 1024 * 1024),
                    },
                    "temperature": gpu.temperature,
                    "fan_speed": getattr(gpu, "fanSpeed", None),
                }
            )
        return samples


class _GPUCollector:
    """Wrapper that selects an available GPU backend (if any)."""

    def __init__(self) -> None:
        self._backend: Optional[_GPUBackend] = None
        self._backend_name: Optional[str] = None
        self._last_error: Optional[str] = None

        for backend_cls in (_NvmlBackend, _GPUtilBackend):
            try:
                self._backend = backend_cls()
            except Exception as exc:  # pragma: no cover - optional deps
                self._backend = None
                self._last_error = str(exc)
                continue
            else:
                self._backend_name = self._backend.name
                self._last_error = None
                break

    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> Optional[str]:
        return self._backend_name

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def describe(self) -> List[Dict[str, Any]]:
        if not self._backend:
            return []
        try:
            return self._backend.describe()
        except Exception as exc:  # pragma: no cover - defensive
            self._last_error = str(exc)
            return []

    def sample(self) -> List[Dict[str, Any]]:
        if not self._backend:
            return []
        try:
            return self._backend.sample()
        except Exception as exc:  # pragma: no cover - defensive
            self._last_error = str(exc)
            return []

    def shutdown(self) -> None:
        if not self._backend:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - defensive
            self._backend.shutdown()


# ---------------------------------------------------------------------------
# System recorder
# ---------------------------------------------------------------------------


@dataclass
class SystemRecorderConfig:
    """Configuration for :class:`SystemRecorder`."""

    poll_interval: float = 1.0
    include_per_cpu: bool = True
    include_swap: bool = True


class SystemRecorder:
    """Sample CPU/GPU/RAM utilisation and emit events."""

    def __init__(
        self,
        session: str,
        session_dir: Optional[Path],
        events_writer: JsonlWriter,
        *,
        config: Optional[SystemRecorderConfig] = None,
    ) -> None:
        self.session = session
        self.session_dir = Path(session_dir) if session_dir is not None else None
        self.events_writer = events_writer
        self._cfg = config or SystemRecorderConfig()
        self._poll_interval = max(0.1, float(self._cfg.poll_interval))
        self._include_per_cpu = bool(self._cfg.include_per_cpu)
        self._include_swap = bool(self._cfg.include_swap)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._gpu = _GPUCollector()
        self._emitted_errors: set[str] = set()
        self._primed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():  # already running
            return
        self._stop_event.clear()
        if not self._primed:
            if self._include_per_cpu:
                psutil.cpu_percent(interval=None, percpu=True)
            else:
                psutil.cpu_percent(interval=None)
            self._primed = True

        self._emit_static_meta()
        self._thread = threading.Thread(target=self._run, name="system-metrics", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._gpu.shutdown()
        self._primed = False

    # ------------------------------------------------------------------
    # Sampling helpers
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            start = time.monotonic()
            try:
                sample = self._collect_sample()
            except Exception as exc:  # pragma: no cover - defensive
                self._emit_error(str(exc))
            else:
                event = Event(kind="system", session=self.session, data=sample)
                self.events_writer.write(_event_dump(event))

            elapsed = time.monotonic() - start
            wait_for = self._poll_interval - elapsed
            if wait_for > 0:
                self._stop_event.wait(wait_for)

    def _collect_sample(self) -> Dict[str, Any]:
        cpu_info = self._cpu_metrics()
        mem_info = self._memory_metrics()
        gpu_info = self._gpu.sample()

        if not gpu_info and self._gpu.last_error:
            self._emit_error(self._gpu.last_error)

        return {
            "cpu": cpu_info,
            "memory": mem_info,
            "gpu": gpu_info,
        }

    # Individual metric collectors -------------------------------------------------
    def _cpu_metrics(self) -> Dict[str, Any]:
        cpu: Dict[str, Any] = {}

        if self._include_per_cpu:
            per_cpu = psutil.cpu_percent(interval=None, percpu=True)
            cpu["percpu_percent"] = per_cpu
            if per_cpu:
                cpu["percent"] = float(sum(per_cpu) / len(per_cpu))
        else:
            cpu["percent"] = float(psutil.cpu_percent(interval=None))

        freq = psutil.cpu_freq()
        if freq:
            cpu["frequency_mhz"] = {
                "current": freq.current,
                "min": freq.min,
                "max": freq.max,
            }

        with contextlib.suppress(Exception):
            stats = psutil.cpu_stats()
            cpu["ctx_switches"] = stats.ctx_switches
            cpu["interrupts"] = stats.interrupts

        if hasattr(psutil, "getloadavg"):
            with contextlib.suppress(OSError):
                load1, load5, load15 = psutil.getloadavg()
                cpu["load_average"] = {
                    "1m": load1,
                    "5m": load5,
                    "15m": load15,
                }

        return cpu

    def _memory_metrics(self) -> Dict[str, Any]:
        vm = psutil.virtual_memory()
        memory: Dict[str, Any] = {
            "virtual": {
                "total": int(vm.total),
                "available": int(vm.available),
                "used": int(vm.used),
                "free": int(vm.free),
                "percent": float(vm.percent),
            }
        }

        if hasattr(vm, "active"):
            memory["virtual"]["active"] = int(getattr(vm, "active"))
        if hasattr(vm, "inactive"):
            memory["virtual"]["inactive"] = int(getattr(vm, "inactive"))
        if hasattr(vm, "buffers"):
            memory["virtual"]["buffers"] = int(getattr(vm, "buffers"))
        if hasattr(vm, "cached"):
            memory["virtual"]["cached"] = int(getattr(vm, "cached"))

        if self._include_swap:
            swap = psutil.swap_memory()
            memory["swap"] = {
                "total": int(swap.total),
                "used": int(swap.used),
                "free": int(swap.free),
                "percent": float(swap.percent),
            }

        return memory

    # ------------------------------------------------------------------
    # Emission helpers
    # ------------------------------------------------------------------
    def _emit_static_meta(self) -> None:
        cpu_count = psutil.cpu_count(logical=True)
        cpu_physical = psutil.cpu_count(logical=False)
        vm = psutil.virtual_memory()

        payload: Dict[str, Any] = {
            "system": {
                "poll_interval": self._poll_interval,
                "cpu": {
                    "logical_cores": cpu_count,
                    "physical_cores": cpu_physical,
                },
                "memory": {
                    "total": int(vm.total),
                },
            }
        }

        if self._gpu.available:
            payload["system"]["gpu"] = {
                "available": True,
                "backend": self._gpu.backend_name,
                "devices": self._gpu.describe(),
            }
        else:
            payload["system"]["gpu"] = {
                "available": False,
                "error": self._gpu.last_error,
            }

        event = Event(kind="meta", session=self.session, data=payload)
        self.events_writer.write(_event_dump(event))

    def _emit_error(self, message: str) -> None:
        if not message or message in self._emitted_errors:
            return
        self._emitted_errors.add(message)
        payload = {"system": {"error": message}}
        event = Event(kind="meta", session=self.session, data=payload)
        self.events_writer.write(_event_dump(event))


__all__ = ["SystemRecorder", "SystemRecorderConfig"]