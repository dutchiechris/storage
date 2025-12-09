#!/usr/bin/env python3
"""
Purpose: Summarize Google Cloud Disk IOPs and Throughput to aid in determining
         appropriate provisioned performance for Hyperdisks and Advanced
         Hyperdisk Storage Pools.

Permissions: Requires the 'roles/monitoring.viewer' (Monitoring Viewer) IAM role
             on the target project to query time series data.

Blog:    TBD
Author:  Chris Madden
"""
import argparse
import time
import os
import csv
import glob
import math
import re
from datetime import timedelta, datetime, timezone
from collections import defaultdict
from google.cloud import monitoring_v3
from google.api_core.exceptions import GoogleAPIError

# --- CONFIGURATION ---
DEFAULT_CACHE_DIR = ".cache"
MAX_CACHE_DIR = ".cache-max"

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%Y-%m-%d %H:%M:%S"
# API Limit is 100,000 points per series.
# 30 days * 1440 mins = 43,200 points (Safe buffer).
BATCH_DAYS = 30

def ceil_round(value, step):
    """Rounds a value UP to the nearest step (e.g., nearest 100)."""
    if value == 0:
        return 0
    return int(math.ceil(value / step)) * step

def get_project_cache_dir(project_id, cache_root):
    """Returns the cache directory for a specific project, creating it if needed."""
    path = os.path.join(cache_root, project_id)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def get_cache_bounds(project_id, metric_type, cache_root):
    """
    Scans the cache directory to find the oldest and newest timestamps.
    Returns (earliest_ts, latest_ts) or (None, None).
    """
    cache_dir = get_project_cache_dir(project_id, cache_root)
    pattern = os.path.join(cache_dir, f"*_{metric_type}.csv")
    files = sorted(glob.glob(pattern))
    
    if not files:
        return None, None

    earliest_ts = None
    latest_ts = None

    # 1. Find Earliest Timestamp (First line of first file)
    try:
        with open(files[0], 'r') as f:
            header = f.readline()
            first_line = f.readline()
            if first_line:
                parts = first_line.split(',')
                # Check for timestamp in first column
                if parts[0] != "timestamp" and len(parts) >= 1:
                    earliest_ts = datetime.strptime(parts[0], TIME_FMT)
    except Exception as e:
        print(f"Warning: Error reading oldest cache file {files[0]}: {e}")

    # 2. Find Latest Timestamp (Last line of last file)
    try:
        with open(files[-1], 'r') as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                # Back up to find the last newline
                pos = f.tell() - 2
                while pos > 0 and f.read(1) != "\n":
                    pos -= 1
                    f.seek(pos, os.SEEK_SET)
                
                last_line = f.readline()
                if last_line:
                    parts = last_line.split(',')
                    if parts and parts[0] != "timestamp" and len(parts) >= 1:
                        latest_ts = datetime.strptime(parts[0], TIME_FMT)
    except Exception as e:
        print(f"Warning: Error reading newest cache file {files[-1]}: {e}")

    return earliest_ts, latest_ts

