"""
Purpose: Test performance of object list operations
Author:  Chris Madden
"""

import argparse, time
from google.cloud import storage

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description="Test performance of the GCS objects.list API")
    parser.add_argument('--pagesize', type=int, default=1000, help='Page size for object listing (default: 1000)')
    parser.add_argument('--maxresults', type=int, default=25000, help='Max results for object listing (default: 25000)')
    parser.add_argument('--location', type=str, default='us', help='Location of bucket, one of: us, eu, us-central1 (default: us)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()

    # Set Location
    if args.location == 'us':
        BUCKET_NAME  = 'gcp-public-data-nexrad-l2'
    if args.location == 'eu':
        BUCKET_NAME  = 'gcp-public-data-sentinel-2'
    if args.location == 'us-central1':
        BUCKET_NAME  = 'gcp-public-data-arco-era5'

    # Execute and time operations
    page_count = 0
    file_count = 0

    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(BUCKET_NAME)
        bucket.reload()
        if args.verbose:
            print(f"Using public bucket {bucket.name} in location {bucket.location}")

        blob_list = bucket.list_blobs(page_size=args.pagesize, max_results=args.maxresults, projection='noAcl')

        total_start_time = time.monotonic()
        page_start_time = total_start_time
        for page in blob_list.pages: # Iterate each page
            page_count += 1
            page_total_time = time.monotonic() - page_start_time
            if args.verbose:
                print(f"Response {page_count} in {page_total_time:.2f}s, Items in response: {page.num_items}")
            file_count += page.num_items

            # for blob in page: # Iterate each object
            #    print (blob.name)

            page_start_time = time.monotonic()
    except Exception as e:
        print(f"Error listing objects: {e}")
        raise

    # Summary info
    total_time = time.monotonic() - total_start_time
    rate = file_count / total_time if file_count else 0
    print(f"Listed {file_count:,.0f} objects in {total_time:.2f}s with a list object throughput of {rate:,.0f} objects/s")