import subprocess
from pathlib import Path
from typing import List, Tuple
from ..core.config import (
    MARKER_CLI,
    MARKER_FLAGS,
    OUTPUTS_DIR,
    OUTPUT_FORMAT,
    GPU_TEMP_THRESHOLD_C,
    GPU_MEM_FREE_MB,
    GPU_WAIT_TIMEOUT_SEC,
    GPU_POLL_INTERVAL_SEC,
)
from ..core.logger import get_logger
from ..core.exceptions import MarkerError
import shlex
import time
import os

logger = get_logger(__name__)


def run_marker_for_chunk(chunk_path: Path, output_dir: Path = None) -> Path:
    """Run marker on a chunk (image or PDF) and return path to markdown output.
    
    Args:
        chunk_path: Path to the input file (image or PDF)
        output_dir: Directory where marker should save outputs. 
                   If None, uses MARKER_OUTPUT_DIR from config.
    
    Returns:
        Path to the extracted markdown file
    
    Raises:
        MarkerError: If marker processing fails
    """
    if output_dir is None:
        output_dir = OUTPUTS_DIR
    
    out_path = output_dir / f"{chunk_path.stem}.md"

    # If CUDA_VISIBLE_DEVICES is set in env, respect it; otherwise use system default
    env = os.environ.copy()

    # Wait for GPU to be in a safe state before launching heavy processing
    try:
        wait_for_gpu_ready()
    except MarkerError:
        # re-raise to stop processing
        raise

    # Build command with custom output directory
    cmd = [MARKER_CLI, str(chunk_path), "--output_dir", str(output_dir)] + [
        flag for flag in MARKER_FLAGS if "--output_dir" not in flag
    ]

    logger.info(f"Starting Marker for {chunk_path} with cmd: {' '.join(shlex.quote(p) for p in cmd)}")
    start = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    duration = time.time() - start

    # Log summary info at INFO and full outputs at DEBUG so app.log captures details
    logger.info(
        "Marker finished for %s (exit=%s) in %.2fs",
        chunk_path,
        res.returncode,
        duration,
    )
    logger.debug("Marker stdout for %s:\n%s", chunk_path, res.stdout or "<no stdout>")
    logger.debug("Marker stderr for %s:\n%s", chunk_path, res.stderr or "<no stderr>")

    if res.returncode != 0:
        logger.error("Marker failed for %s (exit=%s). See stderr in logs.", chunk_path, res.returncode)
        # ensure stderr is available in the exception message for immediate feedback
        raise MarkerError(f"Marker failed for {chunk_path}: {res.stderr}")
    
    # If marker outputs to stdout or writes file elsewhere, try to discover the produced markdown.
    # First, check the canonical out_path
    if out_path.exists():
        return out_path

    logger.debug("Expected output not found at canonical path; attempting discovery heuristics.")
    
    # Look for the markdown file in the output directory or as a directory with .md file inside
    candidates = []
    stem_pattern = f"{chunk_path.stem}*"

    try:
        candidates.extend(list(output_dir.glob(stem_pattern)))
    except Exception:
        logger.debug(f"Could not access output_dir: {output_dir}")

    # Look in the input file's parent (where marker may have placed outputs)
    try:
        candidates.extend(list(chunk_path.parent.glob(stem_pattern)))
    except Exception:
        pass

    # Look in current working directory
    try:
        candidates.extend(list(Path.cwd().glob(stem_pattern)))
    except Exception:
        pass

    # Parse stdout/stderr for any .md path
    text = (res.stdout or "") + "\n" + (res.stderr or "")
    import re
    md_paths = re.findall(r"[A-Za-z0-9_:\\/.\- ]+\.md", text)
    for p in md_paths:
        p = p.strip()
        try:
            pth = Path(p)
            if pth.exists() and pth.is_file():
                candidates.append(pth)
        except Exception:
            continue

    # Deduplicate and sort by modification time (newest first)
    unique = {}
    for c in candidates:
        try:
            unique[str(c.resolve())] = c
        except Exception:
            unique[str(c)] = c

    candidates = list(unique.values())
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

    if candidates:
        chosen = candidates[0]
        logger.info(f"Discovered Marker output at {chosen}")
        
        # If it's a directory, look for .md file inside
        if chosen.is_dir():
            md_files = list(chosen.glob("*.md"))
            if md_files:
                chosen = md_files[0]
                logger.info(f"Found markdown file inside directory: {chosen}")
        
        if chosen.is_file() and chosen.suffix == ".md":
            return chosen

    # Nothing found
    logger.error("Marker finished but no markdown output discovered; stdout/stderr below:\n%s", text)
    raise MarkerError(f"Expected markdown output not found after Marker run for {chunk_path}")


def _query_nvidia_smi() -> List[Tuple[int, int, int, int]]:
    """Return list of tuples (index, temp_c, mem_total_mb, mem_used_mb) for each GPU.
    If nvidia-smi is not available or fails, return empty list.
    """
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=index,temperature.gpu,memory.total,memory.used",
            "--format=csv,noheader,nounits",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.debug(f"nvidia-smi returned non-zero: {res.stderr}")
            return []

        lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
        out = []
        for ln in lines:
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) >= 4:
                idx = int(parts[0])
                temp = int(parts[1])
                mem_total = int(parts[2])
                mem_used = int(parts[3])
                out.append((idx, temp, mem_total, mem_used))
        return out
    except FileNotFoundError:
        logger.debug("nvidia-smi not found; skipping GPU queries")
        return []
    except Exception as e:
        logger.debug(f"Error querying nvidia-smi: {e}")
        return []


def _gpu_state_ok() -> bool:
    """Return True if all GPUs are below temp threshold and have sufficient free memory.
    If no GPUs are present or nvidia-smi unavailable, return True (no GPU to wait on).
    """
    gpus = _query_nvidia_smi()
    if not gpus:
        return True

    for idx, temp, mem_total, mem_used in gpus:
        mem_free = mem_total - mem_used
        if temp >= GPU_TEMP_THRESHOLD_C:
            logger.debug(f"GPU {idx} temp {temp}C >= threshold {GPU_TEMP_THRESHOLD_C}C")
            return False
        if mem_free < GPU_MEM_FREE_MB:
            logger.debug(f"GPU {idx} free mem {mem_free}MB < required {GPU_MEM_FREE_MB}MB")
            return False
    return True


def wait_for_gpu_ready(timeout: int = GPU_WAIT_TIMEOUT_SEC, poll: int = GPU_POLL_INTERVAL_SEC):
    """Block until GPU(s) are below thresholds or timeout reached. Raises MarkerError on timeout.
    If no GPUs detected, returns immediately.
    """
    start = time.time()
    # quick check
    if _gpu_state_ok():
        return

    logger.info("Waiting for GPU(s) to cool down and free memory before starting next chunk")
    while True:
        if _gpu_state_ok():
            logger.info("GPU(s) are ready")
            return
        if time.time() - start > timeout:
            msg = f"Timeout waiting for GPU to become available after {timeout}s"
            logger.error(msg)
            raise MarkerError(msg)
        time.sleep(poll)