def write_to_cache(project_id, metric_type, rows, cache_root):
    """
    Writes new data rows to daily cache files.
    Performs Read-Merge-Sort-Write to ensure files remain chronological
    regardless of whether we are backfilling or forward-filling.
    """
    if not rows:
        return

    cache_dir = get_project_cache_dir(project_id, cache_root)
    
    # Group by Date (UTC)
    rows_by_day = defaultdict(list)
    for row in rows:
        ts = row[0]
        day_str = ts.strftime(DATE_FMT)
        rows_by_day[day_str].append(row)

    for day, new_rows in rows_by_day.items():
        filename = os.path.join(cache_dir, f"{day}_{metric_type}.csv")
        file_exists = os.path.exists(filename)
        
        all_rows = []
        
        # 1. Read existing data if file exists
        if file_exists:
            try:
                with open(filename, 'r') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    for r in reader:
                        try:
                            # Reconstruct tuple: (datetime, zone, device, instance_id, value)
                            r_ts = datetime.strptime(r[0], TIME_FMT)
                            r_val = float(r[4])
                            all_rows.append((r_ts, r[1], r[2], r[3], r_val))
                        except ValueError:
                            continue
            except Exception as e:
                print(f"Warning: Could not read existing cache file {filename}: {e}")

        # 2. Merge with new rows
        # Use a dict keyed by (timestamp, instance_id, device) to deduplicate if ranges overlapped slightly
        data_map = {} 
        for r in all_rows:
            key = (r[0], r[3], r[2]) # ts, instance, device
            data_map[key] = r
        for r in new_rows:
            key = (r[0], r[3], r[2])
            data_map[key] = r
            
        merged_rows = list(data_map.values())
        
        # 3. Sort
        merged_rows.sort(key=lambda x: x[0])

        # 4. Rewrite file
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            # HEADER: instance_id
            writer.writerow(['timestamp', 'zone', 'device_name', 'instance_id', 'value'])
            for r in merged_rows:
                writer.writerow([r[0].strftime(TIME_FMT), r[1], r[2], r[3], r[4]])

def execute_fetch(client, project_id, metric_type, start_dt, end_dt, use_max_metrics=False):
    """
    Helper function to perform the actual API call for a specific time range.
    """
    if start_dt >= end_dt:
        return []

    all_rows = []
    current_start = start_dt
    
    while current_start < end_dt:
        chunk_end = min(current_start + timedelta(days=BATCH_DAYS), end_dt)
        mql_time_fmt = "%Y/%m/%d %H:%M:%S"
        start_str = current_start.strftime(mql_time_fmt)
        end_str = chunk_end.strftime(mql_time_fmt)

        print(f"[{metric_type}] Fetching batch: {start_str} -> {end_str} ...")

        query = ""
        if use_max_metrics:
            if metric_type == 'IOPS':
                query = f"""
                fetch gce_instance
                | {{ 
                    metric 'compute.googleapis.com/instance/disk/max_read_ops_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], max(val())
                    | every 1m
                ; 
                    metric 'compute.googleapis.com/instance/disk/max_write_ops_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], max(val())
                    | every 1m
                }}
                | outer_join 0
                | value cast_double(val(0).or_else(0) + val(1).or_else(0))
                | within d'{start_str}', d'{end_str}'
                """
            else: # MiBps
                conv_factor = 1048576
                query = f"""
                fetch gce_instance
                | {{ 
                    metric 'compute.googleapis.com/instance/disk/max_read_bytes_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], max(val())
                    | every 1m
                ; 
                    metric 'compute.googleapis.com/instance/disk/max_write_bytes_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], max(val())
                    | every 1m
                }}
                | outer_join 0
                | value (val(0).or_else(0) + val(1).or_else(0)) / {conv_factor}
                | within d'{start_str}', d'{end_str}'
                """
        else:
            if metric_type == 'IOPS':
                query = f"""
                fetch gce_instance
                | {{ metric 'compute.googleapis.com/instance/disk/read_ops_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], sum(val())
                  ; metric 'compute.googleapis.com/instance/disk/write_ops_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], sum(val()) }}
                | outer_join 0
                | value val(0) + val(1)
                | align rate(1m)
                | every 1m
                | within d'{start_str}', d'{end_str}'
                """
            else: # MiBps
                query = f"""
                fetch gce_instance
                | {{ metric 'compute.googleapis.com/instance/disk/read_bytes_count'
                    | group_by [resource.zone, resource.instance_id, metric.device_name], sum(val())
                  ; metric 'compute.googleapis.com/instance/disk/write_bytes_count' 
                    | group_by [resource.zone, resource.instance_id, metric.device_name], sum(val()) }}
                | outer_join 0
                | value val(0) + val(1)
                | align rate(1m)
                | scale 'MiBy/s' 
                | every 1m
                | within d'{start_str}', d'{end_str}'
                """

        try:
            iterator = client.query_time_series(
                request={"name": f"projects/{project_id}", "query": query}
            )
            
            for page in iterator.pages:
                label_keys = [d.key for d in page.time_series_descriptor.label_descriptors]
                z_idx = label_keys.index('resource.zone') if 'resource.zone' in label_keys else -1
                i_idx = -1
                if 'resource.instance_id' in label_keys:
                    i_idx = label_keys.index('resource.instance_id')
                d_idx = label_keys.index('metric.device_name') if 'metric.device_name' in label_keys else -1

                for ts_data in page.time_series_data:
                    zone = ts_data.label_values[z_idx].string_value if z_idx != -1 else "unknown"
                    instance_id = ts_data.label_values[i_idx].string_value if i_idx != -1 else "unknown"
                    device = ts_data.label_values[d_idx].string_value if d_idx != -1 else "unknown"

                    points = list(ts_data.point_data)
                    
                    if len(points) > 1:
                        valid_points = points[1:]
                        for p in valid_points:
                            ts = p.time_interval.end_time
                            val = p.values[0].double_value
                            if use_max_metrics and val == 0.0:
                                val = float(p.values[0].int64_value)
                            if ts.tzinfo is not None:
                                ts = ts.replace(tzinfo=None)
                            all_rows.append((ts, zone, device, instance_id, val))

        except GoogleAPIError as e:
            print(f"Error fetching {metric_type} batch: {e}")
            return all_rows

        current_start = chunk_end
    
    return all_rows

