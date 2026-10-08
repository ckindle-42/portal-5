"""bully.behavior_values: behavior kept, environment identity masked, noise kept out of the budget."""

from __future__ import annotations

from portal.modules.security.core.bully import signatures
from portal.modules.security.core.bully.behavior_values import (
    MAX_PER_LABEL,
    behavior_values,
    normalize,
)


def test_kv_text_yields_process_lineage_and_masks_identity() -> None:
    rec = (
        r"EventCode=1 UtcTime=2020-11-18 10:05:55.939 ProcessGuid={31314CAD-F097-5FB4-0000-0010885F0000} "
        r"Image=C:\Windows\System32\schtasks.exe User=ATTACKRANGE\bob "
        r"CommandLine=schtasks /create /tn Updater /tr C:\Users\bob\AppData\Local\Temp\u.exe /sc minute "
        r"ParentImage=C:\Windows\System32\cmd.exe"
    )
    terms = behavior_values([rec])
    assert "image: schtasks.exe" in terms
    assert "parent image: cmd.exe" in terms
    assert "command: schtasks /create /tn updater /tr u.exe /sc minute" in terms
    joined = " ".join(terms)
    assert "bob" not in joined and "attackrange" not in joined and "31314cad" not in joined


def test_paths_with_spaces_keep_the_file_name() -> None:
    v = normalize("command", r'"C:\Program Files\Splunk\bin\splunk-powershell.exe" --ps2')
    assert v == "splunk-powershell.exe --ps2"


def test_windows_switches_survive_path_masking() -> None:
    assert normalize("command", "cmd.exe /c whoami") == "cmd.exe /c whoami"


def test_generated_names_collapse_and_real_names_do_not() -> None:
    assert normalize("file", r"C:\x\__PSScriptPolicyTest_04hirqe5.pu0.ps1") == (
        "__psscriptpolicytest_<r>.pu0.ps1"
    )
    assert normalize("image", r"C:\Windows\sysmon64.exe") == "sysmon64.exe"


def test_auditd_hex_proctitle_is_decoded() -> None:
    rec = "type=PROCTITLE msg=audit(1:2): proctitle=726d002d7266002f746d702f78"
    assert "command: rm -rf x" in behavior_values([rec])


def test_identity_provider_json_is_flattened() -> None:
    rec = {
        "eventType": "user.session.start",
        "displayMessage": "User login to Okta",
        "outcome": {"result": "SUCCESS"},
        "actor": {"alternateId": "user15@example.com"},
    }
    terms = behavior_values([rec])
    assert {"event type: user.session.start", "outcome: success"} <= set(terms)
    assert not any("user15" in t for t in terms)


def test_rare_terms_first_and_one_label_cannot_take_the_budget() -> None:
    background = [
        f"EventCode=13 TargetObject=HKLM\\Software\\Inv\\app{i}\\Publisher" for i in range(30)
    ]
    noisy = ["EventCode=10 SourceImage=C:\\Windows\\svchost.exe"] * 20
    attack = [
        "EventCode=1 Image=C:\\Windows\\certutil.exe CommandLine=certutil -urlcache -f x a.exe"
    ]
    terms = behavior_values(background + noisy + attack, limit=10)
    # 30 distinct registry writes tie the one-off attack at count 1; the per-label cap is what
    # keeps the attack in a small budget, and the recurring svchost access sorts last.
    assert sum(t.startswith("registry: ") for t in terms) == MAX_PER_LABEL
    assert "image: certutil.exe" in terms
    assert "command: certutil -urlcache -f x a.exe" in terms
    assert terms[-1] == "source image: svchost.exe"


def test_semantic_query_leads_with_content_and_is_unchanged_without_values() -> None:
    view = {
        "action_sequence": ["event-0:1", "field:Image"],
        "artifacts": {"behavior_values": ["image: certutil.exe", "command: certutil -urlcache"]},
    }
    sig = signatures.build_signature({"episode_id": "e"}, view)
    assert signatures.semantic_query(sig).startswith(
        "content: image: certutil.exe; command: certutil -urlcache | actions: "
    )
    bare = signatures.build_signature({"episode_id": "e"}, {"action_sequence": ["event-0:1"]})
    assert signatures.semantic_query(bare) == "actions: event-0:1"


def test_lab_identity_is_masked_but_public_domains_and_admin_shares_are_not() -> None:
    assert normalize("dns", "ar-win-dc.attackrange.local") == "<host>"
    assert normalize("dns", "pastebin.com") == "pastebin.com"
    assert normalize("service", "WIN-DC-MVELAZCO$") == "<machine>"
    assert normalize("share", r"\\*\IPC$") == "ipc$"
    assert normalize("command", r"net use \\fs01.corp\c$") == "net use c$"


def test_coded_values_survive_and_html_entities_are_decoded() -> None:
    assert normalize("access", "0x1fffff") == "0x1fffff"
    assert normalize("command", "sudo octave-cli --eval sh&quot;)") == "sudo octave-cli --eval sh )"
    assert normalize("script", "([adsisearcher] (&amp;(objectcategory=group)) ).findall()") == (
        "([adsisearcher] (&(objectcategory=group)) ).findall()"
    )
