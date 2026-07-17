"""Entry point for python3 -m portal.modules.security.core."""

import sys
from pathlib import Path

# Load .env before anything else imports — several modules read LAB_SPLUNK_*
# and similar env vars at import/instantiation time (e.g. SplunkBackend.__init__),
# so a caller that forgets to `source .env` first silently gets broken defaults
# (e.g. LAB_SPLUNK_URL falling back to an unresolvable hostname) instead of an
# error. Found live 2026-07-17: every non-AD blue/purple telemetry fetch this
# session returned empty because .env wasn't sourced for the invoking shell —
# the CLI should not depend on the caller remembering this.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[4] / ".env")
except ImportError:
    pass

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "self-index":
        as_json = "--json" in sys.argv
        from portal.modules.security.core.self_index import self_index_main

        sys.exit(self_index_main(as_json=as_json))
    if len(sys.argv) > 1 and sys.argv[1] == "stage2-propose":
        as_json = "--json" in sys.argv
        apply = "--apply" in sys.argv
        from portal.modules.security.core.stage2_propose import stage2_propose_main

        sys.exit(stage2_propose_main(as_json=as_json, apply=apply))
    if len(sys.argv) > 1 and sys.argv[1] == "candidate-eval":
        from portal.modules.security.core.candidate_eval import candidate_eval_main

        sys.exit(candidate_eval_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "compliance-report":
        from portal.modules.security.core.compliance_report import compliance_report_main

        sys.exit(compliance_report_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "capability":
        from portal.modules.security.core.capability.cli import capability_main

        sys.exit(capability_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "goal":
        from portal.modules.security.core.goal_cli import goal_main

        sys.exit(goal_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "drift-check":
        from portal.modules.security.core.drift_cli import drift_check_main

        sys.exit(drift_check_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "model-canary":
        from portal.modules.security.core.drift_cli import model_canary_main

        sys.exit(model_canary_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        from portal.modules.security.core.loop_cli import loop_main

        sys.exit(loop_main(sys.argv[2:]))
    from portal.modules.security.core import main

    main()