def sync_cache(client, project_id, metric_type, lookback_days, cache_root, use_max_metrics=False):
    # Calculate midnight (00:00) of current day
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None).replace(second=0, microsecond=0)
    midnight_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Target start is midnight - lookback_days
    # e.g., if days=1, we go back 24h from today's midnight -> Yesterday 00:00
    target_start_dt = midnight_utc - timedelta(days=lookback_days)
    
    earliest_ts, latest_ts = get_cache_bounds(project_id, metric_type, cache_root)
    
    if earliest_ts and target_start_dt < earliest_ts:
        print(f"[{metric_type}] Detected missing history. Backfilling...")
        rows = execute_fetch(client, project_id, metric_type, target_start_dt, earliest_ts, use_max_metrics)
        write_to_cache(project_id, metric_type, rows, cache_root)
        print(f"[{metric_type}] Backfill complete: {len(rows)} points.")

    if latest_ts:
        forward_start = latest_ts + timedelta(minutes=1)
        if forward_start < now_utc:
            rows = execute_fetch(client, project_id, metric_type, forward_start, now_utc, use_max_metrics)
            write_to_cache(project_id, metric_type, rows, cache_root)
            print(f"[{metric_type}] Forward sync complete: {len(rows)} points.")
        else:
            print(f"[{metric_type}] Cache is up to date (Forward).")
    
    if not earliest_ts:
        print(f"[{metric_type}] No cache found. Initializing...")
        rows = execute_fetch(client, project_id, metric_type, target_start_dt, now_utc, use_max_metrics)
        write_to_cache(project_id, metric_type, rows, cache_root)
        print(f"[{metric_type}] Initialization complete: {len(rows)} points.")

def calculate_stats(values):
    """Returns dict with max, p99, p50 from a list of values."""
    vals = sorted(values)
    count = len(vals)
    if count == 0:
        return {'max': 0, 'p99': 0, 'p50': 0}
    idx_p99 = int(0.99 * (count - 1))
    idx_p50 = int(0.50 * (count - 1))
    return {
        'max': vals[-1],
        'p99': vals[idx_p99],
        'p50': vals[idx_p50]
    }

