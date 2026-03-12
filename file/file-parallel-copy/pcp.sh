#!/bin/bash
# Purpose: Parallelize large file copy operations to characterize storage system performance
#          for these workloads.
# Author:  Chris Madden

# --- Default Values ---
# PROCESS_COUNT: Number of concurrent processes (defaults to CPU cores)
PROCESS_COUNT=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
TASK_SIZE_MIB=""
SOURCE=""
DEST=""
SIZE_GB=""
BS=$((1024 * 1024)) # 1 MiB base block size

# --- Usage Function ---
usage() {
    echo "Usage: $0 [--if=<input_file> | --size-gib=<GiB>] --of=<output_file> [options]"
    echo ""
    echo "Mandatory:"
    echo "  --of=<path>              Path to the destination file."
    echo "  --if=<path>              Path to source file (mutually exclusive with --size-gib)."
    echo "  OR"
    echo "  --size-gib=<GiB>         Generate random data of this size in GiB (mutually exclusive with --if)."
    echo ""
    echo "Options:"
    echo "  --processes=<count>      Number of active parallel processes (defaults to CPU count: $PROCESS_COUNT)."
    echo "  --task-size-mib=<MiB>    Amount of data (in MiB) per task (defaults to file size / processes)."
    exit 1
}

# --- Parse Arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --if=*) SOURCE="${1#*=}"; shift 1 ;;
        --if) SOURCE="$2"; shift 2 ;;
        --of=*) DEST="${1#*=}"; shift 1 ;;
        --of) DEST="$2"; shift 2 ;;
        --size-gib=*) SIZE_GB="${1#*=}"; shift 1 ;;
        --size-gib) SIZE_GB="$2"; shift 2 ;;
        --processes=*) PROCESS_COUNT="${1#*=}"; shift 1 ;;
        --processes) PROCESS_COUNT="$2"; shift 2 ;;
        --task-size-mib=*) TASK_SIZE_MIB="${1#*=}"; shift 1 ;;
        --task-size-mib) TASK_SIZE_MIB="$2"; shift 2 ;;
        *) usage ;;
    esac
done

# --- Validation & Environment Check ---
[[ -z "$DEST" ]] && { echo "Error: --of is mandatory"; usage; }
[[ -n "$SOURCE" && -n "$SIZE_GB" ]] && { echo "Error: Use either --if or --size-gib, not both"; usage; }
[[ -z "$SOURCE" && -z "$SIZE_GB" ]] && { echo "Error: Must provide a source (--if or --size-gib)"; usage; }
[[ "$TASK_SIZE_MIB" == "0" ]] && { echo "Error: --task-size-mib cannot be 0"; exit 1; }

# Dependency Check
for cmd in parallel dd awk bc; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Error: Required command '$cmd' is not installed. Please install it to continue."
        exit 1
    fi
done

# --- Setup Data Source and Size ---
if [[ -n "$SIZE_GB" ]]; then
    TOTAL_SIZE_BYTES=$(awk "BEGIN {printf \"%.0f\", $SIZE_GB * 1024 * 1024 * 1024}")
    SOURCE="/dev/urandom"
    MODE="Random Data Generation"
else
    [[ ! -f "$SOURCE" ]] && { echo "Error: Source file '$SOURCE' not found"; exit 1; }
    TOTAL_SIZE_BYTES=$(stat -c%s "$SOURCE")
    MODE="File Copy"
fi

# Ensure destination directory exists and handle file cleanup
DEST_DIR=$(dirname "$DEST")
if [[ ! -d "$DEST_DIR" ]]; then
    echo "Error: Destination directory '$DEST_DIR' does not exist."
    exit 1
fi
[[ -f "$DEST" ]] && rm -f "$DEST"

# --- Logic Calculations ---
TOTAL_FULL_BLOCKS=$(( TOTAL_SIZE_BYTES / BS ))
TRAILING_BYTES=$(( TOTAL_SIZE_BYTES % BS ))

if [[ -n "$TASK_SIZE_MIB" ]]; then
    BLOCKS_PER_TASK="$TASK_SIZE_MIB"
else
    # Default: Divide total blocks by requested process count
    BLOCKS_PER_TASK=$(( TOTAL_FULL_BLOCKS / PROCESS_COUNT ))
    [[ "$BLOCKS_PER_TASK" -le 0 ]] && BLOCKS_PER_TASK=1
fi

if [[ "$MODE" == "Random Data Generation" ]]; then
    # Cap default BLOCKS_PER_TASK to 1024 (1 GiB) to avoid exhausting /dev/shm
    if [[ -z "$TASK_SIZE_MIB" ]] && [[ "$BLOCKS_PER_TASK" -gt 1024 ]]; then
        BLOCKS_PER_TASK=1024
    fi
fi

