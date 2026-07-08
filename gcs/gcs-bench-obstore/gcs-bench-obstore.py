#!/usr/bin/env python3
"""
Purpose: Script for testing upload and download performance of large files
         using obstore. Test parallelized transfers with disk or memory
         source or destination files, various chunk sizes and worker counts
Blog:    N/A
Author:  Chris Madden
"""
import os
import sys
import asyncio
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm
from obstore.store import GCSStore

load_dotenv()

# Retrieve standard configuration variables
BUCKET_NAME = os.getenv("BUCKET_NAME")
REMOTE_KEY = os.getenv("REMOTE_KEY")
SOURCE_FILE = Path(os.getenv("LOCAL_SOURCE_FILE", "/ramdisk/obstore.bin"))
DEST_FILE = Path(os.getenv("LOCAL_DEST_FILE", "/ramdisk/obstore.bin"))

# Performance benchmark toggles
DOWNLOAD_TO_MEMORY_ONLY = os.getenv("DOWNLOAD_TO_MEMORY_ONLY", "False").lower() in ("true", "1", "yes")

# In-memory upload toggle
UPLOAD_FROM_MEMORY_ONLY_GIB_ENV = os.getenv("UPLOAD_FROM_MEMORY_ONLY_GIB", "0")
try:
    UPLOAD_FROM_MEMORY_ONLY_GIB = float(UPLOAD_FROM_MEMORY_ONLY_GIB_ENV)
except ValueError:
    UPLOAD_FROM_MEMORY_ONLY_GIB = 0.0

if not BUCKET_NAME or not REMOTE_KEY:
    print("Error: BUCKET_NAME and REMOTE_KEY must be set in your .env file.")
    sys.exit(1)


async def upload_file(
    store: GCSStore, 
    local_path: Path, 
    remote_path: str, 
    chunk_size: int, 
    max_concurrency: int, 
    upload_from_memory_gib: float = 0.0,
    verbose: bool = False
):
    """
    Handles asynchronous file uploads to GCS with configurable chunk sizes and worker count.
    Supports on-the-fly, in-memory zero buffer uploads to bypass physical disk IO bottlenecks.
    """
    if upload_from_memory_gib <= 0:
        if not local_path.exists():
            raise FileNotFoundError(f"Source file not found at: {local_path}")
        file_size = local_path.stat().st_size
    else:
        file_size = int(upload_from_memory_gib * (1024**3))

    # Calculate anticipated part count to prevent MPU limit violations (>10k parts)
    estimated_parts = (file_size + chunk_size - 1) // chunk_size
    if estimated_parts > 10000:
        raise ValueError(
            f"Error: Upload size ({file_size / (1024**2):.1f} MiB) with chunk size ({chunk_size / (1024**2):.1f} MiB) "
            f"would require {estimated_parts:,} parts. Object store multi-part uploads are strictly limited to a "
            f"maximum of 10,000 parts. Please increase --chunksize to avoid failure."
        )

    start_time = time.perf_counter()

    if verbose:
        file_size_mib = file_size / (1024**2)
        chunk_size_mib = chunk_size / (1024**2)
        total_chunks = file_size / chunk_size
        local_display = "(Memory)" if upload_from_memory_gib > 0 else str(local_path)
        print(f"local file={local_display}, remote file=gs://{BUCKET_NAME}/{remote_path}, file size={file_size_mib:.1f} MiB")
        print(f"worker count={max_concurrency}, chunk size={chunk_size_mib:.2f} MiB, total chunks={total_chunks:.1f}")
    else:
        print(f"Uploading: {remote_path} ({file_size / (1024**2):.2f} MB)")

    with tqdm(total=file_size, unit="B", unit_scale=True, unit_divisor=1024, desc="Uploading") as pbar:
        if upload_from_memory_gib > 0:
            # Pre-allocate a single dummy block to avoid CPU/allocator overhead
            dummy_chunk = b"\0" * chunk_size
            async def async_chunk_generator():
                bytes_sent = 0
                while bytes_sent < file_size:
                    to_send = min(chunk_size, file_size - bytes_sent)
                    if to_send == chunk_size:
                        yield dummy_chunk
                    else:
                        yield dummy_chunk[:to_send]
                    bytes_sent += to_send
                    pbar.update(to_send)
        else:
            async def async_chunk_generator():
                with open(local_path, "rb") as f:
                    while chunk := f.read(chunk_size):
                        pbar.update(len(chunk))
                        yield chunk

        await store.put_async(
            path=remote_path,
            file=async_chunk_generator(),
            chunk_size=chunk_size,
            max_concurrency=max_concurrency
        )

    elapsed = time.perf_counter() - start_time
    throughput = (file_size / (1024**2)) / elapsed
    print(f"Upload completed in {elapsed:.2f}s ({throughput:.2f} MB/s)\n")


