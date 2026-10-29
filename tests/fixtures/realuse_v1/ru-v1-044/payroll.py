crew = [
    {'name': 'Ivo', 'hours': 6},
    {'name': 'Mara', 'hours': None},
]
for member in crew:
    pay = member['hours'] * 22
    print(member['name'], pay)
