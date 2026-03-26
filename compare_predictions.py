import os
import sys
from test import predict

# Test the same video file that your web interface would process
video_path = r"echovox_LipSync_Dataset\videos\Sentence2_02.mp4"
checkpoint_path = "checkpoints/best_model.pt"

print("Testing prediction consistency...")
print(f"Video: {video_path}")
print(f"Checkpoint: {checkpoint_path}")
print()

# Run prediction multiple times to check consistency
for i in range(3):
    print(f"Run {i+1}:")
    result = predict(video_path, checkpoint_path)
    if 'error' in result:
        print(f"  ERROR: {result['error']}")
    else:
        print(f"  Prediction: {result['predicted_sentence']}")
        print(f"  Confidence: {result['confidence']:.4f}")
    print()

# Also test with absolute path like web view uses
abs_checkpoint = os.path.abspath(checkpoint_path)
print(f"Testing with absolute path: {abs_checkpoint}")
result = predict(video_path, abs_checkpoint)
if 'error' in result:
    print(f"  ERROR: {result['error']}")
else:
    print(f"  Prediction: {result['predicted_sentence']}")
    print(f"  Confidence: {result['confidence']:.4f}")
