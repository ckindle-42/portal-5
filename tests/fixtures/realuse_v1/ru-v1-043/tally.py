votes = ['Y', 'N ', 'Y', 'N ', 'Y']
noes = sum(1 for vote in votes if vote == 'N')
print(f'noes={noes}')
