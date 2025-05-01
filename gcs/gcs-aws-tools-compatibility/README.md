# gcs-aws-tools-compatibility

## Purpose
Scripts for testing s3 sdk and aws cli interop with Google Cloud Storage (gcs), especially as it relates to default data integrity checks in AWS provided s3 tools. More on those updates is described in the AWS blog ["Introducing default data integrity protections for new objects in Amazon S3"](https://aws.amazon.com/blogs/aws/introducing-default-data-integrity-protections-for-new-objects-in-amazon-s3/). 

For these tools to interoperate with GCS two settings need to be made, either via environemnt variables or aws cli or boto client config:

Environment variables:
```
AWS_REQUEST_CHECKSUM_CALCULATION='when_required'
AWS_RESPONSE_CHECKSUM_VALIDATION='when_required'
```

boto client config or aws cli profiles:
```
request_checksum_calculation='when_required'
response_checksum_validation='when_required'
```

See more [here](https://docs.aws.amazon.com/cli/v1/userguide/cli-configure-envvars.html).

## Setup instructions
These instructions assume a basic knowledge of Google Cloud. They can be executed from Google Cloud Shell or a temporary performance testing VM. They assume you have created a test bucket with access to a Service Account and have [created HMAC keys](https://cloud.google.com/storage/docs/authentication/managing-hmackeys) for it.

1. Install required software
    ```
    sudo apt update
    sudo apt install git python3-pip python3-venv -y
    ```
1. Clone git repo and change into directory
    ```
    git clone https://github.com/dutchiechris/storage.git
    cd storage/gcs/gcs-aws-tools-compatibility
    ```
1. Configure Python environment (if intereted in boto3 python interop):
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
1. Export environment variables:
    ```
    export AWS_ACCESS_KEY_ID="<YOUR GCS HMAC ACCESS KEY>"
    export AWS_SECRET_ACCESS_KEY="<YOUR GCS HMAC SECRET KEY>"
    export BUCKET_NAME="<YOUR BUCKET NAME>
    ```

### Run tests!

Basic usage and output for the aws cli test is:
```
(.venv)$ ./gcs-aws-boto3.py
## Using config parameters
PUT: 200: OK
GET: 200 : OK
## Using environment variables
PUT: 200: OK
GET: 200 : OK
```

Basic usage and output for the aws cli test is:
```
$ ./gcs-aws-cli.sh
10+0 records in
10+0 records out
10485760 bytes (10 MB, 10 MiB) copied, 0.0377093 s, 278 MB/s
1+0 records in
1+0 records out
1048576 bytes (1.0 MB, 1.0 MiB) copied, 0.00324147 s, 323 MB/s
##################################################################################################
Running commands with version: 2.22.35
##################################################################################################
Running command: s3 cp /tmp_host/file.small s3://20231221-boto/file.small
upload: ../tmp_host/file.small to s3://20231221-boto/file.small  
Running command: s3 cp /tmp_host/file.big s3://20231221-boto/file.big
upload: ../tmp_host/file.big to s3://20231221-boto/file.big       
Running command: s3 cp s3://20231221-boto/file.small /tmp_host/foo
download: s3://20231221-boto/file.small to ../tmp_host/foo       
Running command: s3 cp s3://20231221-boto/file.big /tmp_host/foo
download: s3://20231221-boto/file.big to ../tmp_host/foo          
##################################################################################################
Running commands with version: 2.23.4
##################################################################################################
Running command: s3 cp /tmp_host/file.small s3://20231221-boto/file.small
upload failed: ../tmp_host/file.small to s3://20231221-boto/file.small An error occurred (SignatureDoesNotMatch) when calling the PutObject operation: Invalid argument.
Running command: s3 cp /tmp_host/file.big s3://20231221-boto/file.big
upload failed: ../tmp_host/file.big to s3://20231221-boto/file.big An error occurred (SignatureDoesNotMatch) when calling the UploadPart operation: Invalid argument.
Running command: s3 cp s3://20231221-boto/file.small /tmp_host/foo
download: s3://20231221-boto/file.small to ../tmp_host/foo       
Running command: s3 cp s3://20231221-boto/file.big /tmp_host/foo
download failed: s3://20231221-boto/file.big to ../tmp_host/foo Expected checksum x4Vs7w== did not match calculated checksum: u4E0XQ==
##################################################################################################
Running commands with version: 2.23.5
##################################################################################################
Running command: s3 cp /tmp_host/file.small s3://20231221-boto/file.small
upload: ../tmp_host/file.small to s3://20231221-boto/file.small  
Running command: s3 cp /tmp_host/file.big s3://20231221-boto/file.big
upload: ../tmp_host/file.big to s3://20231221-boto/file.big       
Running command: s3 cp s3://20231221-boto/file.small /tmp_host/foo
download: s3://20231221-boto/file.small to ../tmp_host/foo       
Running command: s3 cp s3://20231221-boto/file.big /tmp_host/foo
download: s3://20231221-boto/file.big to ../tmp_host/foo          
All commands finished. Check /tmp/output.log
```