def load_time_series_data(project_id, lookback_days, cache_root):
    """
    Loads raw time series data from cache into memory.
    Returns: { (inst, dev, zone): {'iops': {ts: val}, 'mibps': {ts: val}} }
    """
    print(f"\nLoading cache data for analysis...")
    
    # Calculate midnight based cutoff
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_time = midnight - timedelta(days=lookback_days)
    
    cutoff_date_str = cutoff_time.strftime(DATE_FMT)
    
    cache_dir = get_project_cache_dir(project_id, cache_root)
    
    # { (inst, dev, zone): {'iops': {ts: val}, 'mibps': {ts: val}} }
    data = defaultdict(lambda: {'iops': {}, 'mibps': {}})

    def process_files(metric_type):
        pattern = os.path.join(cache_dir, f"*_{metric_type}.csv")
        all_files = sorted(glob.glob(pattern))
        target_key = 'iops' if metric_type == 'IOPS' else 'mibps'

        for filepath in all_files:
            filename = os.path.basename(filepath)
            file_date_str = filename.split('_')[0]
            if file_date_str < cutoff_date_str:
                continue
            try:
                with open(filepath, 'r') as f:
                    reader = csv.reader(f)
                    next(reader, None) # header
                    for row in reader:
                        try:
                            ts_str, zone, device, instance_id, val_str = row
                            ts = datetime.strptime(ts_str, TIME_FMT)
                            if ts < cutoff_time:
                                continue
                            val = float(val_str)
                            key = (instance_id, device, zone)
                            data[key][target_key][ts] = val
                        except: continue
            except: continue

    process_files('IOPS')
    process_files('MiBps')
    return data

