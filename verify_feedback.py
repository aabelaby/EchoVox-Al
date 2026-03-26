import requests
import json

BASE_URL = "http://localhost:5000"

def test_feedback_api():
    print("Testing Feedback API...")
    
    # Mock data
    feedback_payload = {
        "user_id": 1,
        "project_id": 1,
        "comment": "Testing the new satisfied column!",
        "satisfied": 1
    }
    
    try:
        # Submit feedback
        resp = requests.post(f"{BASE_URL}/api/feedback", json=feedback_payload)
        print(f"POST /api/feedback: {resp.status_code}")
        print(resp.json())
        
        # Check admin stats
        resp = requests.get(f"{BASE_URL}/api/admin/stats")
        print(f"GET /api/admin/stats: {resp.status_code}")
        print(resp.json())
        
        # Check admin feedback list
        resp = requests.get(f"{BASE_URL}/api/admin/feedback")
        print(f"GET /api/admin/feedback: {resp.status_code}")
        feedback_list = resp.json()
        if feedback_list:
            print(f"Latest feedback: {feedback_list[0]}")
            
    except Exception as e:
        print(f"Error during testing: {e}")

if __name__ == "__main__":
    test_feedback_api()
