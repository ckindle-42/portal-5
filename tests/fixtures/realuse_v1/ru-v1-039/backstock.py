items = [
    {'name': 'mug', 'place': 'shelf', 'count': 12},
    {'name': 'plate', 'place': 'bin', 'count': 5},
    {'name': 'bowl', 'place': 'bin', 'count': 2},
]
total = sum(item['count'] for item in items if item['place'] == 'shelf')
print(total)
