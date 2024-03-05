"""
Purpose: Script for testing upload and download performance of large files
         using [Python SDK | gcloud storage cp | Python boto3] using parallel
         (incl. various chunk sizes and worker counts) or serialized transfers
Blog:    https://www.beginswithdata.com/2024/02/01/google-cloud-storage-max-throughput/
Author:  Chris Madden
"""
from google.cloud.storage import Client, transfer_manager, blob
from boto3.session import Session
from botocore.client import Config
from boto3.s3.transfer import TransferConfig
from botocore.handlers import set_list_objects_encoding_type_url
from dotenv import load_dotenv
import time, os, argparse, subprocess, boto3


# Parse arguments
parser = argparse.ArgumentParser(description="Test single file upload/downloads")
group_direction = parser.add_argument_group('Transfer Direction', 'Choose to test uploads or downloads.')
ex_group_direction = group_direction.add_mutually_exclusive_group(required=True)
ex_group_direction.add_argument('--upload', action='store_true', help="upload")
ex_group_direction.add_argument('--download', action='store_true', help="download")

group_tool = parser.add_argument_group('Transfer tool', 'Choose the desired copy tool.')
ex_group_tool = group_tool.add_mutually_exclusive_group(required=True)
ex_group_tool.add_argument('--sdk', action='store_true', help="GCS SDK")
ex_group_tool.add_argument('--gcloud', action='store_true', help="GCS gcloud storage")
ex_group_tool.add_argument('--aws', action='store_true', help="AWS boto3")

parser.add_argument('--serial', action='store_true', help='Serialized operations (no MPU or chunking)')
parser.add_argument('--null', action='store_true', help='Download to null instead of tmpfs')
parser.add_argument('--chunksize', type=int, default=25, help='Chunk size in MB (Defaults: SDK=25, gcloud=self-tuned)')
parser.add_argument('--workers', type=int, default=50, help='Number of workers (Defaults: SDK=50, gcloud=self-tuned)')
parser.add_argument('--verbose', action='store_true', help='Verbose output')
args = parser.parse_args()

# Load variables from .env file
load_dotenv() # Get environment variables from .env
BUCKET_NAME     = os.environ.get("BUCKET_NAME")
REMOTE_FILENAME = os.environ.get("REMOTE_FILENAME").lstrip('/')
LOCAL_FILENAME  = os.environ.get("LOCAL_FILENAME")
ACCESS_KEY      = os.environ.get("ACCESS_KEY") # Only required for boto3 tests; others use default application credentials
SECRET_KEY      = os.environ.get("SECRET_KEY") # Only required for boto3 tests; others use default application credentials
CHUNK_SIZE = args.chunksize * 1024 * 1024
WORKER_COUNT = args.workers

# Perform fixed calcs
file_size_mb = os.path.getsize(LOCAL_FILENAME) / (1024 * 1024)
chunk_size_mb = CHUNK_SIZE / (1024 * 1024)
num_chunks = file_size_mb / chunk_size_mb


# Offer downloads to null because writing to a ramdisk takes time
if args.null:
    LOCAL_FILENAME = '/dev/null'

# Create Python resources
if args.sdk:
    storage_client = Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    remote_blob = bucket.blob(REMOTE_FILENAME)

if args.aws:
    session = Session(aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name="europe-west4")
    session.events.unregister('before-parameter-build.s3.ListObjects', set_list_objects_encoding_type_url)
    s3 = session.resource('s3', endpoint_url='https://storage.googleapis.com', config=Config(signature_version='s3v4'))
    tconfig = TransferConfig(multipart_threshold=CHUNK_SIZE, max_concurrency=WORKER_COUNT, multipart_chunksize=CHUNK_SIZE, use_threads=True)

if args.verbose:
    print(f"local file={LOCAL_FILENAME}, remote file=gs://{BUCKET_NAME}/{REMOTE_FILENAME}, file size={file_size_mb} MiB")
    if  (args.sdk or args.aws):
        print(f"worker count={WORKER_COUNT}, chunk size={chunk_size_mb:.2f} MiB, total chunks={num_chunks}")

## Do transfer
start_time = time.time()

# GCS SDK parallel workers
if args.sdk:
    if args.upload:
        if args.serial:
            remote_blob.upload_from_filename(filename=LOCAL_FILENAME)
        else:
            transfer_manager.upload_chunks_concurrently(filename=LOCAL_FILENAME, blob=remote_blob, chunk_size=CHUNK_SIZE, max_workers=WORKER_COUNT)

    if args.download:
        if args.serial:
            remote_blob.download_to_filename(filename=LOCAL_FILENAME)
        else:
            transfer_manager.download_chunks_concurrently(filename=LOCAL_FILENAME, blob=remote_blob, chunk_size=CHUNK_SIZE, max_workers=WORKER_COUNT)

# GCS gcloud storage CLI
# gcloud defaults to cpu_count processes, each with 4 threads
if args.gcloud:
    if args.upload:
        if args.serial:
            os.environ['CLOUDSDK_STORAGE_PARALLEL_COMPOSITE_UPLOAD_ENABLED'] = 'False'
        out = subprocess.run(["gcloud", "storage", "cp", LOCAL_FILENAME, f"gs://{BUCKET_NAME}/{REMOTE_FILENAME}"], capture_output=True)
        if args.verbose:
            print (out)

    if args.download:
        if args.null:
            raise SystemExit('Downloading to null not supported by gcloud.')
        if args.serial:
            os.environ['CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_THRESHOLD'] = '0'
        if args.chunksize != 25:
            os.environ['CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_MAX_COMPONENTS'] = '1000000'
            os.environ['CLOUDSDK_STORAGE_SLICED_OBJECT_DOWNLOAD_COMPONENT_SIZE'] = str(CHUNK_SIZE)
        if args.workers != 50:
            os.environ['CLOUDSDK_STORAGE_PROCESS_COUNT'] = str(args.workers)
            os.environ['CLOUDSDK_STORAGE_THREAD_COUNT'] = "1"
        out = subprocess.run(["gcloud", "storage", "cp", f"gs://{BUCKET_NAME}/{REMOTE_FILENAME}", LOCAL_FILENAME], capture_output=True)
        if args.verbose:
            print (out)

# AWS S3 boto3 parallel workers
if args.aws:
    if args.upload:
        s3.Object(bucket_name=BUCKET_NAME, key=REMOTE_FILENAME).upload_file(Filename=LOCAL_FILENAME, Config=tconfig)
    if args.download:
        s3.Object(bucket_name=BUCKET_NAME, key=REMOTE_FILENAME).download_file(Filename=LOCAL_FILENAME, Config=tconfig)


total_time = time.time() - start_time
transfer_rate = file_size_mb / total_time

print(f"Took {total_time:.2f} seconds. Average throughput: {transfer_rate:.2f} MiB/s")

