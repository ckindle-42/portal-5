"""Entry point for python3 -m tests.benchmarks.bench_security."""

import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self-index":
        as_json = "--json" in sys.argv
        from bench_security.self_index import self_index_main

        sys.exit(self_index_main(as_json=as_json))
    if len(sys.argv) > 1 and sys.argv[1] == "stage2-propose":
        as_json = "--json" in sys.argv
        apply = "--apply" in sys.argv
        from bench_security.stage2_propose import stage2_propose_main

        sys.exit(stage2_propose_main(as_json=as_json, apply=apply))
    from bench_security import main

    main()
