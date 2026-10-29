def load_config():
    raw = {'path': 'data.db', 'db': 'shop', 'mode': 'live'}
    path = raw.get('path', 'missing')
    return {'path': path, 'db': raw['db'], 'mode': raw['mode']}
