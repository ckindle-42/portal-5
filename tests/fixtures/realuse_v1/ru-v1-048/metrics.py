import csv
rows = list(csv.DictReader(['name,seconds', 'boil,90']))
total = sum(int(row['elapsed']) for row in rows)
print(total)
