#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# https://github.com/therealdreg/disk_fill_test
# David Reguera Garcia (Dreg) - Dreg@rootkit.es - X @therealdreg
# CLI tool that fills a target drive with a single large file, showing live progress/ETA, then reads it back to verify data integrity via SHA-256. Reports precise write/read times and throughput, and deletes the test file by default

import argparse, hashlib, os, shutil, sys, time, queue, threading, math

DEFAULT_CHUNK_MIB   = 1024
DEFAULT_RESERVE_MIB = 512
DEFAULT_QUEUE_DEPTH = 3

def mib(b): return b / (1024**2)

def human_rate(b, s):
    if s <= 0: return "∞ MiB/s"
    return f"{mib(b)/s:,.2f} MiB/s"

def human_time(seconds):
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m)}m {s:,.2f}s"

def print_progress(prefix, done, total, t0):
    elapsed = time.perf_counter() - t0
    pct = (done / total) * 100 if total else 100.0
    eta = (total - done) * (elapsed / done) if done else 0.0
    line = (f"{prefix}: {pct:6.2f}% | {mib(done):,.0f}/{mib(total):,.0f} MiB | "
            f"{human_rate(done, elapsed)} | ETA {human_time(eta)}")
    print("\r" + line, end="", flush=True)

def open_sequential_write(path):
    flags = os.O_RDWR | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):     flags |= os.O_BINARY
    if hasattr(os, "O_SEQUENTIAL"): flags |= os.O_SEQUENTIAL
    fd = os.open(path, flags, 0o666)
    return os.fdopen(fd, "wb", buffering=0)

def open_sequential_read(path):
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):     flags |= os.O_BINARY
    if hasattr(os, "O_SEQUENTIAL"): flags |= os.O_SEQUENTIAL
    fd = os.open(path, flags)
    return os.fdopen(fd, "rb", buffering=0)

def producer_urandom(q, total_bytes, chunk_size, stop_evt):
    produced = 0
    try:
        while produced < total_bytes and not stop_evt.is_set():
            this_chunk = min(chunk_size, total_bytes - produced)
            buf = os.urandom(this_chunk)
            q.put(buf)
            produced += this_chunk
    finally:
        q.put(None)

def main():
    print("https://github.com/therealdreg/disk_fill_test")
    print("David Reguera Garcia (Dreg) - Dreg@rootkit.es - X @therealdreg")
    print("CLI tool that fills a target drive with a single large file, showing live progress/ETA, then reads it back to verify data integrity via SHA-256. Reports precise write/read times and throughput, and deletes the test file by default")
    print("-")

    ap = argparse.ArgumentParser(description="Fill a drive with a large file, with progress/ETA and SHA-256 verification.")
    ap.add_argument("target_path", help=r"Destination path (e.g., E:\)")
    ap.add_argument("--filename", default="disk_fill_test.bin")
    ap.add_argument("--chunk-mib", type=int, default=DEFAULT_CHUNK_MIB)
    ap.add_argument("--reserve-mib", type=int, default=DEFAULT_RESERVE_MIB)
    ap.add_argument("--queue-depth", type=int, default=DEFAULT_QUEUE_DEPTH,
                    help="Buffers in flight (higher = more CPU/IO overlap)")
    ap.add_argument("--keep", action="store_true", help="Do not delete the file at the end.")
    args = ap.parse_args()

    target_path = os.path.abspath(args.target_path)
    if not os.path.isdir(target_path):
        print(f"ERROR: Invalid directory: {target_path}"); sys.exit(2)

    total, used, free = shutil.disk_usage(target_path)
    reserve_bytes = args.reserve_mib * 1024**2
    if free <= reserve_bytes + 16 * 1024**2:
        print("ERROR: Not enough free space for the test."); sys.exit(2)

    file_size  = free - reserve_bytes
    chunk_size = args.chunk_mib * 1024**2
    file_path  = os.path.join(target_path, args.filename)

    print("=== Test configuration ===")
    print(f"Destination:  {file_path}")
    print(f"Planned file size: {mib(file_size):,.2f} MiB")
    print(f"I/O block:    {args.chunk_mib} MiB")
    print(f"Reserve:      {args.reserve_mib} MiB")
    print(f"Queue depth:  {args.queue_depth}")
    print("==================================")

    sha_w = hashlib.sha256()
    bytes_written = 0
    t0 = time.perf_counter()
    q  = queue.Queue(maxsize=max(2, args.queue_depth))
    stop_evt = threading.Event()
    prod = threading.Thread(target=producer_urandom, args=(q, file_size, chunk_size, stop_evt), daemon=True)
    prod.start()

    try:
        with open_sequential_write(file_path) as f:
            while True:
                buf = q.get()
                if buf is None: break
                sha_w.update(buf)
                written = f.write(buf)
                if written != len(buf):
                    raise IOError("Incomplete write.")
                bytes_written += written
                print_progress("Write", bytes_written, file_size, t0)
            f.flush()
            os.fsync(f.fileno())
        print()
    except Exception as e:
        stop_evt.set()
        print(f"\nERROR during write: {e}")
        try: os.remove(file_path)
        except Exception: pass
        sys.exit(1)

    t1 = time.perf_counter()
    write_seconds = t1 - t0
    write_hash = sha_w.hexdigest()
    print("--- Write completed ---")
    print(f"Written: {mib(bytes_written):,.2f} MiB in {human_time(write_seconds)} ({human_rate(bytes_written, write_seconds)})")
    print(f"SHA-256 (write): {write_hash}")

    sha_r = hashlib.sha256()
    bytes_read = 0
    t2 = time.perf_counter()
    try:
        with open_sequential_read(file_path) as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk: break
                sha_r.update(chunk)
                bytes_read += len(chunk)
                print_progress("Read ", bytes_read, bytes_written, t2)
        print()
    except Exception as e:
        print(f"\nERROR during read: {e}")
        sys.exit(1)

    t3 = time.perf_counter()
    read_seconds = t3 - t2
    read_hash = sha_r.hexdigest()
    print("--- Read completed ---")
    print(f"Read:   {mib(bytes_read):,.2f} MiB in {human_time(read_seconds)} ({human_rate(bytes_read, read_seconds)})")
    print(f"SHA-256 (read):   {read_hash}")

    ok = (bytes_written == bytes_read) and (write_hash == read_hash)
    print("\n✅ INTEGRITY OK" if ok else "\n❌ INTEGRITY FAILED")

    if not args.keep:
        try:
            os.remove(file_path)
            print(f"\nTemporary file deleted: {file_path}")
        except Exception as e:
            print(f"\nWarning: could not delete the temporary file: {e}")

    print("\n=== Summary ===")
    print(f"File size:              {mib(bytes_written):,.2f} MiB")
    print(f"Write time:             {human_time(write_seconds)}  | {human_rate(bytes_written, write_seconds)}")
    print(f"Read time:              {human_time(read_seconds)}    | {human_rate(bytes_read, read_seconds)}")
    print(f"Integrity result:       {'OK' if ok else 'ERROR'}")

if __name__ == "__main__":
    main()
