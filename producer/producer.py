from googleapiclient.discovery import build
import json
import traceback
import os
import time
import pandas as pd
import re
from dotenv import load_dotenv
from kafka import KafkaProducer

load_dotenv()

# Kafka configuration
KAFKA_BOOTSTRAP_SERVERS = 'kafka1:29092'
KAFKA_TOPIC = 'youtube-comments'

def create_kafka_producer():
    """Create and return a Kafka producer instance."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )
        print(f"Successfully connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
        return producer
    except Exception as e:
        print(f"Error creating Kafka producer: {str(e)}")
        raise

def extract_video_id(youtube_url):
    """Extract the video ID from a YouTube URL."""
    # Regular expression to match YouTube video IDs in URLs
    pattern = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, youtube_url)
    
    if match:
        return match.group(1)
    else:
        print(f"Could not extract video ID from {youtube_url}")
        return None

def get_comments(producer, api_key, video_id, category, original_link):
    """Fetch comments for a given video ID and send to Kafka topic."""
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    request = youtube.commentThreads().list(
        part="snippet,replies",
        videoId=video_id,
        textFormat="plainText",
        maxResults=50
    )
    
    # Initialize comments list to store all data
    all_comments = []
    page_count = 0
    
    while request:
        try:
            response = request.execute()
            page_count += 1
            print(f"Processing page {page_count}")
            
            for item in response['items']:
                # Extract the top-level comment
                comment_data = {
                    'comment_id': item['id'],
                    'text': item['snippet']['topLevelComment']['snippet']['textDisplay'],
                    'date': item['snippet']['topLevelComment']['snippet']['publishedAt'],
                    'replies': []
                }
                
                # Process replies if they exist
                reply_count = item['snippet']['totalReplyCount']
                if reply_count > 0 and 'replies' in item:
                    for reply in item['replies']['comments']:
                        reply_data = {
                            'reply_id': reply['id'],
                            'text': reply['snippet']['textDisplay'],
                            'date': reply['snippet']['publishedAt']
                        }
                        comment_data['replies'].append(reply_data)
                
                all_comments.append(comment_data)
                
                # Send individual comment to Kafka
                send_to_kafka(producer, video_id, category, original_link, comment_data)
            
            # Get next page
            request = youtube.commentThreads().list_next(request, response)
            
            if request:
                print("Moving to next page of comments")
                time.sleep(2)  # Prevent rate limiting
                
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            print(traceback.format_exc())
            print("Sleeping for 10 seconds before trying to continue")
            time.sleep(10)
            
            # Try to continue if possible
            if 'request' in locals() and request:
                continue
            else:
                break
    
    print(f"Finished processing {len(all_comments)} comments for video {video_id}")
    return len(all_comments)

def send_to_kafka(producer, video_id, category, original_link, comment_data):
    """Send a comment to the Kafka topic."""
    try:
        # Create the message with metadata
        message = {
            "video_id": video_id,
            "category": category,
            "link": original_link,
            "platform": "youtube",
            "comment": comment_data,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        
        # Send to Kafka using video_id as the key for partitioning
        future = producer.send(KAFKA_TOPIC, key=video_id, value=message)
        # Wait for the message to be delivered
        future.get(timeout=10)
        
    except Exception as e:
        print(f"Error sending to Kafka: {str(e)}")
        print(traceback.format_exc())

def process_csv_links(csv_file_path, api_key):
    """Process all YouTube links from the CSV file."""
    # Create Kafka producer
    producer = create_kafka_producer()
    
    # Read the CSV file
    try:
        df = pd.read_csv(csv_file_path)
        print(f"Successfully loaded {len(df)} links from {csv_file_path}")
    except Exception as e:
        print(f"Error reading CSV file: {str(e)}")
        return
    
    # Process each link
    for index, row in df.iterrows():
        try:
            link = row['Link']
            category = row['Category']
            
            # Extract video ID from the link
            video_id = extract_video_id(link)
            
            if video_id:
                print(f"\nProcessing {index+1}/{len(df)}: {video_id} (Category: {category})")
                
                # Process the video, passing the original link
                get_comments(producer, api_key, video_id, category, link)
                
                # Small delay between videos to prevent rate limiting
                time.sleep(3)
            
        except Exception as e:
            print(f"Error processing row {index}: {str(e)}")
            print(traceback.format_exc())
    
    # Clean up Kafka producer
    producer.flush()
    producer.close()
    
    print("\nAll videos have been processed!")

def main():
    # Configuration variables
    csv_file_path = "link_crawl_youtube.csv"  # CSV file with links
    
    # Get API key from environment variables
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("Error: YOUTUBE_API_KEY not found in environment variables")
        return
    
    print(f"Starting to process videos from {csv_file_path}")
    process_csv_links(csv_file_path, api_key)

if __name__ == "__main__":
    main()