def main():
    parser = argparse.ArgumentParser(description="Summarize Google Cloud Disk IOPs and Throughput to aid in determining appropriate provisioned performance for Hyperdisks and Advanced Hyperdisk Storage Pools.")
    parser.add_argument("--project", required=True, dest="project_id", help="Your Google Cloud Project ID")
    parser.add_argument("--days", type=int, default=42, help="Full days (0-24h) prior to today to include. 0=Today only. (default: 42)")
    parser.add_argument("--max", action="store_true", help="Use max_* metrics for peak estimation instead of average rates.")
    parser.add_argument("--csv-output", help="Save the summary output to a CSV file.")
    
    # Pool Filtering Arguments (Mutually Exclusive)
    pool_group = parser.add_mutually_exclusive_group()
    pool_group.add_argument("--disk-filter-file", help="File containing list of device names (one per line) to analyze.")
    pool_group.add_argument("--disk-filter-regex", help="Regex pattern to match device names to analyze.")

    args = parser.parse_args()

    # Warning for high lookback periods
    if args.days > 42:
        print("WARNING: You requested > 42 days of history. Google Cloud Monitoring down-samples data older than 6 weeks to 10-minute intervals, reducing fidelity.")
    
    cache_root = MAX_CACHE_DIR if args.max else DEFAULT_CACHE_DIR
    mode_msg = "MAX Metrics" if args.max else "AVERAGE Rate"
    print(f">>> Using {mode_msg} Mode (Saving to {cache_root})")

    # --- AUTHENTICATION ---
    print("Authenticating with Application Default Credentials...")
    client = monitoring_v3.QueryServiceClient()

    # --- SYNC PHASE ---
    sync_cache(client, args.project_id, 'IOPS', args.days, cache_root, use_max_metrics=args.max)
    sync_cache(client, args.project_id, 'MiBps', args.days, cache_root, use_max_metrics=args.max)
    
    # --- LOAD PHASE ---
    # Load all data into memory structure for flexible processing
    raw_data = load_time_series_data(args.project_id, args.days, cache_root)
    
    # --- FILTERING PHASE ---
    filtered_keys = []
    
    if args.disk_filter_file:
        try:
            with open(args.disk_filter_file, 'r') as f:
                target_devices = set()
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#'):
                        target_devices.add(stripped)
            
            for key in raw_data.keys():
                # key = (instance_id, device_name, zone)
                if key[1] in target_devices:
                    filtered_keys.append(key)
        except Exception as e:
            print(f"Error reading disk filter file: {e}")
            return
    elif args.disk_filter_regex:
        try:
            pattern = re.compile(args.disk_filter_regex)
            for key in raw_data.keys():
                if pattern.search(key[1]):
                    filtered_keys.append(key)
        except re.error as e:
            print(f"Invalid regex: {e}")
            return
    else:
        # No filter = process all keys individually
        filtered_keys = list(raw_data.keys())

    if not filtered_keys:
        print("No disks matched the criteria.")
        return

    # --- POOL AGGREGATION LOGIC ---
    # Always calculate pool stats UNLESS in Max mode
    calc_pool_stats = not args.max
    pool_stats_by_zone = {}

    if calc_pool_stats:
        print(f"\nCalculating Storage Pool metrics for {len(filtered_keys)} matching disks...")
        
        # Group filtered keys by Zone
        keys_by_zone = defaultdict(list)
        for key in filtered_keys:
            zone = key[2]
            keys_by_zone[zone].append(key)
        
        for zone, keys in keys_by_zone.items():
            # Create Aggregate Time Series for this zone
            # Collect all unique timestamps involved to ensure we sum correctly
            all_timestamps = set()
            for k in keys:
                all_timestamps.update(raw_data[k]['iops'].keys())
                all_timestamps.update(raw_data[k]['mibps'].keys())
            
            sorted_ts = sorted(list(all_timestamps))
            
            agg_iops_vals = []
            agg_mibps_vals = []
            
            for ts in sorted_ts:
                sum_iops = 0.0
                sum_mibps = 0.0
                for k in keys:
                    sum_iops += raw_data[k]['iops'].get(ts, 0.0)
                    sum_mibps += raw_data[k]['mibps'].get(ts, 0.0)
                
                agg_iops_vals.append(sum_iops)
                agg_mibps_vals.append(sum_mibps)
            
            # Calculate Pool Stats
            pool_stats_by_zone[zone] = {
                'iops': calculate_stats(agg_iops_vals),
                'mibps': calculate_stats(agg_mibps_vals)
            }

    # --- OUTPUT GENERATION ---
    print("\n" + "="*145)
    
    # 1. Pool Summary Output (Only if calc_pool_stats is True)
    if calc_pool_stats and pool_stats_by_zone:
        pool_header = f"{'POOL ZONE':<15} | {'IOPS (Max/p99/p50)':<25} | {'MiBps (Max/p99/p50)':<25}"
        print(pool_header)
        print("-" * 145)
        
        for zone, stats in sorted(pool_stats_by_zone.items()):
            i_max = ceil_round(stats['iops']['max'], 100)
            i_p99 = ceil_round(stats['iops']['p99'], 100)
            i_p50 = ceil_round(stats['iops']['p50'], 100)
            
            m_max = ceil_round(stats['mibps']['max'], 10)
            m_p99 = ceil_round(stats['mibps']['p99'], 10)
            m_p50 = ceil_round(stats['mibps']['p50'], 10)
            
            print(f"{zone:<15} | {f'{i_max} / {i_p99} / {i_p50}':<25} | {f'{m_max} / {m_p99} / {m_p50}':<25}")
        
        print("\n" + "="*145)

    # 2. Individual Disks Output
    header = f"{'ZONE':<15} | {'INSTANCE ID':<30} | {'DEVICE NAME':<20} | {'IOPS (Max/p99/p50)':<25} | {'MiBps (Max/p99/p50)':<25}"
    print(header)
    print("-" * 145)

    # Calculate stats for individual disks in the filtered list
    disk_rows = []
    for key in filtered_keys:
        inst_id, dev_name, zone = key
        i_stats = calculate_stats(list(raw_data[key]['iops'].values()))
        m_stats = calculate_stats(list(raw_data[key]['mibps'].values()))
        
        disk_rows.append({
            'zone': zone, 'inst': inst_id, 'dev': dev_name,
            'iops': i_stats, 'mibps': m_stats
        })

    # Sort by Instance ID, then Device Name
    disk_rows.sort(key=lambda x: (x['inst'], x['dev']))

    for d in disk_rows:
        i_max = ceil_round(d['iops']['max'], 100)
        i_p99 = ceil_round(d['iops']['p99'], 100)
        i_p50 = ceil_round(d['iops']['p50'], 100)
        
        m_max = ceil_round(d['mibps']['max'], 10)
        m_p99 = ceil_round(d['mibps']['p99'], 10)
        m_p50 = ceil_round(d['mibps']['p50'], 10)

        iops_str = f"{i_max} / {i_p99} / {i_p50}"
        mibps_str = f"{m_max} / {m_p99} / {m_p50}"

        print(f"{d['zone']:<15} | {d['inst']:<30} | {d['dev']:<20} | {iops_str:<25} | {mibps_str:<25}")

    print("-" * 145)
    
    if args.max:
        print("MAX LOGIC:")
        print("1. Data is based on the single second peak value in a 1 min sample (Max Burst).")
        print("2. Useful to see bursts that are washed out in a one minute sample.")
        print("3. Cannot be compared across disks (burst timestamp may vary) and thus NO POOL stats are generated.")
    else:
        print("POOL LOGIC:")
        print("1. POOL stats are calculated by summing aligned timestamps across all matched disks.")
        print("2. Individual stats show the contribution of each disk to the pool.")
        print("AVERAGE LOGIC:")
        print("1. Data is based on per 1 min samples.")
        
    print("2. IOPS rounded up to nearest 100. Throughput rounded up to nearest 10 MiB/s.")

    # --- CSV OUTPUT ---
    if args.csv_output:
        print(f"\nWriting summary to CSV: {args.csv_output}")
        try:
            with open(args.csv_output, 'w', newline='') as csvfile:
                fieldnames = ['Type', 'Zone', 'Instance_ID', 'Device_Name', 
                              'IOPS_Max', 'IOPS_P99', 'IOPS_P50', 
                              'MiBps_Max', 'MiBps_P99', 'MiBps_P50']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                # Write Pools
                if calc_pool_stats and pool_stats_by_zone:
                    for zone, stats in sorted(pool_stats_by_zone.items()):
                        writer.writerow({
                            'Type': 'POOL',
                            'Zone': zone,
                            'Instance_ID': '',
                            'Device_Name': '',
                            'IOPS_Max': ceil_round(stats['iops']['max'], 100),
                            'IOPS_P99': ceil_round(stats['iops']['p99'], 100),
                            'IOPS_P50': ceil_round(stats['iops']['p50'], 100),
                            'MiBps_Max': ceil_round(stats['mibps']['max'], 10),
                            'MiBps_P99': ceil_round(stats['mibps']['p99'], 10),
                            'MiBps_P50': ceil_round(stats['mibps']['p50'], 10),
                        })

                # Write Disks
                for d in disk_rows:
                    writer.writerow({
                        'Type': 'DISK',
                        'Zone': d['zone'],
                        'Instance_ID': d['inst'],
                        'Device_Name': d['dev'],
                        'IOPS_Max': ceil_round(d['iops']['max'], 100),
                        'IOPS_P99': ceil_round(d['iops']['p99'], 100),
                        'IOPS_P50': ceil_round(d['iops']['p50'], 100),
                        'MiBps_Max': ceil_round(d['mibps']['max'], 10),
                        'MiBps_P99': ceil_round(d['mibps']['p99'], 10),
                        'MiBps_P50': ceil_round(d['mibps']['p50'], 10),
                    })
        except IOError as e:
            print(f"Error writing to CSV file: {e}")

if __name__ == "__main__":
    main()
