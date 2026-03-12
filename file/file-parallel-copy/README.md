# file-parallel-copy

## Purpose
`pcp.sh` is a bash utility designed to parallelize large file copy operations to characterize write performance of various storage targets. In contrast to a simple single-threaded `cp` command, this utility can copy data in a parallelized manner. It uses `parallel` and `dd` to slice a file and copy portions of it concurrently, enabling higher throughputs. Source file for copy can be provided, or a random seed file will be generated in memory (`/dev/shm`) to thwart storage level deduplication and compression without taxing the CPU to generate all of it. Keep in mind that when copying from a source file if data is not in Linux buffer cache already that data will be read from a source potentially impacting the performance of the copy job. This software is designed for performance testing and not production use. NO WARRANTY IMPLIED OR GIVEN.

## Features
The utility provides:
* Parallel Execution: Distributes copy tasks across multiple processes.
* Direct I/O: Uses `oflag=direct` for writes and `iflag=direct` for file reads to bypass host buffer cache.
* Real or Simulated Data: Supports both physical file copying (--if) and random data generation (--size-gib).
* Precise Data Handling: Manages "trailing bytes" to ensure the destination file matches the source size exactly, down to the byte.
* Configurable Task Count: Fine-tune performance by adjusting the number of concurrent tasks and the amount of data processed per task.

## How it Works
1. Environment Check: Verifies all dependencies are installed.
1. Planning: Logically Splits the file into chunks.
1. Parallelization: Launches GNU Parallel, which spawns multiple dd instances.
1. Seek & Skip: Each dd instance uses skip to read from a specific source offset and seek to write to the corresponding destination offset.
1. Remainder Handling: The final task handles any remaining bytes that didn't fit into the 1 MiB block size using a byte-level copy.
1. Statistics: Logs total copy time and throughput.

## Prerequisites
The script requires the following utilities to be installed on your system:
* GNU Parallel: The core engine for parallelization.
* dd: The standard data copying utility.
* awk: Used for floating-point math and formatting.
* bc: Used for high-precision duration calculations.

## Install software

1. Install required software:
    ```
    sudo apt-get update
    sudo apt-get install -y parallel coreutils gawk bc git bmon
    ```
1. Clone git repo and change into directory
    ```
    git clone https://github.com/dutchiechris/storage.git
    cd storage/file/file-parallel-copy
    ```

## Usage

Help text:
```
./pcp.sh --help
Usage: ./pcp.sh [--if=<input_file> | --size-gib=<GiB>] --of=<output_file> [options]

Mandatory:
  --of=<path>              Path to the destination file.
  --if=<path>              Path to source file (mutually exclusive with --size-gib).
  OR
  --size-gib=<GiB>         Generate random data of this size in GiB (mutually exclusive with --if).

Options:
  --processes=<count>      Number of active parallel processes (defaults to CPU count: 288).
  --task-size-mib=<MiB>    Amount of data (in MiB) per task (defaults to file size / processes).
```

### Write test using random data
Generates random data to avoid any delays from data reads from a source storage system.
```
./pcp.sh --size-gib=10 --of=/path/to/output.dat
```
This command will cause a 10 GiB `output.dat` file to be created. On a 4 vCPU VM the utility will create 4 `dd` processes that run concurrently where each writes 2.5 GiB to a different offset of `output.dat`.

### Write test using a source file
Useful to test write throughput with a specific file you want to copy. May introduce delays from data reads from a source storage system.
```
./pcp.sh --if=/path/to/input.dat --of=/path/to/output.dat
```
This command will discover the filesize of `input.dat` and then copy it to `output.dat`. On a 4 vCPU VM, with a 8 GiB `input.dat` file, the utility will create 4 `dd` processes that run concurrently where each writes 2 GiB to a different offset of `output.dat`.

### Write test with a specific task size using random data
```
./pcp.sh --size-gib=10 --of=/path/to/output.dat --task-size-mib=256 
```
This command will cause a 10 GiB `output.dat` file to be created. On a 4 vCPU VM the utility will repeately create 4 `dd` processes that run concurrently where each writes 256 MiB to a different offset of `output.dat`. Using a smaller task size might be of interest to test flush or sync behavior.

