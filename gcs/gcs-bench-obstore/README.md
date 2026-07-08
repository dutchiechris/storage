# gcs-bench-obstore

## Purpose
Script for testing upload and download performance of large files using [obstore](https://github.com/developmentseed/obstore).

## Setup instructions
These instructions assume a basic knowledge of Google Cloud. They can be executed from Google Cloud Shell and a temporary performance testing VM.

### Create test VM
1. Set variables for subsequent commands
    ```
    PROJECT=your-project-name
    BUCKET=your-bucket-name
    REGION=europe-west4
    ZONE=europe-west4-b
    ```
1. Create GCE SA
    ```
    gcloud iam service-accounts create gce-sa --display-name="GCE default SA" --project=$PROJECT
    ```
1. Create storage bucket
    ```
    gcloud storage buckets create gs://$BUCKET --location=$REGION --project=$PROJECT --soft-delete-duration=0
    ```
1. Grant GCE Service Account (SA) access to bucket
    ```
    gcloud storage buckets add-iam-policy-binding gs://$BUCKET --project=$PROJECT \
    --member=serviceAccount:gce-sa@$PROJECT.iam.gserviceaccount.com --role=roles/storage.objectUser
    ```
1. Create a VM (consider network limits for a given machine-type). Ensure that scopes include storage read/write and the GCE SA has access to the bucket.
    ```
    gcloud compute instances create gcs-client \
    --machine-type=c3-highmem-4 \
    --project=$PROJECT \
    --zone=$ZONE \
    --shielded-secure-boot \
    --service-account=gce-sa@$PROJECT.iam.gserviceaccount.com \
    --network-interface=stack-type=IPV4_ONLY,subnet=default,no-address,nic-type=GVNIC \
    --create-disk=auto-delete=yes,boot=yes,mode=rw,size=10,image-project=debian-cloud,image-family=debian-12,type=projects/$PROJECT/zones/$ZONE/diskTypes/pd-balanced \
    --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/devstorage.read_write	
    ```
### Configure test VM

1. SSH into the VM ([configure IAP](https://cloud.google.com/compute/docs/connect/ssh-using-iap) if required)
    ```
    gcloud compute ssh gcs-client --zone $ZONE --tunnel-through-iap --project=$PROJECT
    ```
1. Install required software
    ```
    sudo apt update
    sudo apt install git python3-pip python3-venv -y
    ```
1. Clone git repo and change into directory
    ```
    git clone https://github.com/dutchiechris/storage.git
    cd storage/gcs/gcs-bench-obstore
    ```
1. Configure Python environment
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
1. Create a ramdisk (optional) as a source and destination for transfers
    ```
    sudo mkdir /ramdisk
    sudo mount -t tmpfs -o size=25G tmpfs /ramdisk
    sudo chmod 777 /ramdisk
    ```
1. Create a test file (optional, can also use MEMORY_ONLY env variables)
    ```
    # Create a 1g test file with dummy data
    openssl rand -out /ramdisk/1g.bin 1073741824

    # For larger tests. make it 20G (or larger, just make sure you have enough RAM, and sized the ramdisk larger)
    for i in {1..35}; do cat /ramdisk/1g.bin >> /ramdisk/obstore.bin ; done
    ```
1. Create a `.env` file in the same directory as the script which includes the following:
    ```
    BUCKET_NAME="<YOUR_BUCKET_NAME>"
    REMOTE_KEY=obstore.bin
    LOCAL_SOURCE_FILE=/ramdisk/obstore.bin
    LOCAL_DEST_FILE=/ramdisk/obstore.bin
    DOWNLOAD_TO_MEMORY_ONLY=FALSE
    UPLOAD_FROM_MEMORY_ONLY_GIB=0
    ```

   Description for each field is:
   ```
    BUCKET_NAME="<YOUR_BUCKET_NAME>"         << GCS Bucket name for tests (no gs://) prefix
    REMOTE_KEY=obstore.bin                   << Object name to save in the BUCKET_NAME
    LOCAL_SOURCE_FILE=/ramdisk/obstore.bin   << Local file as source for upload
    LOCAL_DEST_FILE=/ramdisk/obstore.bin     << Local file as destination for download
    DOWNLOAD_TO_MEMORY_ONLY=FALSE            << For downloads, save to memory instead of LOCAL_DEST_FILE
    UPLOAD_FROM_MEMORY_ONLY_GIB=0            << For uploads, create upload stream as x GiB instead of LOCAL_SOURCE_FILE
   ```

### Run tests!

Basic usage is:
```
$ python3 gcs-bench-obstore.py
usage: gcs-bench-single.py [-h] (--upload | --download) [--chunksize CHUNKSIZE] [--workers WORKERS] [--verbose]
gcs-bench-obstore.py: error: one of the arguments --upload --download is required
```

Required parameters:
```
  --upload             # Run upload benchmark
  --download           # Run download benchmark
```
Optional parameters:
```
  --chunksize CHUNKSIZE Chunk size in MB (default: 16)
  --workers WORKERS     Number of concurrent connections/workers (default: 64)
  --verbose             Enable verbose logging
```

Example to upload:
```
# python3 gcs-bench-obstore.py --upload --verbose 
local file=(Memory), remote file=gs://20220715-europe-west4/obstore.bin, file size=20480.0 MiB
worker count=64, chunk size=16.00 MiB, total chunks=1280.0
Uploading: 100%|███████████████████████████████████████████████████████████████████████| 20.0G/20.0G [00:08<00:00, 2.61GB/s]
Upload completed in 8.23s (2489.83 MB/s)
```

Example to download:
```
# python3 gcs-bench-obstore.py --download --verbose 
local file=(Memory), remote file=gs://20220715-europe-west4/obstore.bin, file size=20480.0 MiB
worker count=64, chunk size=16.00 MiB, total chunks=1280.0
Downloading: 100%|█████████████████████████████████████████████████████████████████████| 20.0G/20.0G [00:05<00:00, 4.06GB/s]
Verification: Successfully transferred 20480.00 MB of 20480.00 MB expected.
Download completed in 5.29s (3869.08 MB/s)
```
