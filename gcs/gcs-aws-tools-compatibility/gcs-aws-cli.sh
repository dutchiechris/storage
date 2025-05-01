#!/bin/bash
# Purpose: Demonstrate AWS cli s3 and GCS interop
#          following boto3 data integrity updates.
# Notes:   awscli <=2.22.35 is compatible without extra checksum config
#          awscli >=2.23.0 <=2.23.4 is incompatible
#          awscli >=2.23.5 is compatible with checksum config
# Blog:    tbd
# Author:  Chris Madden

## Export variables in your environment!
##
# export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
# export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
# export BUCKET_NAME="YOUR_BUCKET_NAME"

set -e

# Define the awscli versions you want to test
versions=("2.22.35" "2.23.4" "2.23.5")

# Check if environment variable are set
if [ -z "${AWS_ACCESS_KEY_ID}" ]; then
  echo "environment variable AWS_ACCESS_KEY_ID not set" >&2
  exit 1
fi
if [ -z "${AWS_SECRET_ACCESS_KEY}" ]; then
  echo "environment variable AWS_SECRET_ACCESS_KEY not set" >&2
  exit 1
fi
if [ -z "${BUCKET_NAME}" ]; then
  echo "environment variable BUCKET_NAME not set" >&2
  exit 1
fi

# Debug or not (empty string for no debug)
debug=""
# debug="--debug"

# Array of s3 cp commands to test.
s3_commands=(
  "s3 cp /tmp_host/file.small s3://${BUCKET_NAME}/file.small"
  "s3 cp /tmp_host/file.big s3://${BUCKET_NAME}/file.big"
  "s3 cp s3://${BUCKET_NAME}/file.small /tmp_host/foo"
  "s3 cp s3://${BUCKET_NAME}/file.big /tmp_host/foo"
)

dd if=/dev/random of=/tmp/file.big bs=1M count=10
dd if=/dev/random of=/tmp/file.small bs=1M count=1

# --- Outer loop: Iterate over versions ---
for version in "${versions[@]}"; do
  echo "##################################################################################################" | tee -a /tmp/output.log
  echo "Running commands with version: $version" | tee -a /tmp/output.log
  echo "##################################################################################################" | tee -a /tmp/output.log

  # --- Inner loop: Iterate over commands ---
  for cmd in "${s3_commands[@]}"; do
    echo "Running command: $cmd" | tee -a /tmp/output.log

    sudo docker run --rm \
      -e AWS_REQUEST_CHECKSUM_CALCULATION=when_required \
      -e AWS_RESPONSE_CHECKSUM_VALIDATION=when_required \
      -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
      -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
      -v /tmp:/tmp_host \
      -v ~/.aws:/root/.aws \
      -v "$(pwd)":/aws \
      "amazon/aws-cli:$version" \
      $cmd \
      --endpoint-url https://storage.googleapis.com $debug \
      2>&1 | tee -a /tmp/output.log

    if [ $? -ne 0 ]; then
      echo "Error: Command failed. See /tmp/output.log"
    fi
  done
done

echo "All commands finished. Check /tmp/output.log"
