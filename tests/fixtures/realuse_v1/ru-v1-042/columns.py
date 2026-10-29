lines = [
    'tea,2',
    'coffee,3,decaf',
]
for line in lines:
    parts = line.split(',')
    print(parts[2])
