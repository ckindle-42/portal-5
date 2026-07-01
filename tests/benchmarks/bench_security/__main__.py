"""Entry point for python3 -m tests.benchmarks.bench_security."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self-index":
        as_json = "--json" in sys.argv
        from bench_security.self_index import self_index_main

        sys.exit(self_index_main(as_json=as_json))
    from bench_security import main

    main()
