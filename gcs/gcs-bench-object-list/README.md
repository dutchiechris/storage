# gcs-bench-single

## Purpose
Script for testing object list performance using the Python storage Libraries against a public GCS bucket. Choose the bucket location (us, eu, or us-central1), page size, and max results. Created to test the impact of different page sizes, especially in cases where the client and bucket are not collocated.

## Setup instructions
These instructions assume a basic knowledge of Google Cloud. They can be executed from Google Cloud Shell and a temporary performance testing VM.

### Create test VM
1. Set variables for subsequent commands
    ```
    PROJECT=your-project-name
    REGION=europe-west4
    ZONE=europe-west4-b
    ```
1. Create a VM . Ensure that scopes include storage read/write and the GCE SA has access to the bucket.
    ```
    gcloud compute instances create gcs-client \
    --machine-type=n2-highmem-4 \
    --project=$PROJECT \
    --zone=$ZONE \
    --shielded-secure-boot \
    --service-account=gce-sa@$PROJECT.iam.gserviceaccount.com \
    --network-interface=stack-type=IPV4_ONLY,subnet=default,nic-type=GVNIC \
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
    cd storage/gcs/gcs-bench-object-list
    ```
1. Configure Python environment
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

### Run tests!

Basic usage is:
```
$ python3 gcs-bench-object-list.py --help
usage: gcs-bench-object-list.py [-h] [--pagesize PAGESIZE] [--maxresults MAXRESULTS] [--location LOCATION] [--verbose]

Test performance of the GCS objects.list API

options:
  -h, --help            show this help message and exit
  --pagesize PAGESIZE   Page size for object listing (default: 1000)
  --maxresults MAXRESULTS
                        Max results for object listing (default: 25000)
  --location LOCATION   Location of bucket, one of: us, eu, us-central1 (default: us)
  --verbose             Verbose output
```

Example to to test object list of 25,000 objects with a page size of 1,000 in the us multi-region:
```
$ python3 gcs-bench-object-list.py
Listed 25,000 objects in 1.98s with a list object throughput of 12,648 objects/s
```

Example to to test object list of 10,000 objects with a page size of 5,000 in the eu multi-region with verbose details:
```
$ python3 gcs-bench-object-list.py --pagesize 5000 --location eu --maxresults=10000 --verbose
Using public bucket gcp-public-data-sentinel-2 in location EU
Response 1 in 1.36s, Items in response: 5000
Response 2 in 1.56s, Items in response: 5000
Listed 10,000 objects in 2.92s with a list object throughput of 3,424 objects/s
```