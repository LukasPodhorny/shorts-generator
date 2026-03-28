import os
import sys
import argparse
from dotenv import load_dotenv
from aishorts.utils.r2_handler import CloudflareR2

# Load environment variables from .env
load_dotenv()

def main():
    parser = argparse.ArgumentParser(description="Upload large assets to Cloudflare R2")
    parser.add_argument("file_path", help="Local path to the file you want to upload")
    parser.add_argument("--key", help="Remote key (path) in the R2 bucket. Defaults to assets/bg_video/filename")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.file_path):
        print(f"Error: File not found at {args.file_path}")
        sys.exit(1)
        
    # Initialize R2 handler
    r2 = CloudflareR2()
    
    # Default key if not provided
    filename = os.path.basename(args.file_path)
    remote_key = args.key or f"assets/bg_video/{filename}"
    
    print(f"Uploading '{args.file_path}' to '{remote_key}'...")
    
    try:
        # boto3 automatically handles multipart uploads for large files
        public_url = r2.upload_file(args.file_path, remote_key)
        
        print("\nUpload Successful!")
        print(f"Remote Key: {remote_key}")
        print(f"Public URL: {public_url}")
        print("\nYou can now use the following in your video_templates.json:")
        print(f'{{\n  "url": "{public_url}",\n  "cache_key": "{filename}"\n}}')
        
    except Exception as e:
        print(f"\nUpload failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
