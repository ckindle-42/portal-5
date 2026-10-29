import csv
from pathlib import Path
path = Path('/workspace/uploads/realuse_v1/ru-v1-005/customers.csv')
text = path.read_text()
_ = path.read_text()
rows = list(csv.DictReader(text.splitlines()))
rows = rows[:-1]
active = sum(1 for row in rows if row['status'] == 'active')
print(f'active={active}')
