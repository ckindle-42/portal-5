Work only with artifacts in artifacts/.

1. Hash and `file` every artifact. Write 00_inventory.md.
2. Number hypotheses in 01_hypotheses.md before deep dives.
3. Each bash command tests one claim. Save interesting output under
   02_evidence/ with a short name.
4. Keep 03_model.md as the current best explanation. When a verifier
   fails, the model is wrong.
5. Register what "done" means in 04_checks.md.
6. 05_report.md is last.

Tools run in the RE container by default (target='container'):
file, sha256sum, strings, xxd, readelf, objdump, nm, llvm-objdump,
radare2, rizin, binwalk, unblob, yara, ssdeep, and python3 with
lief/capstone/pefile. Use these for ELF/PE/firmware/generic.

For Mach-O only, use bash target='host' (otool, codesign, lipo) —
available only if the operator enabled it.

Never dump a whole image. Disassemble one symbol at a time.
Do not fetch from the network. Do not execute the target.
