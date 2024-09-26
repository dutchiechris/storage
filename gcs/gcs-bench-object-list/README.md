# gcs-bench-object-list

## Purpose
Script for testing object list performance of a bucket using the GCP Python storage libraries. Choose from one of three locations (uses a public dataset bucket) or set a specific bucket. Adjust the page size and max results to compare performance for various client and region locations to optimize your use case.

## Setup instructions
These instructions assume a basic knowledge of Google Cloud. They can be executed from Google Cloud Shell and a temporary performance testing VM in the desired region.

### Create test VM
1. Set variables for subsequent commands
    ```
    PROJECT=your-project-name
    REGION=europe-west4
    ZONE=europe-west4-b
    ```
1. Create a VM. Ensure that scopes include storage read.
    ```
    gcloud compute instances create gcs-client \
    --machine-type=n2-highmem-4 \
    --project=$PROJECT \
    --zone=$ZONE \
    --shielded-secure-boot \
    --network-interface=stack-type=IPV4_ONLY,subnet=default,nic-type=GVNIC \
    --create-disk=auto-delete=yes,boot=yes,mode=rw,size=10,image-project=debian-cloud,image-family=debian-12,type=projects/$PROJECT/zones/$ZONE/diskTypes/pd-balanced \
    --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/devstorage.read_only
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

## Run tests!

Help text:
```
$ python3 gcs-bench-object-list.py --help
usage: gcs-bench-object-list.py [-h] [--pagesize PAGESIZE] [--maxresults MAXRESULTS] [--location {us,eu,us-central1} | --bucket BUCKET] [--verbose]

Test performance of the GCS objects.list API

options:
  -h, --help            show this help message and exit
  --pagesize PAGESIZE   Page size for object listing (default: 1000)
  --maxresults MAXRESULTS
                        Max results for object listing (default: 25000)
  --verbose             Verbose output

Bucket or Location:
  Choose either a location (uses a public dataset bucket) or a specific bucket.

  --location {us,eu,us-central1}
                        Public bucket location (default: us)
  --bucket BUCKET       Specific bucket name
```

Test object list with defaults of 25,000 objects with a page size of 1,000 in the us multi-region:
```
$ python3 gcs-bench-object-list.py
Listed 25,000 objects in 1.98s with a list object throughput of 12,648 objects/s
```

Test object list of 10,000 objects with a page size of 5,000 in the eu multi-region with verbose details:
```
python3 gcs-bench-object-list.py --location=eu --maxresults=10000 --pagesize=5000 --verbose
Using bucket gcp-public-data-sentinel-2 in location EU
Response 1 in 0.28s, Items in response: 5000
Response 2 in 0.35s, Items in response: 5000
Listed 10,000 objects in 0.63s with a list object throughput of 15,751 objects/s
```

Example to test object list of up to 10,000 objects from a bucket named `josefiene` with verbose details:
```
$ python3 gcs-bench-object-list.py --bucket=josefiene --maxresults=10000 --verbose
Using bucket josefiene in ['EUROPE-WEST1', 'EUROPE-WEST4']
Response 1 in 0.03s, Items in response: 35
Listed 35 objects in 0.03s with a list object throughput of 1,076 objects/s
```


### Bring your own bucket (optional)

If you bring your own bucket your [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/provide-credentials-adc) will be used to access the bucket. You can grant your VM's service account acceess to the bucket using the role `roles/storage.legacyBucketReader `.

If access is missing you will get an error like `Error listing objects: 403 GET https://storage.googleapis.com/storage/v1/b/josefiene?projection=noAcl&prettyPrint=false: 937694258238-compute@developer.gserviceaccount.com does not have storage.buckets.get access to the Google Cloud Storage bucket. Permission 'storage.buckets.get' denied on resource (or it may not exist).`

From that output you will see the service account that needs access, in my case: `937694258238-compute@developer.gserviceaccount.com`

Grant access to the service account:
```
gcloud storage buckets add-iam-policy-binding gs://BUCKET --project=PROJECT \
--member=serviceAccount:YOURSERVICEACCOUNT@developer.gserviceaccount.com \
--role=roles/storage.legacyBucketReader
```

