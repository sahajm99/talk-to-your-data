"""Test script for chat endpoint."""

import requests
import json
import sys


def test_chat_query(base_url: str = "http://localhost:8000"):
    """
    Test the chat query endpoint.

    Args:
        base_url: Base URL of the API (default: http://localhost:8000)
    """
    # Test queries
    test_queries = [
        {
            "project_id": "test",
            "query": "What is this document about?",
            "top_k": 5,
            "include_images": True
        },
        {
            "project_id": "test",
            "query": "Can you summarize the main points?",
            "top_k": 3,
            "include_images": False
        }
    ]

    print("=" * 80)
    print("Testing Chat Endpoint")
    print("=" * 80)

    session_id = None

    for idx, query_data in enumerate(test_queries, 1):
        print(f"\n\nTest Query {idx}:")
        print(f"Question: {query_data['query']}")
        print("-" * 80)

        # Add session_id if we have one from previous query
        if session_id:
            query_data["session_id"] = session_id

        try:
            # Send POST request
            response = requests.post(
                f"{base_url}/chat/query",
                json=query_data,
                headers={"Content-Type": "application/json"}
            )

            # Check response status
            if response.status_code == 200:
                result = response.json()

                # Save session_id for next query
                session_id = result.get("session_id")

                print(f"\n✓ Success!")
                print(f"  Session ID: {session_id}")
                print(f"  Answer:\n  {result['answer']}\n")
                print(f"  Sources Retrieved: {len(result.get('sources', []))}")

                # Print source details
                if result.get('sources'):
                    print("\n  Source Details:")
                    for i, source in enumerate(result['sources'][:3], 1):  # Show first 3 sources
                        print(f"    [{i}] {source['file_name']} (Page {source.get('page_number', 'N/A')})")
                        print(f"        Score: {source['score']:.4f}")
                        print(f"        Text: {source['text'][:100]}...")

                # Print timing information
                print(f"\n  Performance:")
                print(f"    Retrieval: {result.get('retrieval_time_ms', 0):.2f}ms")
                print(f"    Generation: {result.get('generation_time_ms', 0):.2f}ms")
                print(f"    Total: {result.get('total_time_ms', 0):.2f}ms")

            else:
                print(f"\n✗ Error: {response.status_code}")
                print(f"  {response.text}")
                return False

        except requests.exceptions.ConnectionError:
            print(f"\n✗ Error: Cannot connect to {base_url}")
            print("  Make sure the server is running with: uvicorn app.main:app --reload")
            return False

        except Exception as e:
            print(f"\n✗ Error: {str(e)}")
            return False

    # Test conversation history
    if session_id:
        print("\n\n" + "=" * 80)
        print("Testing Conversation History")
        print("=" * 80)

        try:
            response = requests.get(f"{base_url}/chat/history/{session_id}")

            if response.status_code == 200:
                history = response.json()
                print(f"\n✓ Retrieved {len(history)} messages")

                for i, msg in enumerate(history, 1):
                    print(f"\n  [{i}] {msg['role'].upper()}:")
                    print(f"      {msg['content'][:100]}...")

            else:
                print(f"\n✗ Error getting history: {response.status_code}")

        except Exception as e:
            print(f"\n✗ Error: {str(e)}")

    # Test session stats
    print("\n\n" + "=" * 80)
    print("Testing Session Stats")
    print("=" * 80)

    try:
        response = requests.get(f"{base_url}/chat/sessions/stats")

        if response.status_code == 200:
            stats = response.json()
            print(f"\n✓ Session Statistics:")
            print(f"  Active Sessions: {stats.get('active_sessions', 0)}")
            print(f"  Expired Cleaned: {stats.get('expired_sessions_cleaned', 0)}")

        else:
            print(f"\n✗ Error getting stats: {response.status_code}")

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")

    print("\n\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)

    return True


def test_health_check(base_url: str = "http://localhost:8000"):
    """
    Test the health check endpoint.

    Args:
        base_url: Base URL of the API
    """
    print("\nTesting Health Check Endpoint...")

    try:
        response = requests.get(f"{base_url}/health")

        if response.status_code == 200:
            print("✓ Server is healthy")
            return True
        else:
            print(f"✗ Health check failed: {response.status_code}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"✗ Cannot connect to {base_url}")
        print("Make sure the server is running with: uvicorn app.main:app --reload")
        return False


if __name__ == "__main__":
    # Get base URL from command line or use default
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    print(f"API Base URL: {base_url}\n")

    # Test health check first
    if not test_health_check(base_url):
        sys.exit(1)

    # Run chat tests
    success = test_chat_query(base_url)

    sys.exit(0 if success else 1)
