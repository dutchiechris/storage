# gcs-relocate-monitor

## Purpose
Script for watching the status of a long-running GCS bucket relocate operation. Created while investigating the GCS Bucket Relocate feature and authoring [Moving GCS Buckets with Bucket Relocation](https://www.beginswithdata.com/2025/10/14/gcs-buckets-relocate/) blog post.

## Usage instructions

1. Start a bucket relocate
```
# BUCKET=bucket-on-the-move
gcloud storage buckets relocate gs://$BUCKET --location=europe-west1 
WARNING: The bucket gs://bucket-on-the-move is in EUROPE-WEST4.
WARNING: 
1. This move will involve write downtime.
2. In-flight resumable uploads not finished before the write downtime will be lost.
3. Bucket tags added to the bucket will result in the relocation being canceled.
4. Please ensure that you have sufficient quota in the destination before performing the relocation.

Please acknowledge that you've read the above warnings and want to relocate the bucket gs://bucket-on-the-move? (Y/n)?
...
selfLink: https://www.googleapis.com/storage/v1/b/bucket-on-the-move/operations/CiQxOTI1OWYyOS00ZjBmLTRjNzEtYjAzMC0wMjZlMGI5ZWI1MDUQBQ
```

1. Copy the operation id from the command output and pass it as an option to the script found in this directory:
``` 
# ./gcs-relocate-monitor.sh $BUCKET CiQxOTI1OWYyOS00ZjBmLTRjNzEtYjAzMC0wMjZlMGI5ZWI1MDUQBQ
Monitoring GCS operation: projects/_/buckets/bucket-on-the-move-5/operations/CiQxOTI1OWYyOS00ZjBmLTRjNzEtYjAzMC0wMjZlMGI5ZWI1MDUQBQ
Polling every 5 seconds and output only on changes
________________________________________________________________________________________________________________________
Timestamp (Elapsed)                     |Status                   |Job  |Objects                 |Capacity GiB            
                                        |                         |%    |%    (done/total)       |%    (done/total)       
2025-10-10 10:31:22 UTC (00:03:04)      |WAITING_ON_SYNC (SYNCING)|0%   |0%   (0/0)              |0%   (0.00/0.00) 
2025-10-10 10:47:08 UTC (00:18:08)      |READY (SYNCING)          |0%   |0%   (0/100000)         |0%   (0.00/155.83)      
2025-10-10 10:57:12 UTC (00:28:12)      |READY (SYNCING)          |41%  |41%  (41000/100000)     |41%  (63.89/155.83)      
2025-10-10 11:02:10 UTC (00:34:50)      |READY (SYNCING)          |99%  |100% (100000/100000)    |100% (155.83/155.83)
2025-10-10 11:03:25 UTC (00:36:06)      |RUNNING (FINALIZING)     |99%  |100% (100000/100000)    |100% (155.83/155.83)    
2025-10-10 11:59:23 UTC (01:31:59)      |FINALIZED (SUCCEEDED)    |100% |100% (100000/100000)    |100% (155.83/155.83)        
```


