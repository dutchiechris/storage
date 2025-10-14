#!/bin/bash

# Monitors a GCS bucket operation (like a relocation) by polling its status.
# Displays key progress metrics only when they change.
#
# Blog:    https://www.beginswithdata.com/2025/10/14/gcs-buckets-relocate/
# Author:  Chris Madden
#
# Usage: ./gcs_relocate_monitor.sh BUCKET_NAME OPERATION_ID

# Check for required dependencies
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' is not installed. Please install it to run this script."
    exit 1
fi

# Check for required arguments
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 BUCKET_NAME OPERATION_ID"
    echo "Example: $0 mybucket CiQ3NmViZWJhZC03NDIwLTQyYWUtYmRlMy0wNDM1NmVhZGIwMjkQBQ"
    exit 1
fi

BUCKET_NAME=$1
OPERATION_ID=$2
INTERVAL=5

OPERATION_PATH="projects/_/buckets/${BUCKET_NAME}/operations/${OPERATION_ID}"

cleanup() {
    echo ""
    echo "------------------------------------------------------------------------------------------------------------------------"
    echo "To view the raw output of this operation, run:"
    echo "gcloud storage operations describe ${OPERATION_PATH}"
    exit 1
}

# Trap Ctrl+C to run cleanup function
trap cleanup SIGINT

echo "Monitoring GCS operation: ${OPERATION_PATH}"
echo "Polling every ${INTERVAL} seconds and output only on changes"

COUNTER=0
LAST_UPDATE_TIME=""

