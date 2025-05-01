#!/usr/bin/env python3
"""
Purpose: Demonstrate AWS S3 SDK and GCS interop 
         following boto3 data integrity updates.
Notes:   boto3 <=1.35.99 is compatible without extra checksum config
         boto3 >=1.36.00 is compatible with extra checksum config
Blog:    tbd
Author:  Chris Madden
"""
import os, boto3
from botocore.exceptions import ClientError
from botocore.client import Config
from boto3.s3.transfer import TransferConfig
from boto3.session import Session

##
## Export variables in your environment!
##
# export AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY"
# export AWS_SECRET_ACCESS_KEY="YOUR_SECRET_KEY"
# export BUCKET_NAME="YOUR_BUCKET_NAME"

ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

# Verify basic input provided
if not all([ACCESS_KEY, SECRET_KEY, BUCKET_NAME]):
    print("Error: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and BUCKET_NAME environment variables must be set.")
    exit(1)

file_data = os.urandom(10 * 1024 * 1024)
remote_object_key = "test.bin"
local_object_key = "/tmp/test.bin"

##
## OPTION 1: Use config parameters:
##  - request_checksum_calculation='when_required'
##  - response_checksum_validation='when_required'
##

print(f"## Using config parameters")
s3 = boto3.client('s3',
                  endpoint_url='https://storage.googleapis.com',
                  aws_access_key_id=ACCESS_KEY,
                  aws_secret_access_key=SECRET_KEY,
                  config=Config(signature_version='s3v4',
                                request_checksum_calculation='when_required',   # REQUIRED WITH GCS
                                response_checksum_validation='when_required' )) # REQUIRED WITH GCS

# Upload object
try:
    r = s3.put_object(Bucket=BUCKET_NAME, Key=remote_object_key, Body=file_data)
    status_code = r['ResponseMetadata']['HTTPStatusCode']
    print(f"PUT: {status_code}: OK")
except ClientError as e:
    if 'Error' in e.response:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"PUT: {e.response['ResponseMetadata']['HTTPStatusCode']}: {error_code}: {error_message}")

# Download object
try:
    os.remove(local_object_key)
    s3.download_file(Bucket=BUCKET_NAME, Key=remote_object_key, Filename=local_object_key)
    print(f"GET: 200 : OK")
except ClientError as e:
    if 'Error' in e.response:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"GET: {e.response['ResponseMetadata']['HTTPStatusCode']}: {error_code}: {error_message}")

##
## OPTION 2: Use environment variables:
##  - AWS_REQUEST_CHECKSUM_CALCULATION='when_required'
##  - AWS_RESPONSE_CHECKSUM_VALIDATIO='when_required'
##

os.environ['AWS_REQUEST_CHECKSUM_CALCULATION'] = 'when_required' # REQUIRED WITH GCS
os.environ['AWS_RESPONSE_CHECKSUM_VALIDATION'] = 'when_required' # REQUIRED WITH GCS

print(f"## Using environment variables")
s3 = boto3.client('s3',
                  endpoint_url='https://storage.googleapis.com',
                  aws_access_key_id=ACCESS_KEY,
                  aws_secret_access_key=SECRET_KEY,
                  config=Config(signature_version='s3v4'))


# Upload object
try:
    r = s3.put_object(Bucket=BUCKET_NAME, Key=remote_object_key)
    status_code = r['ResponseMetadata']['HTTPStatusCode']
    print(f"PUT: {status_code}: OK")
except ClientError as e:
    if 'Error' in e.response:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"PUT: {e.response['ResponseMetadata']['HTTPStatusCode']}: {error_code}: {error_message}")

# Download object
try:
    os.remove(local_object_key)
    s3.download_file(Bucket=BUCKET_NAME, Key=remote_object_key, Filename=local_object_key, Config=TransferConfig(use_threads=True, multipart_threshold=10*1024*1024, max_concurrency=10, multipart_chunksize=10*1024*1024))
    print(f"GET: 200 : OK")
except ClientError as e:
    if 'Error' in e.response:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"GET: {e.response['ResponseMetadata']['HTTPStatusCode']}: {error_code}: {error_message}")
