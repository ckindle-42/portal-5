import config_reader

def main():
    cfg = config_reader.load_config()
    return cfg['db']
