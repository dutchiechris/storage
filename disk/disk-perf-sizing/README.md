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
usage: disk-perf-sizing.py [-h] --project PROJECT_ID [--zone ZONE] [--days DAYS] [--max] [--csv-output CSV_OUTPUT]
                           [--disk-filter-file DISK_FILTER_FILE | --disk-filter-regex DISK_FILTER_REGEX]

Summarize Google Cloud Disk IOPs and Throughput.

options:
  -h, --help            show this help message and exit
  --project PROJECT_ID  Your Google Cloud Project ID
  --zone ZONE           Restrict collection and output to a specific Zone (e.g., us-central1-a)
  --days DAYS           Full days (0-24h) prior to today to include. 0=Today only. (default: 42)
  --max                 Use max_* metrics for peak estimation instead of average rates.
  --csv-output CSV_OUTPUT
                        Save the summary output to a CSV file.
  --disk-filter-file DISK_FILTER_FILE
                        File containing list of device names (one per line) to analyze.
  --disk-filter-regex DISK_FILTER_REGEX
                        Regex pattern to match device names to analyze.
```

Example collection of metrics for project `my-project`, zone `europe-west4-a` where disk name matches `sg1-` with output in CSV format saved to file `sg1.csv`:
```
$ ./disk-perf-sizing.py --project=my-project --zone=europe-west4-a --disk-filter-regex="sg1\-" --csv-output=sg1.csv
>>> Using AVERAGE Rate Mode | Zone: europe-west4-a | (Saving to .cache)
Authenticating with Application Default Credentials...
[IOPS] No cache found. Initializing...
[IOPS] Fetching batch: 2025/10/31 00:00:00 -> 2025/11/07 00:00:00 ...
[IOPS] Fetching batch: 2025/11/07 00:00:00 -> 2025/11/14 00:00:00 ...
[IOPS] Fetching batch: 2025/11/14 00:00:00 -> 2025/11/21 00:00:00 ...
[IOPS] Fetching batch: 2025/11/21 00:00:00 -> 2025/11/28 00:00:00 ...
[IOPS] Fetching batch: 2025/11/28 00:00:00 -> 2025/12/05 00:00:00 ...
[IOPS] Fetching batch: 2025/12/05 00:00:00 -> 2025/12/12 00:00:00 ...
[IOPS] Fetching batch: 2025/12/12 00:00:00 -> 2025/12/12 15:35:00 ...
[IOPS] Initialization complete: 11474 points.
[MiBps] No cache found. Initializing...
[MiBps] Fetching batch: 2025/10/31 00:00:00 -> 2025/11/07 00:00:00 ...
[MiBps] Fetching batch: 2025/11/07 00:00:00 -> 2025/11/14 00:00:00 ...
[MiBps] Fetching batch: 2025/11/14 00:00:00 -> 2025/11/21 00:00:00 ...
[MiBps] Fetching batch: 2025/11/21 00:00:00 -> 2025/11/28 00:00:00 ...
[MiBps] Fetching batch: 2025/11/28 00:00:00 -> 2025/12/05 00:00:00 ...
[MiBps] Fetching batch: 2025/12/05 00:00:00 -> 2025/12/12 00:00:00 ...
[MiBps] Fetching batch: 2025/12/12 00:00:00 -> 2025/12/12 15:35:00 ...
[MiBps] Initialization complete: 11474 points.

Loading cache data for analysis...

Calculating Storage Pool metrics for 5 matching disks...

=================================================================================================================================================
POOL ZONE       | IOPS (Max/p99/p50)        | MiBps (Max/p99/p50)      
-------------------------------------------------------------------------------------------------------------------------------------------------
europe-west4-a  | 75500 / 73700 / 55600     | 1630 / 1510 / 920        

=================================================================================================================================================
ZONE            | INSTANCE ID                    | DEVICE NAME          | IOPS (Max/p99/p50)        | MiBps (Max/p99/p50)      
------------------------------------------------------------------------------------------------------------------------------------------------- 
europe-west4-a  | 8853480501397099998            | sg1-1                | 40100 / 33200 / 12400     | 750 / 390 / 90           
europe-west4-a  | 8853480501397099998            | sg1-2                | 34500 / 28300 / 12500     | 450 / 400 / 90           
europe-west4-a  | 8853480501397099998            | sg1-3                | 29600 / 28100 / 12600     | 460 / 420 / 90           
europe-west4-a  | 8853480501397099998            | sg1-4                | 38600 / 36100 / 13300     | 980 / 460 / 120          
europe-west4-a  | 8853480501397099998            | sg1-5                | 9300 / 8400 / 3400        | 1190 / 1060 / 460        
-------------------------------------------------------------------------------------------------------------------------------------------------
OUTPUT LOGIC (avg):
1. Data is based on the average value per 1 min sample.
2. DISKS: Statistics for each disk over the day count requested.
3. POOLS: Statistics for all matching disks, aligned by timestamp, over the day count requested.
4. IOPS rounded up to nearest 100. Throughput rounded up to nearest 10 MiB/s.
```

In the disk list above, disk 1sg1-1 had a max minute average of 40,100 IOPS and 750 MiB/s, while the p99 minute average was 33,200 IOPS (20% less) and 390 MiB/s (52% less). You can set Hyperdisk provisioned performance conservatively at the Max, or Max + buffer %, to reduce the chance of disk throttling. Alternatively, for cost savings, you can choose a lower value with the expectation that during peak periods the disk will be throttled. When a disk is throttled, requests experience higher latency.

In the pool list above, the `europe-west4-a` zone pool had a max minute average (i.e. the aligned sum of individual disks) of 75,500 IOPS and 1,630 MiB/s. You can set the Hyperdisk provisioned performance to Max + buffer % to provide sufficient performance for the five disks listed. For example, if you apply a 20% buffer to the pool, you would set it to 90,000 IOPS and 2,000 MiB/s. Because a pool offers 5x performance overprovisioning, you can allocate up to 450,000 IOPS and 10,000 MiB/s across the disks within it. When using a pool, you would likely set higher individual disk limits (e.g., Max + a larger buffer %) than in a standalone configuration, further reducing the chance of disk throttling.

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
## Collection Recommendations

1. For large projects that use multiple zones use the `--zone ZONE` option to reduce work per script invocation. If you experience long run time of the script, or Cloud Monitoring timeouts, analyze on a zone by zone basis.
1. Analyze 42 days of history or less. Cloud Montioring metrics are summarized from 1 to 10 min granularity after 6 weeks. Specifying more than 42 days may smooth out minute or multi-minute usage spikes decreasing overall Max and p99 statistics.