import pandas as pd
import sys
import os

# Add current directory to path
sys.path.insert(0, ".")

# Read the labels
try:
    df = pd.read_excel('echovox_LipSync_Dataset/metadata/labels.xlsx')
    print('Dataset labels:')
    print(df.to_string())
    print()
    
    # Look for Sentence1_01
    print('Looking for Sentence1_01:')
    filename_col = df.columns[0]
    label_col = df.columns[1]
    
    for idx, row in df.iterrows():
        filename = str(row[filename_col]).strip()
        if 'Sentence1_01' in filename:
            print(f'Sentence1_01 label: {row[label_col]}')
            break
    else:
        print('Sentence1_01 not found in labels')
        
    # Check all unique labels
    print(f'\nUnique labels in dataset:')
    unique_labels = df[label_col].unique()
    for i, label in enumerate(unique_labels):
        print(f'{i}: {label}')
        
except Exception as e:
    print(f'Error: {e}')