while true; do
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S %Z")

    # Run the gcloud command and parse the JSON output
    STATUS_JSON=$(gcloud storage operations describe "${OPERATION_PATH}" --format=json 2>/dev/null)

    if [ $? -ne 0 ]; then
        echo "Error: Failed to get operation status. Check your bucket name and operation ID."
        exit 1
    fi

    # Extract required status fields
    DONE=$(echo "$STATUS_JSON" | jq -r '.done')
    RELOCATION_STATE=$(echo "$STATUS_JSON" | jq -r '.metadata.relocationState // "N/A"')
    FINALIZATION_STATE=$(echo "$STATUS_JSON" | jq -r '.metadata.finalizationState // "N/A"')
    
    # Extract timestamps
    CREATE_TIME_RAW=$(echo "$STATUS_JSON" | jq -r '.metadata.commonMetadata.createTime')
    UPDATE_TIME_RAW=$(echo "$STATUS_JSON" | jq -r '.metadata.commonMetadata.updateTime')

    # Skip printing if updateTime has not changed
    if [ "$UPDATE_TIME_RAW" == "$LAST_UPDATE_TIME" ]; then
        sleep "$INTERVAL"
        continue
    fi
    LAST_UPDATE_TIME="$UPDATE_TIME_RAW"

    # Convert ISO timestamps to Unix epoch seconds and calculate difference
    CREATE_TIME_EPOCH=$(date -d "${CREATE_TIME_RAW}" +%s 2>/dev/null)
    UPDATE_TIME_EPOCH=$(date -d "${UPDATE_TIME_RAW}" +%s 2>/dev/null)
    
    if [ -z "$CREATE_TIME_EPOCH" ] || [ -z "$UPDATE_TIME_EPOCH" ]; then
        ELAPSED_FORMATTED="N/A"
    else
        ELAPSED_SECONDS=$((UPDATE_TIME_EPOCH - CREATE_TIME_EPOCH))
        HOURS=$((ELAPSED_SECONDS / 3600))
        MINUTES=$(( (ELAPSED_SECONDS % 3600) / 60 ))
        SECONDS=$((ELAPSED_SECONDS % 60))
        ELAPSED_FORMATTED=$(printf "%02d:%02d:%02d" "$HOURS" "$MINUTES" "$SECONDS")
    fi

    # Progress fields
    OVERALL_PROGRESS_PERCENT=$(echo "$STATUS_JSON" | jq -r '.metadata.commonMetadata.progressPercent // "N/A"')
    PROGRESS_BYTES_PERCENT=$(echo "$STATUS_JSON" | jq -r '.metadata.progress.byteProgressPercent // "N/A"')
    PROGRESS_OBJECTS_PERCENT=$(echo "$STATUS_JSON" | jq -r '.metadata.progress.objectProgressPercent // "N/A"')
    DISCOVERED_OBJECTS=$(echo "$STATUS_JSON" | jq -r '.metadata.progress.discoveredObjectCount // "N/A"')
    REMAINING_OBJECTS=$(echo "$STATUS_JSON" | jq -r '.metadata.progress.remainingObjectCount // "N/A"')

    # Calculate and format Objects column: % (done/total)
    if [[ "$DISCOVERED_OBJECTS" == "N/A" || "$REMAINING_OBJECTS" == "N/A" ]]; then
        OBJECTS_COLUMN=$(printf "%-5s(N/A/%s)" "${PROGRESS_OBJECTS_PERCENT}%" "${DISCOVERED_OBJECTS}")
    else
        DONE_OBJECTS=$((DISCOVERED_OBJECTS - REMAINING_OBJECTS))
        if (( DONE_OBJECTS < 0 )); then DONE_OBJECTS=0; fi
        OBJECTS_COLUMN=$(printf "%-5s(%s/%s)" "${PROGRESS_OBJECTS_PERCENT}%" "${DONE_OBJECTS}" "${DISCOVERED_OBJECTS}")
    fi

    # Calculate and format Capacity column (in GiB): % (done/total)
    DISCOVERED_GIB=$(echo "$STATUS_JSON" | jq -r 'if .metadata.progress.discoveredBytes != null then (.metadata.progress.discoveredBytes | tonumber) / 1073741824 else "N/A" end')
    DONE_GIB=$(echo "$STATUS_JSON" | jq -r 'if .metadata.progress.discoveredBytes != null and .metadata.progress.remainingBytes != null then ((.metadata.progress.discoveredBytes | tonumber) - (.metadata.progress.remainingBytes | tonumber)) / 1073741824 else "N/A" end')
    
    if [[ "$DONE_GIB" == "N/A" || "$DISCOVERED_GIB" == "N/A" ]]; then
        CAPACITY_COLUMN=$(printf "%-5s(N/A/%s)" "${PROGRESS_BYTES_PERCENT}%" "${DISCOVERED_GIB}")
    else
        printf -v DONE_FORMATTED "%.2f" "$DONE_GIB"
        printf -v DISCOVERED_FORMATTED "%.2f" "$DISCOVERED_GIB"
        CAPACITY_COLUMN=$(printf "%-5s(%s/%s)" "${PROGRESS_BYTES_PERCENT}%" "$DONE_FORMATTED" "$DISCOVERED_FORMATTED")
    fi
    
    # Print header rows every 20 lines
    if [ $((COUNTER % 20)) -eq 0 ]; then
        printf "________________________________________________________________________________________________________________________\n"
        printf "%-40s|%-25s|%-5s|%-24s|%-24s\n" \
            "Timestamp (Elapsed)" "Status" "Job" "Objects" "Capacity GiB"
        printf "%-40s|%-25s|%-5s|%-24s|%-24s\n" \
            "" "" "%" "%    (done/total)" "%    (done/total)"
    fi

    # Format data row
    JOB_PERCENT_FORMATTED=$(printf "%s%%" "${OVERALL_PROGRESS_PERCENT}")
    STATUS_DETAIL="${FINALIZATION_STATE} (${RELOCATION_STATE})"
    ELAPSED_DETAIL="${TIMESTAMP} (${ELAPSED_FORMATTED})"

    # Simplified formatting: Apply all padding in the main printf format string.
    # This avoids creating intermediate arguments that could start with '-' and be misinterpreted as options.
    printf "%-40s|%-25s|%-5s|%-24s|%-24s\n" \
        "${ELAPSED_DETAIL}" \
        "${STATUS_DETAIL}" \
        "${JOB_PERCENT_FORMATTED}" \
        "${OBJECTS_COLUMN}" \
        "${CAPACITY_COLUMN}"

    # Break the loop if the operation is complete
    if [ "$DONE" == "true" ]; then
        echo "________________________________________________________________________________________________________________________"

        echo "Operation completed successfully."
        break
    fi

    sleep "$INTERVAL"
    COUNTER=$((COUNTER + 1))
done

echo "To view the raw output of this operation, run:"
echo "gcloud storage operations describe ${OPERATION_PATH}"
