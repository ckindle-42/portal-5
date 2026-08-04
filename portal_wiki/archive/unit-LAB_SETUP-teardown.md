---
id: unit-LAB_SETUP-teardown
kind: why
title: "LAB_SETUP \u2014 Teardown"
sources:
- type: design
  path: docs/LAB_SETUP.md
  section: Teardown
last_generated_commit: ''
confidence: high
tags:
- docs
- LAB_SETUP
created_at: 1783195000.86915
updated_at: 1783195000.86915
---


```bash
./launch.sh lab-down                        # stop core + on-demand (no footprint)
./launch.sh lab-teardown                    # lab-down + teardown
./launch.sh lab-teardown --purge-downloads  # deep reclaim (removes vulhub clone + images)
```

Default preserves downloads (`--purge-downloads` is opt-in) so the next `lab up` is instant.
