def main():
    mode = globals().get('mode')
    if mode == 'live':
        print('READY')
        return
    print('ERROR missing config.json')
main()