### Write test with specific task and process count using a source file
```
./pcp.sh --if=/path/to/input.dat --of=/path/to/output.dat --task-size-mib=256 --processes=8 
```
This command will discover the filesize of `input.dat` and then copy it to `output.dat`. With a 24 GiB `input.dat` file, the utility will repeatedly create 8 `dd` processes that run concurrently, where each writes 256 MiB to a different offset of `output.dat`. If the VM had 16 vCPUs, you will use at most half of the CPU resources.

## Example outputs
> TIP: Run the bandwidth monitoring `bmon` in a second terminal to view realtime network usage.

Test writes with random data:
```
# ./pcp.sh --size-gib=10 --of=/flex/file.dat
Generating 320 MiB random seed file in /dev/shm...
-------------------------------------
Mode:             Random Data Generation
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    32
Task Size (MiB):  320
Total Tasks:      32
-------------------------------------
Transfer Complete.
Duration:      8.46022s
Avg Speed:     1210.37 MiB/s
-------------------------------------
```

Test writes with a source file that you created on a ramdisk:
```
# sudo mkdir /ramdisk
# sudo mount -t tmpfs -o size=20G tmpfs /ramdisk
# sudo chmod 777 /ramdisk

# ./pcp.sh --of=/ramdisk/file.dat --size-gib=10
Generating 320 MiB random seed file in /dev/shm...
-------------------------------------
Mode:             Random Data Generation
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    32
Task Size (MiB):  320
Total Tasks:      32
-------------------------------------
Transfer Complete.
Duration:      4.00912s
Avg Speed:     2554.18 MiB/s
-------------------------------------

# ./pcp.sh --if=/ramdisk/file.dat --of=/flex/file.dat
-------------------------------------
Mode:             File Copy
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    32
Task Size (MiB):  320
Total Tasks:      32
-------------------------------------
Transfer Complete.
Duration:      8.08675s
Avg Speed:     1266.27 MiB/s
-------------------------------------
````

Test writes with a smaller process count:
```
# ./pcp.sh --of=/flex/file.dat --size-gib=10 --processes=5
Generating 1024 MiB random seed file in /dev/shm...
-------------------------------------
Mode:             Random Data Generation
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    5
Task Size (MiB):  1024
Total Tasks:      10
-------------------------------------
Transfer Complete.
Duration:      14.3093s
Avg Speed:     715.62 MiB/s
-------------------------------------
````

Test writes with a smaller task size:
```
 ./pcp.sh --of=/flex/file.dat --size-gib=10 --task-size-mib=64
Generating 64 MiB random seed file in /dev/shm...
-------------------------------------
Mode:             Random Data Generation
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    32
Task Size (MiB):  64
Total Tasks:      160
-------------------------------------
Transfer Complete.
Duration:      8.09568s
Avg Speed:     1264.87 MiB/s
-------------------------------------
````

Test single threaded writes:
```
# ./pcp.sh  --of=/flex/file.dat --size-gib=10 --processes=1
Generating 1024 MiB random seed file in /dev/shm...
-------------------------------------
Mode:             Random Data Generation
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    1
Task Size (MiB):  1024
Total Tasks:      10
-------------------------------------
Transfer Complete.
Duration:      47.6523s
Avg Speed:     214.89 MiB/s
-------------------------------------
```

Test parallel reads to `/dev/null`:
```
# ./pcp.sh  --if=/flex/file.dat --of=/dev/null
-------------------------------------
Mode:             File Copy
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    32
Task Size (MiB):  320
Total Tasks:      32
-------------------------------------
Transfer Complete.
Duration:      3.25319s
Avg Speed:     3147.68 MiB/s
-------------------------------------
```

Test single threaded reads to `/dev/null`:
```
# ./pcp.sh  --if=/flex/file.dat --of=/dev/null --processes=1
-------------------------------------
Mode:             File Copy
Total Size:       10737418240 bytes (10.00 GiB)
Process Count:    1
Task Size (MiB):  10240
Total Tasks:      1
-------------------------------------
Transfer Complete.
Duration:      23.0056s
Avg Speed:     445.11 MiB/s
```

While loop to verify consistency across test runs:
```
# while true; do ./pcp.sh --size-gib=16 --of=/flex/file.dat | grep Avg; done
Avg Speed:     1256.52 MiB/s
Avg Speed:     1265.69 MiB/s
Avg Speed:     1248.40 MiB/s
Avg Speed:     1254.31 MiB/s
Avg Speed:     1241.76 MiB/s
```