# YouTube Comment Sentiment Analysis Streaming Pipeline

A real-time data processing pipeline that crawls YouTube comments, streams them through Kafka, and analyzes sentiment using Spark Structured Streaming and a deep learning model.

## Overview

This project implements an end-to-end streaming pipeline that:

1. **Collects data**: Crawls comments from YouTube videos using the YouTube Data API v3
2. **Streams data**: Publishes comment data to Kafka topics in real-time
3. **Processes data**: Consumes the stream with Spark Structured Streaming
4. **Analyzes sentiment**: Classifies each comment as positive, neutral, or negative using a pre-trained deep learning model

## Architecture

```
YouTube API → Producer → Kafka → Spark Streaming → Sentiment Analysis → Console Output
```

## Prerequisites

- Docker and Docker Compose
- Google Cloud account with YouTube Data API v3 enabled
- YouTube API key

## Installation

### 1. Install Docker

Visit: https://docs.docker.com/engine/install/ubuntu/

### 2. Install Docker Compose

```bash
# Update the package index, and install the latest version of Docker Compose:
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Verify that Docker Compose is installed correctly by checking the version.
docker compose version

```

For detailed instructions, visit: https://docs.docker.com/compose/install/linux/

### 3. Clone the Repository

```bash
git clone https://github.com/hien2706/sentiment-streaming-analysis.git
cd sentiment-streaming-analysis
```

### 4. Setup YouTube API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3
4. Create API credentials (API Key)
5. Create a `.env` file in the `producer` directory:
   ```bash
   echo "YOUTUBE_API_KEY=your_api_key_here" > producer/.env
   ```

## Running the Pipeline

### 1. Build the Docker Images

```bash
docker compose build
```

### 2. Start the Containers

```bash
docker compose up -d
```

### 3. Create Kafka Topic

```bash
docker exec -it kafka1 kafka-topics --create --bootstrap-server kafka1:29092 --replication-factor 1 --partitions 1 --topic youtube-comments
```

### 4. Start the Spark Job (in a dedicated terminal)

```bash
docker exec -it spark-master spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.2 /app/spark_jobs/youtube_sentiment_analyzer.py
```

### 5. Start the Producer (in another terminal)

```bash
docker exec -it kafka-producer python producer.py
```

## Monitoring

- **Kafka**: View messages with `docker exec -it kafka1 kafka-console-consumer --topic youtube-comments --bootstrap-server kafka1:29092`
- **Spark**: Access the Spark UI at `http://localhost:8080`

## Customization

- Edit `producer/link_crawl_youtube.csv` to analyze comments from different YouTube videos
- The sentiment analysis model files are stored in `spark/artifacts/`

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.