async def download_file(store: GCSStore, remote_path: str, local_path: Path, chunk_size: int, max_concurrency: int, verbose: bool = False):
    """
    Asynchronously downloads a remote GCS object in parallel using concurrent range requests.
    If DOWNLOAD_TO_MEMORY_ONLY is enabled, bytes are downloaded to memory buffers and 
    instantly discarded to benchmark pure pipeline network throughput.
    """
    meta = await store.head_async(remote_path)
    
    # Extract file size dynamically from metadata
    if isinstance(meta, dict):
        file_size = int(meta["size"])
    else:
        try:
            file_size = int(meta.size)
        except AttributeError:
            file_size = int(meta["size"])
    
    start_time = time.perf_counter()

    if verbose:
        file_size_mib = file_size / (1024**2)
        chunk_size_mib = chunk_size / (1024**2)
        total_chunks = file_size / chunk_size
        dest_display = "(Memory)" if DOWNLOAD_TO_MEMORY_ONLY else str(local_path)
        print(f"local file={dest_display}, remote file=gs://{BUCKET_NAME}/{remote_path}, file size={file_size_mib:.1f} MiB")
        print(f"worker count={max_concurrency}, chunk size={chunk_size_mib:.2f} MiB, total chunks={total_chunks:.1f}")
    else:
        if DOWNLOAD_TO_MEMORY_ONLY:
            print(f"Downloading: {remote_path} ({file_size / (1024**2):.2f} MB)...")
        else:
            # Pre-allocate container file on target disk
            local_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Downloading: {remote_path} ({file_size / (1024**2):.2f} MB) in parallel ranges...")

            with open(local_path, "wb") as f:
                f.truncate(file_size)

    chunks = []
    offset = 0
    while offset < file_size:
        length = min(chunk_size, file_size - offset)
        chunks.append((offset, length))
        offset += length

    sem = asyncio.Semaphore(max_concurrency)
    use_pwrite = hasattr(os, "pwrite") and not DOWNLOAD_TO_MEMORY_ONLY
    
    if DOWNLOAD_TO_MEMORY_ONLY:
        fd = None
        f_out = None
        write_lock = None
    elif use_pwrite:
        fd = os.open(local_path, os.O_WRONLY)
        write_lock = None
        f_out = None
    else:
        fd = None
        f_out = open(local_path, "r+b")
        write_lock = asyncio.Lock()

    total_received_bytes = 0
    tracker_lock = asyncio.Lock()

    try:
        with tqdm(total=file_size, unit="B", unit_scale=True, unit_divisor=1024, desc="Downloading") as pbar:
            
            async def download_chunk(start_offset, chunk_len):
                nonlocal total_received_bytes
                async with sem:
                    # Request targeted range via HTTP Range header
                    chunk_bytes = await store.get_range_async(
                        remote_path, 
                        start=start_offset, 
                        length=chunk_len
                    )
                    
                    if not DOWNLOAD_TO_MEMORY_ONLY:
                        if use_pwrite:
                            os.pwrite(fd, chunk_bytes, start_offset)
                        else:
                            async with write_lock:
                                f_out.seek(start_offset)
                                f_out.write(chunk_bytes)
                    
                    async with tracker_lock:
                        total_received_bytes += len(chunk_bytes)
                    
                    pbar.update(len(chunk_bytes))

            tasks = [download_chunk(o, l) for o, l in chunks]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check if any tasks encountered errors
            for result in results:
                if isinstance(result, Exception):
                    raise result

    finally:
        if fd is not None:
            os.close(fd)
        if f_out is not None:
            f_out.close()

    elapsed = time.perf_counter() - start_time
    throughput = (file_size / (1024**2)) / elapsed
    
    print(f"Verification: Successfully transferred {total_received_bytes / (1024**2):.2f} MB of {file_size / (1024**2):.2f} MB expected.")
    print(f"Download completed in {elapsed:.2f}s ({throughput:.2f} MB/s)\n")


async def main():
    parser = argparse.ArgumentParser(
        description="GCS Benchmark Single Operations",
        usage="gcs-bench-single.py [-h] (--upload | --download) [--chunksize CHUNKSIZE] [--workers WORKERS] [--verbose]"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--upload", action="store_true", help="Run upload benchmark")
    group.add_argument("--download", action="store_true", help="Run download benchmark")
    
    parser.add_argument("--chunksize", type=int, default=16, help="Chunk size in MB (default: 16)")
    parser.add_argument("--workers", type=int, default=64, help="Number of concurrent connections/workers (default: 64)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    gcs_store = GCSStore(bucket=BUCKET_NAME)
    chunk_size_bytes = args.chunksize * 1024 * 1024

    try:
        if args.upload:
            await upload_file(
                store=gcs_store,
                local_path=SOURCE_FILE,
                remote_path=REMOTE_KEY,
                chunk_size=chunk_size_bytes,
                max_concurrency=args.workers,
                upload_from_memory_gib=UPLOAD_FROM_MEMORY_ONLY_GIB,
                verbose=args.verbose
            )
        elif args.download:
            await download_file(
                store=gcs_store,
                remote_path=REMOTE_KEY,
                local_path=DEST_FILE,
                chunk_size=chunk_size_bytes,
                max_concurrency=args.workers,
                verbose=args.verbose
            )
    except Exception as e:
        print(f"Execution failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())