if [[ "$TOTAL_FULL_BLOCKS" -gt 0 ]]; then
    TOTAL_TASKS=$(( (TOTAL_FULL_BLOCKS + BLOCKS_PER_TASK - 1) / BLOCKS_PER_TASK ))
else
    TOTAL_TASKS=1
fi

if [[ "$MODE" == "Random Data Generation" ]]; then
    SEED_SIZE_BLOCKS=$BLOCKS_PER_TASK
    [[ "$TOTAL_FULL_BLOCKS" -lt "$SEED_SIZE_BLOCKS" ]] && SEED_SIZE_BLOCKS=$TOTAL_FULL_BLOCKS
    [[ "$SEED_SIZE_BLOCKS" -eq 0 ]] && SEED_SIZE_BLOCKS=1

    SEED_FILE="/dev/shm/parallel_cp_seed_$$"
    echo "Generating ${SEED_SIZE_BLOCKS} MiB random seed file in /dev/shm..."
    if ! dd if=/dev/urandom of="$SEED_FILE" bs=$BS count=$SEED_SIZE_BLOCKS status=none; then
        echo "Error: Failed to allocate random seed in /dev/shm. Check available RAM."
        rm -f "$SEED_FILE"
        exit 1
    fi
    SOURCE="$SEED_FILE"
    trap 'rm -f "$SEED_FILE"' EXIT INT TERM
fi

DISPLAY_GIB=$(awk "BEGIN {printf \"%.2f\", $TOTAL_SIZE_BYTES / 1024 / 1024 / 1024}")

echo "-------------------------------------"
echo "Mode:             $MODE"
echo "Total Size:       $TOTAL_SIZE_BYTES bytes ($DISPLAY_GIB GiB)"
echo "Process Count:    $PROCESS_COUNT"
echo "Task Size (MiB):  $BLOCKS_PER_TASK"
echo "Total Tasks:      $TOTAL_TASKS"
echo "-------------------------------------"

# --- Execution ---
OFLAG_ARG="oflag=direct"
# /dev/null does not support O_DIRECT
[[ "$DEST" == "/dev/null" ]] && OFLAG_ARG=""

IFLAG_ARG="iflag=direct"
# Disable iflag=direct when reading from our temporary seed file in tmpfs
if [[ "$MODE" == "Random Data Generation" ]]; then
    IFLAG_ARG=""
fi

export SOURCE DEST BS BLOCKS_PER_TASK TOTAL_TASKS TOTAL_FULL_BLOCKS TRAILING_BYTES TOTAL_SIZE_BYTES MODE OFLAG_ARG IFLAG_ARG

START_TIME=$(date +%s.%N)
seq 0 $((TOTAL_TASKS - 1)) | parallel -j "$PROCESS_COUNT" --halt now,fail=1 '
    OFFSET_BLOCKS=$(( {1} * BLOCKS_PER_TASK ))
    
    SKIP_ARG=""
    if [ "$MODE" == "File Copy" ]; then
        SKIP_ARG="skip=$OFFSET_BLOCKS"
    fi

    if [ "$OFFSET_BLOCKS" -lt "$TOTAL_FULL_BLOCKS" ]; then
        if [ {1} -eq $((TOTAL_TASKS - 1)) ]; then
            COUNT=$(( TOTAL_FULL_BLOCKS - OFFSET_BLOCKS ))
        else
            COUNT=$BLOCKS_PER_TASK
        fi
        dd if="$SOURCE" of="$DEST" bs=$BS count=$COUNT seek=$OFFSET_BLOCKS $SKIP_ARG conv=notrunc $IFLAG_ARG $OFLAG_ARG status=none
    fi

    if [ {1} -eq $((TOTAL_TASKS - 1)) ] && [ "$TRAILING_BYTES" -gt 0 ]; then
        BYTE_SKIP_ARG=""
        if [ "$MODE" == "File Copy" ]; then
            BYTE_SKIP_ARG="skip=$(( TOTAL_FULL_BLOCKS * BS ))"
        fi
        dd if="$SOURCE" of="$DEST" bs=1 count=$TRAILING_BYTES seek=$(( TOTAL_FULL_BLOCKS * BS )) $BYTE_SKIP_ARG conv=notrunc $IFLAG_ARG $OFLAG_ARG status=none
    fi
'
END_TIME=$(date +%s.%N)

# --- Final Stats ---

DURATION=$(awk "BEGIN {print $END_TIME - $START_TIME}")
[[ $(echo "$DURATION > 0" | bc -l) -eq 0 ]] && DURATION=0.001
AVG_SPEED=$(awk "BEGIN {printf \"%.2f\", ($TOTAL_SIZE_BYTES / 1024 / 1024) / $DURATION}")

echo "Transfer Complete."
echo "Duration:      ${DURATION}s"
echo "Avg Speed:     $AVG_SPEED MiB/s"
echo "-------------------------------------"