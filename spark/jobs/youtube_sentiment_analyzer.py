from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, udf, pandas_udf
from pyspark.sql.types import StructType, StructField, StringType, ArrayType, TimestampType
import re
import os
import pickle
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences
import numpy as np
import json
import logging
import pandas as pd
# Define path to the artifacts
MODEL_PATH = '/app/artifacts/sentiment_model.h5'
TOKENIZER_PATH = '/app/artifacts/tokenizer.pickle'
CHECKPOINT_PATH = '/tmp/kafka-syslog-checkpoint'

def clean_text(text):
    """Clean the text by removing special characters and converting to lowercase"""
    if not isinstance(text, str):
        return ''
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    text = text.lower()
    return text

def create_spark_session():
    """Create and configure Spark Session with necessary packages"""
    return (SparkSession.builder
            .appName("YouTube Comment Sentiment Analysis")
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0")
            .config("spark.streaming.stopGracefullyOnShutdown", "true")
            .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_PATH)
            .getOrCreate())

def load_sentiment_model():
    """Load the sentiment analysis model and tokenizer"""
    print(f"Loading model from {MODEL_PATH}")
    model = load_model(MODEL_PATH)
    
    print(f"Loading tokenizer from {TOKENIZER_PATH}")
    with open(TOKENIZER_PATH, 'rb') as handle:
        tokenizer = pickle.load(handle)
        
    return model, tokenizer

def predict_sentiment_batch(texts, model, tokenizer):
    """Predict sentiment for a batch of texts"""
    texts_clean = [clean_text(t) for t in texts]
    sequences = tokenizer.texts_to_sequences(texts_clean)
    padded = pad_sequences(sequences, padding='pre', maxlen=24)
    preds = model.predict(padded)
    labels = preds.argmax(axis=1)
    label_mapping = {0: 'negative', 1: 'neutral', 2: 'positive'}
    mapped_labels = [label_mapping[l] for l in labels]
    return mapped_labels

@pandas_udf(StringType())
def predict_sentiment(texts: pd.Series) -> pd.Series:
    # lazy-load inside UDF so each executor can access
    from tensorflow.keras.models import load_model
    from tensorflow.keras.preprocessing.sequence import pad_sequences
    import pickle, re

    # load artifacts once per partition
    model = load_model(MODEL_PATH)
    with open(TOKENIZER_PATH, 'rb') as f:
        tokenizer = pickle.load(f)

    def clean(t):
        if not isinstance(t, str): return ''
        return re.sub(r'[^a-zA-Z\s]', '', t).lower()

    cleaned = texts.map(clean).tolist()
    seqs = tokenizer.texts_to_sequences(cleaned)
    padded = pad_sequences(seqs, padding='pre', maxlen=24)
    preds = model.predict(padded)
    idxs = preds.argmax(axis=1)
    mapping = {0: 'negative', 1: 'neutral', 2: 'positive'}
    return pd.Series([mapping[i] for i in idxs])


def main():
    # Create Spark Session
    spark = create_spark_session()
    
    # Set up logging
    spark.sparkContext.setLogLevel("ERROR")
    logging.getLogger("py4j").setLevel(logging.ERROR)
    
    # Load model and tokenizer
    model, tokenizer = load_sentiment_model()
    
    # Define schema for JSON message
    comment_schema = StructType([
        StructField("video_id", StringType()),
        StructField("category", StringType()),
        StructField("link", StringType()),
        StructField("platform", StringType()),
        StructField("comment", StructType([
            StructField("comment_id", StringType()),
            StructField("text", StringType()),
            StructField("date", StringType()),
            StructField("replies", ArrayType(StructType([
                StructField("reply_id", StringType()),
                StructField("text", StringType()),
                StructField("date", StringType())
            ])))
        ])),
        StructField("timestamp", StringType())
    ])
    
    # Read from Kafka
    kafka_df = (spark
                .readStream
                .format("kafka")
                .option("kafka.bootstrap.servers", "kafka1:29092")
                .option("subscribe", "youtube-comments")
                .option("startingOffsets", "latest")
                .load())
    
    # Parse JSON data
    parsed_df = (kafka_df
                .selectExpr("CAST(value AS STRING)")
                .select(from_json(col("value"), comment_schema).alias("data"))
                .select(
                    col("data.video_id").alias("video_id"),
                    col("data.comment.text").alias("text")
                ))
    
    # Process each batch with our sentiment model
    result_df = parsed_df.withColumn("sentiment", predict_sentiment(col("text"))).select("video_id", "sentiment", "text")

    query = (result_df
            .writeStream
            .format("console")
            .option("truncate", "false")
            .start())

    query.awaitTermination()


if __name__ == "__main__":
    main()