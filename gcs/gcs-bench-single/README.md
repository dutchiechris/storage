# gcs-bench-single

## Purpose
Script for testing upload and download performance of large files.  You can pick the transfer tool (Python SDK, `gcloud storage cp`, or Python aws boto3) and parallelization parameters. Created while evaluating GCS performance as part of the [High throughput file transfers with Google Cloud Storage (GCS)](https://www.beginswithdata.com/2024/02/01/google-cloud-storage-max-throughput/) blog post.

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
    gcloud storage buckets create gs://$BUCKET --location=$REGION --project=$PROJECT
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
    cd storage/gcs/gcs-bench-single
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
1. Create a test file
    ```
    # Create a 1g test file with dummy data
    openssl rand -out /ramdisk/file.1g 1073741824

    # For larger tests. make it 20G (or larger, just make sure you have enough RAM, and sized the ramdisk larger)
    for i in {1..20}; do cat /ramdisk/file.1g >> /ramdisk/file.20g ; done
    ```
1. Create a `.env` file in the same directory as the script which includes the following (ACCESS_KEY and SECRET_KEY are only needed for aws boto3 tests):
    ```
    BUCKET_NAME="your-bucket-name"
    REMOTE_FILENAME="remote-file"
    LOCAL_FILENAME="/ramdisk/file.1g"
    ACCESS_KEY="GOOG1EC2AXZNOWAYAXZNOWAYAXZNOWAYAXZNOWAYAXZNOWAYAXZNOWAYAXZ4U"
    SECRET_KEY="k6O62k6O62k6O62k6O62k6O62k6O62k6O62k6O62"
    ```

### Run tests!

Run tests using: \
```
$ python3 gcs-bench-single.py
usage: gcs-bench-single.py [-h] (--upload | --download) (--sdk | --gcloud | --aws) [--serial] [--null] [--chunksize CHUNKSIZE] [--workers WORKERS] [--verbose]
gcs-bench-single.py: error: one of the arguments --upload --download is required
```

Required parameters:
```
--upload | --download #Direction of transfer
--sdk | --gcloud | --aws #Transfer tool
--serial # Force serialized transfers
```
Optional parameters:
```
--chunksize <# MB> #Set to the number of MBs per chunk to upload or download (or omit to use default)
--workers <#> #Set to the worker count (or omit to use default)
--verbose #Verbose logging
```

* Example to upload using the sdk with 24 workers:
```
(.venv) sa_115019974160331027606@gcs-client-snow:~/storage/gcs/gcs-bench-single$ python3 gcs-bench-single.py --upload --sdk --verbose --workers=24
local file=/ramdisk/file.20g, remote file=gs://2024050-snow/remote-file, file size=20480.0 MiB
worker count=24, chunk size=25.00 MiB, total chunks=819.2
Took 17.04 seconds. Average throughput: 1201.75 MiB/s
```

* Example to download using gcloud with defaults:
```
(.venv) sa_115019974160331027606@gcs-client-snow:~/storage/gcs/gcs-bench-single$ python3 gcs-bench-single.py --download --gcloud --verbose
local file=/ramdisk/file.20g, remote file=gs://2024050-snow/remote-file, file size=20480.0 MiB
CompletedProcess(args=['gcloud', 'storage', 'cp', 'gs://2024050-snow/remote-file', '/ramdisk/file.20g'], returncode=0, stdout=b'', stderr=b'Copying gs://2024050-snow/remote-file to file:///ramdisk/file.20g\n  \n................................................................................................\n\nAverage throughput: 1.1GiB/s\n')
Took 20.16 seconds. Average throughput: 1015.95 MiB/s
```