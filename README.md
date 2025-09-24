# Disk Fill & Verify (Python) chatgpt x-)

CLI utility to **saturate a target drive with one large file**, show **live progress/ETA**, then **read it back** to verify **bit-perfect integrity** via **SHA-256**. Reports precise write/read **time** and **throughput**, and deletes the test file by default (configurable with `--keep`). Cross-platform and optimized for high throughput with a producer/consumer pipeline.

## Why

* Practical stress test for external SSDs/HDDs, USB enclosures, SD cards, RAID/LVM volumes.
* Detect silent corruption, flaky cables/controllers, and throttling under sustained load.
* Get realistic throughput numbers using **random data** (avoids transparent compression).

## Features

* **Live progress:** percent, MiB written/read, current rate, ETA.
* **Integrity check:** compares SHA-256 from write vs read (bit-for-bit validation).
* **High performance:** large default block (1 GiB) + adjustable queue depth to overlap CPU/I/O.
* **Sequential I/O hints on Windows** when available (`O_SEQUENTIAL`, `O_BINARY`).
* **Safety:** forced flush to disk (`fsync`) on write completion.
* **Portable:** works on Windows, macOS, and Linux.

## Quick Start

```bash
# Fill E:\, leave 512 MiB free by default, then verify and delete the file
python disk_fill_verify.py E:\

# More aggressive settings and keep the test file
python disk_fill_verify.py D:\ --chunk-mib 2048 --reserve-mib 1024 --queue-depth 4 --keep
```

## CLI

```text
usage: disk_fill_verify.py target_path [--filename NAME]
                                     [--chunk-mib N]
                                     [--reserve-mib N]
                                     [--queue-depth N]
                                     [--keep]
```

| Option          | Default              | Description                                              |
| --------------- | -------------------- | -------------------------------------------------------- |
| `target_path`   | — (required)         | Destination directory or root (e.g., `E:\`, `/mnt/ssd`). |
| `--filename`    | `disk_fill_test.bin` | Output file name.                                        |
| `--chunk-mib`   | `1024`               | I/O block size in MiB (bigger = fewer syscalls).         |
| `--reserve-mib` | `512`                | MiB to leave free on the target volume.                  |
| `--queue-depth` | `3`                  | Buffers in flight; increases CPU/I/O overlap.            |
| `--keep`        | off                  | Keep the test file instead of deleting it.               |

## How it works

* A background producer generates random bytes (`os.urandom`) in big chunks.
* The writer consumes those buffers, streams them sequentially to disk, and updates a running SHA-256.
* After flushing to disk, the file is read back in the same chunk size, hashing the content again.
* If sizes and hashes match, integrity is **OK**; otherwise, it reports **FAILED**.

## Example Output

```
=== Test configuration ===
Destination:  E:\disk_fill_test.bin
Planned file size: 470,686 MiB
I/O block:    1024 MiB
Reserve:      512 MiB
Queue depth:  3
==================================
Write:   42.13% | 198,057/470,686 MiB | 890.12 MiB/s | ETA 5m 12.34s
...
--- Write completed ---
Written: 470,686.48 MiB in 8m 49.20s (889.52 MiB/s)
SHA-256 (write):  <hash>
Read :  100.00% | 470,686/470,686 MiB | 1,120.45 MiB/s | ETA 0m 00.00s
--- Read completed ---
Read:   470,686.48 MiB in 7m 00.10s (1,120.45 MiB/s)
SHA-256 (read):   <hash>

✅ INTEGRITY OK

=== Summary ===
File size:              470,686.48 MiB
Write time:             8m 49.20s  | 889.52 MiB/s
Read time:              7m 00.10s  | 1,120.45 MiB/s
Integrity result:       OK
```

## Tips

* Use a **large** `--chunk-mib` (e.g., 1024–4096) for fast SSDs.
* Increase `--queue-depth` if CPU isn’t saturated and the device is fast.
* Keep some reserve (`--reserve-mib`) so the system and other apps don’t run out of space.
* On ultra-fast NVMe over USB, test different cables/ports to spot controller or PSU issues.

---

Use at your own risk on the **correct target path**. This tool writes a very large file and can fill the device if `--reserve-mib` is set too low.
