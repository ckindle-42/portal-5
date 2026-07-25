---
id: unit-lab-setup-teardown
kind: what
title: "LAB_SETUP \u2014 Teardown"
sources:
- type: doc
  path: docs/LAB_SETUP.md
  commit: 05e42ec2
  section: Teardown
last_generated_commit: 05e42ec2
confidence: high
tags:
- docs
created_at: 1784946220.521163
updated_at: 1784946220.521163
---

```bash
./launch.sh lab-down                        # stop core + on-demand (no footprint)
./launch.sh lab-teardown                    # lab-down + teardown
./launch.sh lab-teardown --purge-downloads  # deep reclaim (removes vulhub clone + images)
```

Default preserves downloads (`--purge-downloads` is opt-in) so the next `lab up` is instant.
