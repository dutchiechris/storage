# disk-perf-sizing

## Purpose
A script designed to analyze historical disk I/O performance (IOPs and throughput) from Cloud Monitoring. It generates essential summary statistics used to accurately determine and set the optimal provisioned performance for Google Cloud Hyperdisks and Advanced Hyperdisk Storage Pools. Datapoints are also saved in `.cache` and `.cache-max` subdirectories to speed up analysis, reduce API calls, and allow other analytics to be performed.

## Setup instructions
These instructions assume a basic knowledge of Google Cloud. They can be executed from Google Cloud Shell.

### Authenication
1.  The script uses **Application Default Credentials (ADC)** with the Cloud Monitoring API. Ensure your environment is authenticated using one of the methods described at [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials).

1. The authenticated account requires the `roles/monitoring.viewer` (Monitoring Viewer) IAM role on the target project to query time series data.

### Install software

1. Install required software (not required if using `Cloud Shell`)
    ```
    sudo apt update
    sudo apt install git python3-pip python3-venv -y
    ```
1. Clone git repo and change into directory
    ```
    git clone https://github.com/dutchiechris/storage.git
    cd storage/disk/disk-perf-sizing
    ```
1. Configure Python environment
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

## Collect and analyze data

Help text:
```
$ ./disk-perf-sizing.py --help
usage: disk-perf-sizing.py [-h] --project PROJECT_ID [--days DAYS] [--max] [--csv-output CSV_OUTPUT] [--disk-filter-file DISK_FILTER_FILE | --disk-filter-regex DISK_FILTER_REGEX]

Summarize Google Cloud Disk IOPs and Throughput to aid in determining appropriate provisioned performance for Hyperdisks and Advanced Hyperdisk Storage Pools.

options:
  -h, --help            show this help message and exit
  --project PROJECT_ID  Your Google Cloud Project ID
  --days DAYS           Full days (0-24h) prior to today to include. 0=Today only. (default: 42)
  --max                 Use max_* metrics for peak estimation instead of average rates.
  --csv-output CSV_OUTPUT
                        Save the summary output to a CSV file.
  --disk-filter-file DISK_FILTER_FILE
                        File containing list of device names (one per line) to analyze.
  --disk-filter-regex DISK_FILTER_REGEX
                        Regex pattern to match device names to analyze.
```

Example collection of metrics for project `my-project` from the last `4` days where disk name matches `sg1-` with output in CSV format saved to file `sg1.csv`:
```
$ ./disk-perf-sizing.py --project=my-project --days=4 --disk-filter-regex="sg1\-" --csv-output=sg1.csv
>>> Using AVERAGE Rate Mode (Saving to .cache)
Authenticating with Application Default Credentials...
[IOPS] No cache found. Initializing...
[IOPS] Fetching batch: 2025/12/04 00:00:00 -> 2025/12/08 14:55:00 ...
[IOPS] Initialization complete: 2826 points.
[MiBps] No cache found. Initializing...
[MiBps] Fetching batch: 2025/12/04 00:00:00 -> 2025/12/08 14:55:00 ...
[MiBps] Initialization complete: 2826 points.

Loading cache data for analysis...

Calculating Storage Pool metrics for 5 matching disks...

=================================================================================================================================================
POOL ZONE       | IOPS (Max/p99/p50)        | MiBps (Max/p99/p50)      
-------------------------------------------------------------------------------------------------------------------------------------------------
europe-west4-a  | 75500 / 73700 / 56300     | 1630 / 1510 / 940        

=================================================================================================================================================
ZONE            | INSTANCE ID                    | DEVICE NAME          | IOPS (Max/p99/p50)        | MiBps (Max/p99/p50)      
-------------------------------------------------------------------------------------------------------------------------------------------------
europe-west4-a  | 8853480501397099998            | sg1-1                | 40100 / 33200 / 12400     | 750 / 390 / 90           
europe-west4-a  | 8853480501397099998            | sg1-2                | 34500 / 28300 / 12500     | 450 / 400 / 90           
europe-west4-a  | 8853480501397099998            | sg1-3                | 29600 / 28100 / 12600     | 460 / 420 / 90           
europe-west4-a  | 8853480501397099998            | sg1-4                | 38600 / 36100 / 13300     | 980 / 460 / 120          
europe-west4-a  | 8853480501397099998            | sg1-5                | 9300 / 8400 / 3400        | 1190 / 1060 / 460        
-------------------------------------------------------------------------------------------------------------------------------------------------
POOL LOGIC:
1. POOL stats are calculated by summing aligned timestamps across all matched disks.
2. Individual stats show the contribution of each disk to the pool.
AVERAGE LOGIC:
1. Data is based on per 1 min samples.
2. IOPS rounded up to nearest 100. Throughput rounded up to nearest 10 MiB/s.

Writing summary to CSV: sg1.csv
```

CSV output contents:
```
$ cat sg1.csv 
Type,Zone,Instance_ID,Device_Name,IOPS_Max,IOPS_P99,IOPS_P50,MiBps_Max,MiBps_P99,MiBps_P50
POOL,europe-west4-a,,,75500,73700,56300,1630,1510,940
DISK,europe-west4-a,8853480501397099998,sg1-1,40100,33200,12400,750,390,90
DISK,europe-west4-a,8853480501397099998,sg1-2,34500,28300,12500,450,400,90
DISK,europe-west4-a,8853480501397099998,sg1-3,29600,28100,12600,460,420,90
DISK,europe-west4-a,8853480501397099998,sg1-4,38600,36100,13300,980,460,120
DISK,europe-west4-a,8853480501397099998,sg1-5,9300,8400,3400,1190,1060,460
```
