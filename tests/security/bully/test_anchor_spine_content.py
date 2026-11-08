"""Content-derived behaviour spines classify the event rather than its log format."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from portal.modules.security.core.bully import telemetry_behavior
from portal.modules.security.core.bully.anchors import AnchorLibrary, EmptySpineError
from scripts.corpus_ingest import (
    ManifestDataset,
    description_census,
    parse_description_steps,
)


def test_attack_episode_with_an_empty_spine_is_refused() -> None:
    lib = AnchorLibrary()
    with pytest.raises(EmptySpineError):
        lib.load_attack_episode(
            source_id="attack_data",
            record={"family": "opaque"},
            logs=[{"verb": "not-a-behaviour"}],
            action_of=lambda log: log["verb"],
        )
    assert len(lib) == 0


def test_anchor_without_logs_still_loads() -> None:
    """The pre-R.3c record-only path is unchanged: no series is claimed."""
    lib = AnchorLibrary()
    anchor = lib.load_attack_episode(source_id="attack_data", record={"family": "x"})
    assert anchor.behavioural_series is None


# ── content classification: same event, different log formats ──────────────


def test_sysmon_process_create_reads_the_command_not_the_sourcetype() -> None:
    record = {
        "EventID": "1",
        "Image": "C:\\Windows\\System32\\vssadmin.exe",
        "CommandLine": "vssadmin delete shadows /all /quiet",
    }
    for sourcetype in ("", "XmlWinEventLog", "xmlwineventlog:sysmon", "corpus:raw"):
        assert telemetry_behavior.classify_content(record, sourcetype) == "destroy"


def test_security_event_id_reads_from_raw_xml() -> None:
    xml = (
        "<Event><System><EventID>4624</EventID></System>"
        "<EventData><Data Name='TargetUserName'>alice</Data></EventData></Event>"
    )
    assert telemetry_behavior.classify_content({"_raw": xml}) == "auth"


def test_powershell_script_block_is_execution_until_its_content_says_otherwise() -> None:
    record = {
        "EventID": "4104",
        "Channel": "Microsoft-Windows-PowerShell/Operational",
        "ScriptBlockText": "$x = Get-ChildItem C:\\Users",
    }
    assert telemetry_behavior.classify_content(record) == "enumerate"


def test_auditd_proctitle_is_read_as_the_command() -> None:
    record = {
        "_raw": "type=PROCTITLE msg=audit(02/20/2025 13:07:46.504:118908) : proctitle=cat /etc/shadow"
    }
    assert telemetry_behavior.classify_content(record) == "collect"


def test_cloudtrail_event_name_is_the_content() -> None:
    assert telemetry_behavior.classify_content({"eventName": "CreatePolicyVersion"}) == "escalate"
    assert (
        telemetry_behavior.classify_content({"eventName": "DescribeInstances", "readOnly": True})
        == "enumerate"
    )


def test_o365_operation_is_the_content() -> None:
    assert telemetry_behavior.classify_content({"Operation": "New-InboxRule"}) == "persist"
    assert telemetry_behavior.classify_content({"Operation": "UserLoggedIn"}) == "auth"


def test_asa_message_id_is_the_content() -> None:
    line = (
        "Sep 23 18:08:27 18.144.133.67 :2025-09-23T18:08:27Z: %ASA-5-111010: "
        "User 'admin', running 'N/A' from IP 198.27.166.158, executed 'logging emblem'"
    )
    assert telemetry_behavior.classify_content({"_raw": line}) == "execute"


def test_record_with_nothing_usable_is_unclassified() -> None:
    assert telemetry_behavior.classify_content({"columns": []}) == ""
    assert telemetry_behavior.classify_content({"_raw": "GET /index.html 200 512"}) == ""


def test_manifest_steps_keep_order_and_stated_outcomes() -> None:
    description = (
        "Atomic Test Results: Successful Execution of test T1003.003-1 Copy credentials "
        "Return value unclear for test T1003.003-3 Dump credentials "
        "Failed Execution of test T1003.003-6 Remove evidence"
    )

    steps = parse_description_steps(description)

    assert [(step.step_index, step.step_id, step.text, step.outcome) for step in steps] == [
        (1, "T1003.003-1", "Copy credentials", "successful"),
        (3, "T1003.003-3", "Dump credentials", "unclear"),
        (6, "T1003.003-6", "Remove evidence", "other"),
    ]


def test_description_census_counts_all_unparsed_descriptions_once_per_manifest() -> None:
    parsed = "Atomic Test Results: Successful Execution of test T1003.003-1 Copy credentials"
    prose = "An operator used a remote tool to access the host."
    malformed = "Atomic Test Results: Successful Execution of test T1003.003 Copy credentials"

    def dataset(manifest: str, description: str | None) -> ManifestDataset:
        steps = parse_description_steps(description)
        return ManifestDataset(
            path=Path(f"{manifest}.log"),
            sourcetype=None,
            source=None,
            dataset_epoch=None,
            techniques=(),
            mapped_sourcetype="",
            manifest=Path(f"{manifest}.yml"),
            description=description,
            steps=steps,
        )

    census = description_census(
        (
            dataset("parsed", parsed),
            dataset("parsed", parsed),
            dataset("prose", prose),
            dataset("malformed", malformed),
            dataset("missing", None),
        )
    )

    assert census["manifests_observed"] == 4
    assert census["with_parseable_steps"] == 1
    assert census["with_description_unparsed"] == 2
    assert census["with_step_like_description_unparsed"] == 1
    assert census["with_prose_description"] == 1
    assert census["without_description"] == 1
    assert census["step_count_distribution"] == {"1": 1}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '{"kind": "admin#reports#activity", "id": {"time": "2022-10-17T19:28:41.139Z", "uniqueQualifier": "243368084206", "applicationName": "login", "customerId": "C046r85ir"}, "etag": "\\"JCPRxFaiNR1s5TJ6ecIH8OpGdY4efiOYXbIB65itOzY/yo7ZAXd7lArzHgrotmSyzakrwoc\\"", "actor": {"email": "user1@splunkresearch.com", "profileId": "113747272258792008435"}, "ipAddress": "25.23.112.12", "event": {"type": "login", "name": "login_failure", "parameters": [{"name": "login_type", "value": "google_password"}, {"name": "login_challenge_method", "multiValue": ["password", "idv_preregistered_phone"]}]}}',
            "auth",
        ),
        (
            '{"ts":"2024-02-27T08:08:03.569305Z","uid":"CzeKJi1fKJy8mqFsTi","id.orig_h":"217.241.55.94","id.orig_p":57960,"id.resp_h":"10.0.1.14","id.resp_p":3389,"proto":"tcp","service":"ssl","duration":5099.188689947128,"orig_bytes":1051131,"resp_bytes":2170972,"conn_state":"RSTR","local_orig":false,"local_resp":true,"missed_bytes":0,"history":"ShADdaFr","orig_pkts":29101,"orig_ip_bytes":2564443,"resp_pkts":18985,"resp_ip_bytes":3158188,"tunnel_parents":["Cig89y3S7FkojKffBk"]}',
            "lateral",
        ),
        (
            '{"ts":"2024-02-27T08:10:31.082816Z","uid":"CwmSSA4EhHrRkVEeb","id.orig_h":"10.0.1.14","id.orig_p":53704,"id.resp_h":"18.153.126.41","id.resp_p":445,"proto":"tcp","service":"smb,ntlm,gssapi","duration":0.7016260623931885,"orig_bytes":1114,"resp_bytes":837,"conn_state":"RSTO","local_orig":true,"local_resp":false,"missed_bytes":0,"history":"ShADdR","orig_pkts":7,"orig_ip_bytes":1406,"resp_pkts":5,"resp_ip_bytes":1049,"tunnel_parents":["CkQjdc2LpKJv71fZl9"]}',
            "lateral",
        ),
        (
            'site="www.example.com" server="www.example.com" dest_port="443" dest_ip="192.0.2.1" src="198.51.100.1" src_ip="198.51.100.1" user="-" time_local="22/Feb/2024:13:00:00 -0500" protocol="HTTP/1.1" status="200" bytes_out="1073741000" bytes_in="234" http_referer="-" http_user_agent="python-requests/2.25.1" nginx_version="1.18.0" http_x_forwarded_for="-" http_x_header="-" uri_query="-" uri_path="/wp-json/bricks/v1/render_element" http_method="POST" response_time="0.250" cookie="-" request_time="0.650" category="application/json" https="on"',
            "c2_exfil",
        ),
        (
            '{"ctime": "Thu Jul 10 07:24:12 2025", "action": "policy_bulk_delete", "description": "{\\"admin_email\\": \\"test@test.com\\", \\"policies\\": \\"test2: PO9XV84OQJ5JXDBROM4O, test3: PO6OTE8JJQBX2C19SK3X, test4: POC0MJSTLYIB0RODL505, test5: POIHKCZ5M2DDE6BTGNE6\\"}", "isotimestamp": "2025-07-10T07:24:12+00:00", "object": null, "timestamp": 1752132252, "username": "Test Test", "host": "api-41e72ada.duosecurity.com", "extracted_eventtype": "administrator", "actionlabel": "policy_bulk_delete"}',
            "evade",
        ),
        (
            '{"ctime": "Thu Jul 10 07:37:49 2025", "access_device": {"browser": "Chrome", "browser_version": "137.0.0.0", "ip": {"address": "1.2.3.4"}, "location": {"city": "San Jose", "country": "United States", "state": "California"}, "os": "Windows", "os_version": "11"}, "action": {"details": "{\\"auth_method\\": \\"Password\\", \\"auth_device\\": \\"WAPF4P9AJ344ZX3DGPNO\\", \\"factor\\": \\"webauthn\\", \\"role\\": \\"Owner\\"}", "name": "admin_login"}, "activity_id": "e9b8d7eb-f274-4250-8f52-d0bee46b8abc", "actor": {"details": "{\\"created\\": \\"2025-07-02T09:18:46.000000+00:00\\", \\"last_login\\": \\"2025-07-10T07:37:33.000000+00:00\\", \\"email\\": \\"test@test.com\\", \\"status\\": null, \\"groups\\": null}", "key": "redacted-actor-key", "name": "Test Test", "type": "admin"}, "akey": "redacted-akey", "application": null, "old_target": null, "outcome": {"result": "SUCCESS"}, "target": {"details": null, "key": null, "name": null, "type": "admin_login"}, "ts": "2025-07-10T07:37:49.616714+00:00", "timestamp": 1752133069, "host": "api-41e72ada.duosecurity.com", "extracted_eventtype": "activity"}',
            "auth",
        ),
        (
            "2026-03-30T04:47:42+00:00 vsmart <auth.info> sshd[9573]: Accepted publickey for admin from 192.168.161.1 port 35252 ssh2: RSA SHA256:KEY_1",
            "auth",
        ),
        (
            '{"activity_id":0,"category_uid":4,"cisco_asa":{"full_log_print_specifiers":"[\\"\\",\\"\\",\\"\\",\\"\\"]","syslog_class":"INFORMATION","syslog_descriptor":"AAA_RESULT_REJECT","syslog_id":"ASA-6-113005","syslog_id_with_version":"ASA-6-113005-0","syslog_severity":"6"},"cisco_dtls_ipsec_tunnel":{"bytes_received":0,"bytes_transmitted":0,"cipher_suite":"","compression":"","connection_timeout":"","connection_timeout_left":"","destination_port":0,"dh_group":"","encapsulation":"","encryption":"","filter_name":"","hashing":"","id":"","idle_timeout":"","idle_timeout_left":"","ipv6_filter_name":"","local_selector":"","packets_received":0,"packets_received_dropped":0,"packets_transmitted":0,"packets_transmitted_dropped":0,"pfs_group":"","prf":"","rekey_data":"","rekey_data_left":"","rekey_interval":"","rekey_interval_left":"","remote_selector":"","source_port":0},"cisco_endpoint_posture":{"dap_connection_type":"","dap_record_name":""},"cisco_event_id":"4be3aa5d442331d1397a1826eec2b80764c10776e8f344636156b214f8b72dff","cisco_event_type":"ravpn","cisco_organization_id":8176184,"cisco_origin":{"id":0,"type":"UNKNOWN"},"cisco_ravpn_metadata":{"anyconnect_version":"","event_type":"FAILED"},"cisco_ravpn_session":{"assigned_ip":"","assigned_ipv6":"","audit_session_id":"","connected_at":0,"disconnection_reason":"","duration":"","id":"","inactivity":"","public_ip":"193.202.11.59","public_ipv6":"","redirect_acl":"","redirect_url":"","security_group_tag":"","session_type":"","vpn_profile":"","warning_reason":""},"cisco_ssl_ike_tunnel":{"bytes_received":0,"bytes_transmitted":0,"cipher_suite":"","compression":"","connection_timeout":"","connection_timeout_left":"","destination_port":0,"dh_group":"","encapsulation":"","encryption":"","filter_name":"","hashing":"","id":"","idle_timeout":"","idle_timeout_left":"","ipv6_filter_name":"","local_selector":"","packets_received":0,"packets_received_dropped":0,"packets_transmitted":0,"packets_transmitted_dropped":0,"pfs_group":"","prf":"","rekey_data":"","rekey_data_left":"","rekey_interval":"","rekey_interval_left":"","remote_selector":"","source_port":0},"class_uid":4001,"cloud":{"region":"us-west-2"},"device":{"os":{"version":""}},"metadata":{"product":{"name":"ciscoSecureAccess"},"version":"1.6.0"},"policy":{"data":{"failed_reasons":["AUTHORIZATION-CHECK"]}},"severity_id":0,"src_endpoint":{"name":""},"time":1777303058000,"type_uid":400100}',
            "auth",
        ),
        (
            '{ "datetime": "2023-11-06 16:49:50 GMT", "reason": "Not allowed to browse this category", "event_id": "0000000000000000004", "protocol": "HTTPS", "action": "Blocked", "zstenantid": "zs0-0000000", "zstenantdomain": "example.com", "transactionsize": "15319", "responsesize": "14662", "requestsize": "657", "urlcategory": "Other Information Technology", "serverip": "00.000.00.000", "clienttranstime": "0", "requestmethod": "POST", "refererURL": "dummy-referer.example.com", "useragent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/00.0.0000.00 Safari/537.36", "product": "NSS", "location": "Road Warrior", "ClientIP": "00.000.0.000", "status": "403", "user": "dummyuser@example.com", "url": "dummy-url.example.com", "vendor": "Zscaler", "hostname": "dummy-hostname.example.com", "clientpublicIP": "000.00.00.000", "threatcategory": "None", "threatname": "r-Virus-r", "filetype": "None", "appname": "General Browsing", "pagerisk": "0", "department": "0000DepartmentCode", "urlsupercategory": "Information Technology", "appclass": "General Browsing", "dlpengine": "None", "dlp_allow": "NA", "urlclass": "Business Use", "threatclass": "Virus", "dlpdictionaries": "None", "dlphitcount": "None", "fileclass": "None", "servertranstime": "0", "contenttype": "Other", "unscannabletype": "None", "deviceowner": "dummyowner", "devicehostname": "DUMMY-HOSTNAME", "clientsslcipher": "TLS1_3_CK_AES_256_GCM_SHA384", "clientsslsessreuse": "NO", "clienttlsversion": "TLS1_3", "deviceappversion": "0.0.0.0", "devicename": "dummy-device-name", "deviceostype": "Dummy OS", "deviceosversion": "Dummy OS Version", "filename": "None", "filesubtype": "None", "md5": "d41d8cd98f00b204e9800998ecf8427e", "mobappcat": "None", "mobappname": "None", "mobdevtype": "None", "respcode": "403", "respversion": "1.1", "rulelabel": "Dummy Rule Label", "ruletype": "UrlCat", "serversslsessreuse": "UNKNOWN", "srvcertchainvalpass": "PASS", "srvcertvalidationtype": "DV", "srvcertvalidityperiod": "MEDIUM", "srvocspresult": "None", "srvsslcipher": "None", "srvtlsversion": "None", "srvwildcardcert": "NO", "ssldecrypted": "Yes", "externalspr": "INSPECTED", "trafficredirectmethod": "DummyRedirectMethod", "datacenter": "DC1", "datacentercity": "City", "datacentercountry": "CT", "df_hostname": "None", "df_hosthead": "None" }',
            "c2_exfil",
        ),
        (
            '{ "datetime": "2023-11-06 16:49:48 GMT", "reason": "Not allowed to browse this category", "event_id": "0000000000000000002", "protocol": "HTTPS", "action": "Blocked", "zstenantid": "zs0-0000000", "zstenantdomain": "example.com", "transactionsize": "15319", "responsesize": "14662", "requestsize": "657", "urlcategory": "Other Information Technology", "serverip": "00.000.00.000", "clienttranstime": "0", "requestmethod": "POST", "refererURL": "dummy-referer.example.com", "useragent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/00.0.0000.00 Safari/537.36", "product": "NSS", "location": "Road Warrior", "ClientIP": "00.000.0.000", "status": "403", "user": "dummyuser@example.com", "url": "dummy-url.example.com", "vendor": "Zscaler", "hostname": "dummy-hostname.example.com", "clientpublicIP": "000.00.00.000", "threatcategory": "None", "threatname": "HTML.Phish.Genjp", "filetype": "None", "appname": "General Browsing", "pagerisk": "0", "department": "0000DepartmentCode", "urlsupercategory": "Information Technology", "appclass": "General Browsing", "dlpengine": "None", "dlp_allow": "NA", "urlclass": "Business Use", "threatclass": "None", "dlpdictionaries": "None", "dlphitcount": "None", "fileclass": "None", "servertranstime": "0", "contenttype": "Other", "unscannabletype": "None", "deviceowner": "dummyowner", "devicehostname": "DUMMY-HOSTNAME", "clientsslcipher": "TLS1_3_CK_AES_256_GCM_SHA384", "clientsslsessreuse": "NO", "clienttlsversion": "TLS1_3", "deviceappversion": "0.0.0.0", "devicename": "dummy-device-name", "deviceostype": "Dummy OS", "deviceosversion": "Dummy OS Version", "filename": "None", "filesubtype": "None", "md5": "d41d8cd98f00b204e9800998ecf8427e", "mobappcat": "None", "mobappname": "None", "mobdevtype": "None", "respcode": "403", "respversion": "1.1", "rulelabel": "Dummy Rule Label", "ruletype": "UrlCat", "serversslsessreuse": "UNKNOWN", "srvcertchainvalpass": "PASS", "srvcertvalidationtype": "DV", "srvcertvalidityperiod": "MEDIUM", "srvocspresult": "None", "srvsslcipher": "None", "srvtlsversion": "None", "srvwildcardcert": "NO", "ssldecrypted": "Yes", "externalspr": "INSPECTED", "trafficredirectmethod": "DummyRedirectMethod", "datacenter": "DC1", "datacentercity": "City", "datacentercountry": "CT", "df_hostname": "None", "df_hosthead": "None" }',
            "",
        ),
        (
            '11/21/2022 08:09:04 PM\nLogName=MSExchange Management\nEventCode=1\nEventType=4\nComputerName=win-dc-exch01.attackrange.local\nSourceName=MSExchange CmdletLogs\nType=Information\nRecordNumber=1897\nKeywords=Classic\nTaskCategory=General\nOpCode=None\nMessage=Cmdlet suceeded. Cmdlet Search-Mailbox, parameters -Identity "Administrator@attackrange.local" -SearchQuery "Subject:"Fay10dOWecFg"" -Force "True" -DeleteContent "True".',
            "collect",
        ),
        (
            "May  8 17:16:26 192.168.8.233 2025-05-08T17:14:37.248Z localhost.lan login[294069]: pam_unix(login:auth): authentication failure; logname= uid=0 euid=0 tty=char/tty/1 ruser= rhost=",
            "auth",
        ),
        (
            "May  7 17:17:50 192.168.8.233 2025-05-07T17:17:49.375Z localhost.localdomain Hostd[263196]: [Originator@6876 sub=Vimsvc.ha-eventmgr] Event 848 : File download from path '[Test]Test2/Test2.vmdk' was initiated from 'govc/0.50.0@192.168.196.95' and completed with status ''",
            "collect",
        ),
        (
            "May  7 13:19:00 192.168.8.233 2025-05-07T13:18:58.568Z localhost.localdomain Hostd[263198]: [Originator@6876 sub=Solo.VmwareCLI opID=esxcli-60-866e sid=52b7edac user=root] Dispatch system.version.get done",
            "enumerate",
        ),
        (
            "SESSION|05/14/2024 17:40:50.250|[HTTPS:217_44466_3nm:anonymous:10.0.1.30] READ: *POST /WebInterface/function/?c2f=qL0U&command=zip&path=%3CINCLUDE%3EC:"
            + "/Users"
            + "/Administrator/Downloads/CrushFTP10/CrushFTP10/sessions.obj%3C/INCLUDE%3E&names=/a HTTP/1.1*",
            "collect",
        ),
        (
            '"2026-04-20 23:19:55","EC2AMAZ-J8G2CH1","EC2AMAZ-J8G2CH1","10.0.1.115","3.151.127.146","Allowed","1 (A)","NOERROR","www.proxysite.com.","Proxy/Anonymizer,Application,Filter Avoidance","Anyconnect Roaming Client","Anyconnect Roaming Client","","139213","","8209150"',
            "enumerate",
        ),
        (
            '"2026-04-20 21:57:29","EC2AMAZ-J8G2CH1","10.0.1.115","3.151.127.146","104.20.23.154","text/html","ALLOWED","http://example.com/css-3444","","gobuster/3.8.1","404","","790","528","fb91d75a6bb430787a61b0aec5e374f580030f2878e1613eab5ca6310f7bbb9a","Research/Reference,Reference","","","","","","Anyconnect Roaming Client","","EC2AMAZ-J8G2CH1","Anyconnect Roaming Client","GET","ALLOWED","","css-3444","14303105","139213","","","","","","","","","","mps-7b95df5757-wmc2v.sigproxy.prod_aws_us-east-2_1_0n","PROD_AWS_US-EAST-2_1_0N","false","","false","false","","","8209150"',
            "enumerate",
        ),
        (
            "Aug 20 21:35:45 52.53.165.221 193: 000188: *Aug 20 21:35:44.567 UTC: %SEC_LOGIN-5-LOGIN_SUCCESS: Login Success [user: ec2-user] [Source: 76.154.218.105] [localport: 22] at 21:35:44 UTC Wed Aug 20 2025",
            "auth",
        ),
        (
            '{"process_exec":{"process":{"exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDo4NjQ5NTU0MzQ5NjAyODY6MjM4Njkx","pid":238691,"uid":0,"cwd":"/","binary":"/usr/bin/bash","arguments":"-lc \\"apt-get update -qq && apt-get install -y -qq sudo && sudo apt-get -o APT::Update::Pre-Invoke::=\\"echo preinvoke-test-daftpunk\\" update\\"","flags":"execve rootcwd clone inInitTree","start_time":"2025-09-15T19:23:01.868177370Z","auid":4294967295,"pod":{"namespace":"default","name":"apt-preinvoke","container":{"id":"containerd://82478fb2c6eb68dc35768e748b8d3cada6ed656e2f814f0c1cbed8130c73f8fc","name":"apt-preinvoke","image":{"id":"docker.io/library/ubuntu@sha256:4e0171b9275e12d375863f2b3ae9ce00a4c53ddda176bd55868df97ac6f21a6e","name":"docker.io/library/ubuntu:22.04"},"start_time":"2025-09-15T19:23:01Z","pid":1,"security_context":{}},"pod_labels":{"run":"apt-preinvoke"},"workload":"apt-preinvoke","workload_kind":"Pod"},"docker":"82478fb2c6eb68dc35768e748b8d3ca","parent_exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDo4NjQ5NTUyNDIzNTE3MDU6MjM4NjM1","tid":238691,"in_init_tree":true},"parent":{"exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDo4NjQ5NTUyNDIzNTE3MDU6MjM4NjM1","pid":238635,"uid":0,"cwd":"/run/containerd/io.containerd.runtime.v2.task/k8s.io/b6655b617d7c11de54944a3b316a7a17779a6c07257c6a4fe59b0ca5b861e7c3","binary":"/usr/bin/containerd-shim-runc-v2","arguments":"-namespace k8s.io -id b6655b617d7c11de54944a3b316a7a17779a6c07257c6a4fe59b0ca5b861e7c3 -address /run/containerd/containerd.sock","flags":"execve clone","start_time":"2025-09-15T19:23:01.675568985Z","auid":4294967295,"parent_exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDo4NjQ5NTUyMzE5NjIzMzk6MjM4NjI1","tid":238635,"in_init_tree":false},"ancestors":[{"exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDo4NjQ5NTUyMzE5NjIzMzk6MjM4NjI1","pid":238625,"uid":0,"cwd":"/run/containerd/io.containerd.runtime.v2.task/k8s.io/b6655b617d7c11de54944a3b316a7a17779a6c07257c6a4fe59b0ca5b861e7c3","binary":"/usr/bin/containerd-shim-runc-v2","arguments":"-namespace k8s.io -address /run/containerd/containerd.sock -publish-binary /usr/bin/containerd -id b6655b617d7c11de54944a3b316a7a17779a6c07257c6a4fe59b0ca5b861e7c3 start","flags":"execve clone","start_time":"2025-09-15T19:23:01.665179455Z","auid":4294967295,"parent_exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDoxMTk5MDAwMDAwMDoxNjI4","tid":238625,"in_init_tree":false},{"exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDoxMTk5MDAwMDAwMDoxNjI4","pid":1628,"uid":0,"cwd":"/","binary":"/usr/bin/containerd","flags":"procFS auid rootcwd","start_time":"2025-09-05T19:07:18.423217035Z","auid":4294967295,"parent_exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDowOjE=","tid":1628,"in_init_tree":false},{"exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDowOjE=","pid":1,"uid":0,"cwd":"/","binary":"/usr/lib/systemd/systemd","arguments":"--switched-root --system --deserialize=32","flags":"procFS auid rootcwd","start_time":"2025-09-05T19:07:06.433217108Z","auid":4294967295,"parent_exec_id":"aXAtMTkyLTE2OC04OS02NC51cy13ZXN0LTIuY29tcHV0ZS5pbnRlcm5hbDoxOjA=","tid":1,"in_init_tree":false}]},"node_name":"ip-192-168-89-64.us-west-2.compute.internal","time":"2025-09-15T19:23:01.868178157Z","cluster_name":"k8s-goat-cluster","node_labels":{"alpha.eksctl.io/cluster-name":"k8s-goat-cluster","alpha.eksctl.io/nodegroup-name":"ng-a99d40b1","beta.kubernetes.io/arch":"arm64","beta.kubernetes.io/instance-type":"t4g.medium","beta.kubernetes.io/os":"linux","eks.amazonaws.com/capacityType":"ON_DEMAND","eks.amazonaws.com/nodegroup":"ng-a99d40b1","eks.amazonaws.com/nodegroup-image":"ami-0339636baccc3c183","eks.amazonaws.com/sourceLaunchTemplateId":"lt-0da0169006f2a7c39","eks.amazonaws.com/sourceLaunchTemplateVersion":"1","failure-domain.beta.kubernetes.io/region":"us-west-2","failure-domain.beta.kubernetes.io/zone":"us-west-2c","k8s.io/cloud-provider-aws":"16c540d8ecc5192189b6444fb194814b","kubernetes.io/arch":"arm64","kubernetes.io/hostname":"ip-192-168-89-64.us-west-2.compute.internal","kubernetes.io/os":"linux","node.kubernetes.io/instance-type":"t4g.medium","topology.k8s.aws/zone-id":"usw2-az3","topology.kubernetes.io/region":"us-west-2","topology.kubernetes.io/zone":"us-west-2c"}}',
            "escalate",
        ),
        (
            '146.70.199.199 - - [23/Jun/2026:09:31:00.130 +0000] "POST /en-US/splunkd/__raw/v1/postgres/recovery/backup HTTP/1.1" 200 196 "-" "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 Mobile/15E148 Safari/604.1" - - 2ms',
            "collect",
        ),
        (
            '1767988970, search_name="Threat - ESCU - Cisco Secure Firewall - SSH Connection to Non-Standard Port - Rule - Rule", InlineResult="Would block", InlineResultReason="Intrusion Policy in \\"Detection\\" Inspection Mode", MitreAttackGroups="MITRE>ATT&CK Framework>Enterprise>Command and Control>Non-Standard Port", annotations="{\\"analytic_story\\":[\\"Cisco Smart Install Remote Code Execution CVE-2018-0171\\"],\\"cis20\\":[\\"CIS 13\\"],\\"cve\\":[\\"CVE-2018-0171\\"],\\"kill_chain_phases\\":[\\"Delivery\\",\\"Exploitation\\",\\"Installation\\"],\\"mitre_attack\\":[\\"T1136\\",\\"T1078\\"],\\"nist\\":[\\"DE.AE\\"],\\"type_list\\":[\\"Anomaly\\"],\\"data_source\\":[\\"Cisco Secure Firewall Threat Defense Intrusion Event\\"]}", annotations._all="Cisco Smart Install Remote Code Execution CVE-2018-0171", annotations._all="CIS 13", annotations._all="CVE-2018-0171", annotations._all="Cisco Secure Firewall Threat Defense Intrusion Event", annotations._all="Delivery", annotations._all="Exploitation", annotations._all="Installation", annotations._all="T1136", annotations._all="T1078", annotations._all="DE.AE", annotations._all="Anomaly", annotations._frameworks="analytic_story", annotations._frameworks="cis20", annotations._frameworks="cve", annotations._frameworks="kill_chain_phases", annotations._frameworks="mitre_attack", annotations._frameworks="nist", annotations._frameworks="type_list", annotations._frameworks="data_source", annotations.analytic_story="Cisco Smart Install Remote Code Execution CVE-2018-0171", annotations.cis20="CIS 13", annotations.cve="CVE-2018-0171", annotations.data_source="Cisco Secure Firewall Threat Defense Intrusion Event", annotations.kill_chain_phases="Delivery", annotations.kill_chain_phases="Exploitation", annotations.kill_chain_phases="Installation", annotations.mitre_attack="T1136", annotations.mitre_attack="T1078", annotations.nist="DE.AE", annotations.type_list="Anomaly", app="SSH", class_desc="Misc Activity", contributing_events_search="| savedsearch \\"Threat - ESCU - Cisco Secure Firewall - SSH Connection to Non-Standard Port - Rule - Rule\\" | search dest=\\"52.53.165.221\\"", dest="52.53.165.221", dest_port="2222", entity="52.53.165.221", entity_type="system", firstTime="2025-08-20T21:33:37", info_max_time="1767988800.000000000", info_min_time="1736380800.000000000", info_search_time="1767988967.790697000", lastTime="2025-08-20T21:33:40", orig_time="None", risk_message="Inbound SSH connection to sshd_operns detected from 76.154.218.105 to network device 52.53.165.221", risk_object="52.53.165.221", risk_object_type="system", risk_score="50.0", rule="Permit Inbound SSH", savedsearch_description="This analytic detects the creation of privileged user accounts on Cisco IOS devices, which could indicate an attacker establishing backdoor access. The detection focuses on identifying when user accounts are created with privilege level 15 (the highest administrative privilege level in Cisco IOS) or when existing accounts have their privileges elevated. This type of activity is particularly concerning when performed by unauthorized users or during unusual hours, as it may represent a key step in establishing persistence following the exploitation of vulnerabilities like CVE-2018-0171 in Cisco Smart Install. Threat actors like Static Tundra have been observed creating privileged accounts as part of their attack chain after gaining initial access to network devices.", signature="POLICY-OTHER Inbound SSH connection to non-standard port", signature_id="65369", source_event_id="2891c915-42aa-4abb-92f5-d63c1e129079@@risk@@2891c91542aa4abb92f5d63c1e129079", source_guid="2891c915-42aa-4abb-92f5-d63c1e129079", src="76.154.218.105", transport="tcp", unique_signature_count="1"',
            "c2_exfil",
        ),
        (
            '{"endtime":"2025-04-18T21:01:08.733505Z","timestamp":"2025-04-18T21:01:08.733014Z","ack_packets_in":3,"ack_packets_out":4,"app":"tcp","bytes":2836,"bytes_in":2616,"bytes_out":220,"client_rtt":8,"client_rtt_packets":1,"client_rtt_sum":8,"connection":"172.16.1.1:4786","data_packets_in":2,"data_packets_out":0,"dest_ip":"172.16.1.1","dest_mac":"52:54:00:B2:9D:B0","dest_port":4786,"duplicate_packets_in":0,"duplicate_packets_out":0,"flow_id":"21ae0dad-c2c8-4608-87c4-8de6f507d43c","initial_rtt":246,"missing_packets_in":0,"missing_packets_out":0,"packets_in":6,"packets_out":4,"protocol_stack":"ip:tcp","server_rtt":78,"server_rtt_packets":2,"server_rtt_sum":156,"src_ip":"172.16.100.1","src_mac":"52:54:00:95:44:64","src_port":3578,"tcp_status":0,"time_taken":499}',
            "",
        ),
        (
            'site="localhost" server="35.84.123.246" dest_port="80" dest_ip="10.0.1.21" src="73.245.172.254" src_ip="73.245.172.254" user="-" time_local="05/Apr/2022:16:05:20 +0000" protocol="HTTP/1.1" status="404" bytes_out="1277" bytes_in="1250" http_referer="http://35.84.123.246/shell.jsp?cmd=id" http_user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.74 Safari/537.36" nginx_version="1.21.5" http_x_forwarded_for="-" http_x_header="-" uri_query="-" uri_path="/favicon.ico" http_method="GET" response_time="0.003" cookie="-" request_time="0.002" category="text/html;charset=utf-8" https=""',
            "",
        ),
        (
            "type=PROCTITLE msg=audit(02/20/2025 13:07:05.497:110383) : proctitle=cat /opt/splunkforwarder/etc/passwd",
            "",
        ),
        (
            r'site="jenkins.example.com" server="3.8.2.2" dest_port="80" dest_ip="1.3.3.1" src="170.64.139.139" src_ip="170.64.139.139" user="-" time_local="29/Jan/2024:16:06:47 +0000" protocol="HTTP/1.1" status="500" bytes_out="3090" bytes_in="3064" http_referer="-" http_user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2762.73 Safari/537.36" nginx_version="1.18.0" http_x_forwarded_for="-" http_x_header="-" uri_query="remoting=false" uri_path="/cli" http_method="POST" response_time="0.004" cookie="-" request_time="0.181" category="text/html;charset=utf-8" https="" request_body="\x00\x00\x00\x06\x00\x00\x04help\x00\x00\x00\x0E\x00\x00\x0C@/etc/passwd\x00\x00\x00\x05\x02\x00\x03GBK\x00\x00\x00\x07\x01\x00\x05en_US\x00\x00\x00\x00\x03"',
            "collect",
        ),
    ],
)
def test_non_host_records_classify_from_their_content(raw: str, expected: str) -> None:
    """Real corpus records classify only when their content names a behaviour."""
    stripped = raw.lstrip()
    record = json.loads(stripped) if stripped.startswith("{") else {"_raw": raw}
    assert telemetry_behavior.classify_content(record) == expected
