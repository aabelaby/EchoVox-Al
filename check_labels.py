import pandas as pd

# Read the labels
df = pd.read_excel('echovox_LipSync_Dataset/metadata/labels.xlsx')
print('Dataset labels:')
print(df.to_string())
print()
print('Looking for Sentence1_08:')
row = df[df.iloc[:, 0].astype(str).str.contains('Sentence1_08', case=False)]
if not row.empty:
    print(f'Sentence1_08 label: {row.iloc[0, 1]}')
else:
    print('Sentence1_08 not found in labels')
