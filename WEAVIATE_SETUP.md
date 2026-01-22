# Weaviate Connection Setup Guide

## Overview

The application now supports Weaviate client v4+ which requires both HTTP and gRPC connection parameters. This guide explains how to configure your `.env` file for Weaviate Cloud or self-hosted instances.

## Environment Variables for .env File

Add these variables to your `.env` file:

### Required Variables

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# Weaviate HTTP URL (REST API endpoint)
WEAVIATE_URL=https://oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud

# Weaviate API Key (required for Weaviate Cloud)
WEAVIATE_API_KEY=d2x1QUhpbklSSEx4ZmtlUV9mOVlvRGxmdFJsK2g3RDJuQko4aHZOSDNYNVlORitBT2FoeGFrcWd1ejhRPV92MjAw

# Weaviate gRPC URL (optional, will be derived from HTTP URL if not provided)
WEAVIATE_GRPC_URL=grpc-oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud

# Weaviate Class/Collection Name (optional, defaults to "IngestedChunk")
WEAVIATE_CLASS_NAME=PSATicketKnowledgeV3_MT
```

### Optional Variables

```env
# Chunking Configuration
CHUNK_MAX_TOKENS=400
CHUNK_OVERLAP_TOKENS=50
```

## Complete .env File Example

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Weaviate Configuration
WEAVIATE_URL=https://oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud
WEAVIATE_GRPC_URL=grpc-oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud
WEAVIATE_API_KEY=d2x1QUhpbklSSEx4ZmtlUV9mOVlvRGxmdFJsK2g3RDJuQko4aHZOSDNYNVlORitBT2FoeGFrcWd1ejhRPV92MjAw
WEAVIATE_CLASS_NAME=PSATicketKnowledgeV3_MT

# Chunking Configuration
CHUNK_MAX_TOKENS=400
CHUNK_OVERLAP_TOKENS=50
```

## Variable Explanations

### `WEAVIATE_URL` (Required)
- **Description**: The HTTP/REST API endpoint for your Weaviate instance
- **Format**: Full URL with protocol (http:// or https://)
- **Example**: `https://oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud`
- **For local**: `http://localhost:8080`

### `WEAVIATE_GRPC_URL` (Optional but Recommended)
- **Description**: The gRPC endpoint hostname (without protocol)
- **Format**: Just the hostname (e.g., `grpc-hostname.com`)
- **Example**: `grpc-oex4cwmtq2wvoonau2uda.c0.us-west3.gcp.weaviate.cloud`
- **Note**: If not provided, the system will derive it from `WEAVIATE_URL`, but for Weaviate Cloud, you should provide the separate gRPC URL

### `WEAVIATE_API_KEY` (Required for Weaviate Cloud)
- **Description**: API key for authenticating with Weaviate
- **Format**: Your Weaviate API key string
- **For local**: Can be left empty if no authentication is required

### `WEAVIATE_CLASS_NAME` (Optional)
- **Description**: Name of the Weaviate collection/class to store documents
- **Default**: `IngestedChunk`
- **Your value**: `PSATicketKnowledgeV3_MT`
- **Note**: The class will be created automatically if it doesn't exist

## Weaviate Client v4+ Changes

### What Changed?
- **Previous versions (v3)**: Only required HTTP connection
- **Current version (v4+)**: Requires both HTTP and gRPC connections

### Why?
Weaviate v4+ uses gRPC for better performance on bulk operations and vector queries. The client library now requires both connection types.

### How It Works
1. **HTTP connection**: Used for REST API operations (schema management, queries)
2. **gRPC connection**: Used for high-performance data insertion and vector operations

## For Weaviate Cloud Users

Weaviate Cloud provides:
- Separate HTTP URL: `https://your-cluster.weaviate.cloud`
- Separate gRPC URL: `grpc-your-cluster.weaviate.cloud`
- API Key: Required for authentication

Make sure to include all three in your `.env` file.

## For Local Weaviate Users

If running Weaviate locally:

```env
WEAVIATE_URL=http://localhost:8080
WEAVIATE_GRPC_URL=  # Can be left empty, will use localhost
WEAVIATE_API_KEY=   # Can be left empty if no auth
WEAVIATE_CLASS_NAME=IngestedChunk
```

## Verification

After setting up your `.env` file, start the application:

```bash
uvicorn app.main:app --reload
```

You should see in the logs:
```
INFO - Initializing Weaviate connection...
INFO - Weaviate class PSATicketKnowledgeV3_MT already exists
INFO - Application startup complete
```

If you see connection errors, check:
1. Your API key is correct
2. Both HTTP and gRPC URLs are accessible
3. Your Weaviate instance is running

