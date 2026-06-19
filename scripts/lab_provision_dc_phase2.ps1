# lab_provision_dc_phase2.ps1 — run after DC reboots post-promotion
# Seeds portal.lab with users, groups, SPNs, weak configs for red team exercises.

param(
    [string]$DomainName = "portal.lab",
    [string]$NetbiosName = "PORTAL"
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
Import-Module ActiveDirectory

$DomainDN = "DC=portal,DC=lab"

Write-Host "[DC] Phase 2: Seeding AD misconfigurations..."

# ── OUs ───────────────────────────────────────────────────────────────────────
foreach ($ou in @("LabUsers","LabComputers","LabServers","ServiceAccounts")) {
    try {
        New-ADOrganizationalUnit -Name $ou -Path $DomainDN -ProtectedFromAccidentalDeletion $false
        Write-Host "  OU: $ou"
    } catch {}
}

# ── Regular users (weak passwords for spray targets) ─────────────────────────
$Users = @(
    @{ Name="arya.stark";    Pass="Winter1!";     Desc="Arya Stark" },
    @{ Name="jon.snow";      Pass="Ghost123!";    Desc="Jon Snow" },
    @{ Name="cersei.lannister"; Pass="Power123!"; Desc="Cersei Lannister" },
    @{ Name="tyrion.lannister"; Pass="Imp1234!";  Desc="Tyrion Lannister" },
    @{ Name="ned.stark";     Pass="Honor123!";    Desc="Ned Stark" },
    @{ Name="daenerys.t";    Pass="Dragons1!";    Desc="Daenerys Targaryen" },
)
foreach ($u in $Users) {
    try {
        $secure = ConvertTo-SecureString $u.Pass -AsPlainText -Force
        New-ADUser -Name $u.Desc -SamAccountName $u.Name -UserPrincipalName "$($u.Name)@$DomainName" `
            -AccountPassword $secure -Enabled $true -Path "OU=LabUsers,$DomainDN" `
            -Description $u.Desc -PasswordNeverExpires $true
        Write-Host "  User: $($u.Name)"
    } catch { Write-Host "  User exists: $($u.Name)" }
}

# ── Service accounts with SPNs (Kerberoasting targets) ───────────────────────
$SVCs = @(
    @{ Sam="svc_mssql";   Pass="Mssql2022!"; SPN="MSSQLSvc/lab-srv01.$DomainName:1433" },
    @{ Sam="svc_iis";     Pass="IisAdmin1!"; SPN="HTTP/lab-srv01.$DomainName" },
    @{ Sam="svc_backup";  Pass="Backup123!"; SPN="backup/lab-srv01.$DomainName" },
)
foreach ($svc in $SVCs) {
    try {
        $secure = ConvertTo-SecureString $svc.Pass -AsPlainText -Force
        New-ADUser -Name $svc.Sam -SamAccountName $svc.Sam `
            -UserPrincipalName "$($svc.Sam)@$DomainName" `
            -AccountPassword $secure -Enabled $true `
            -Path "OU=ServiceAccounts,$DomainDN" -PasswordNeverExpires $true
        Set-ADUser -Identity $svc.Sam -ServicePrincipalNames @{Add=$svc.SPN}
        Write-Host "  SVC+SPN: $($svc.Sam) → $($svc.SPN)"
    } catch { Write-Host "  SVC exists: $($svc.Sam)" }
}

# ── AS-REP roasting targets (no pre-auth required) ───────────────────────────
foreach ($u in @("arya.stark","ned.stark")) {
    Set-ADAccountControl -Identity $u -DoesNotRequirePreAuth $true
    Write-Host "  AS-REP: $u (pre-auth disabled)"
}

# ── Groups ────────────────────────────────────────────────────────────────────
try {
    New-ADGroup -Name "IT Admins" -GroupScope Global -Path "OU=LabUsers,$DomainDN"
    Add-ADGroupMember -Identity "IT Admins" -Members "tyrion.lannister","cersei.lannister"
    Write-Host "  Group: IT Admins"
} catch {}

try {
    New-ADGroup -Name "Domain Admins Backup" -GroupScope Global -Path "OU=LabUsers,$DomainDN"
    Add-ADGroupMember -Identity "Domain Admins" -Members "tyrion.lannister"
    Write-Host "  Group: Domain Admins += tyrion.lannister (privilege escalation path)"
} catch {}

# ── Weak GPO: disable Windows Defender on lab machines ───────────────────────
try {
    $gpo = New-GPO -Name "Lab - Disable Defender" -Domain $DomainName
    Set-GPRegistryValue -Name "Lab - Disable Defender" -Domain $DomainName `
        -Key "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender" `
        -ValueName "DisableAntiSpyware" -Type DWord -Value 1
    New-GPLink -Name "Lab - Disable Defender" -Target $DomainDN -Domain $DomainName
    Write-Host "  GPO: Defender disabled (lab range)"
} catch { Write-Host "  GPO: $($_.Exception.Message)" }

# ── Unconstrained delegation on service accounts (coercion path) ─────────────
foreach ($svc in @("svc_backup","svc_iis")) {
    try {
        Set-ADAccountControl -Identity $svc -TrustedForDelegation $true
        Write-Host "  Unconstrained delegation: $svc"
    } catch {}
}

# ── Weak ACL: give svc_backup GenericAll on Domain Admins group ──────────────
# Uses dsacls (built into Windows Server) which is more reliable than Set-Acl
# for AD object permissions — avoids SecurityIdentifier cast issues in ADSI.
try {
    $da  = Get-ADGroup "Domain Admins"
    $svc = Get-ADUser  "svc_backup"
    # dsacls /G <trustee DN>:<right>  GA = GenericAll
    $result = dsacls $da.DistinguishedName /G "$($svc.DistinguishedName):GA" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ACL: svc_backup → GenericAll on Domain Admins (dsacls OK)"
    } else {
        # Fallback: explicit SecurityIdentifier cast for Set-Acl
        $sid = New-Object System.Security.Principal.SecurityIdentifier($svc.SID.Value)
        $acl = Get-Acl "AD:$($da.DistinguishedName)"
        $ace = New-Object System.DirectoryServices.ActiveDirectoryAccessRule(
            $sid,
            [System.DirectoryServices.ActiveDirectoryRights]::GenericAll,
            [System.Security.AccessControl.AccessControlType]::Allow,
            [System.DirectoryServices.ActiveDirectorySecurityInheritance]::None
        )
        $acl.AddAccessRule($ace)
        Set-Acl -Path "AD:$($da.DistinguishedName)" -AclObject $acl
        Write-Host "  ACL: svc_backup → GenericAll on Domain Admins (Set-Acl fallback)"
    }
    # Verify: read back the DACL and confirm svc_backup SID is present
    $check = (Get-Acl "AD:$($da.DistinguishedName)").Access | Where-Object {
        $_.IdentityReference -like "*svc_backup*" -or
        $_.IdentityReference -eq $svc.SID.Value
    }
    if ($check) {
        Write-Host "  ACL verified: $($check.Count) ACE(s) for svc_backup on Domain Admins"
    } else {
        Write-Host "  ACL WARN: svc_backup not found in Domain Admins DACL after write"
    }
} catch { Write-Host "  ACL error: $($_.Exception.Message)" }

# ── Audit policy: emit the events the blue/purple detection bench grades on ──
# Default Server 2022 auditing does NOT reliably log 4769 RC4 ticket detail,
# 4662 (DCSync), or 4720/4728 (persistence). Force them on via Advanced Audit
# Policy subcategories so the lab produces a real detection corpus.
try {
    $subcats = @(
        "Kerberos Service Ticket Operations",  # 4769 / 4770
        "Kerberos Authentication Service",      # 4768 / 4771
        "Credential Validation",                # 4776
        "Logon",                                # 4624 / 4625
        "Directory Service Access",             # 4662  (DCSync)
        "User Account Management",              # 4720 / 4722 / 4738
        "Security Group Management",            # 4728 / 4732 / 4756
        "Other Object Access Events"            # scheduled task creation (4698)
    )
    foreach ($sc in $subcats) {
        auditpol /set /subcategory:"$sc" /success:enable /failure:enable | Out-Null
    }
    # RC4 downgrade detail in 4769 is what lets a hunter spot Kerberoasting.
    # Ticket Encryption Type 0x17 (RC4) appears only when this audit is on AND
    # the SPN accounts allow RC4 (they do — lab default).
    Write-Host "  Audit: advanced audit policy enabled (4769/4768/4662/4720/4728/4698)"
} catch { Write-Host "  Audit: $($_.Exception.Message)" }

# Force the change to settle in the local security policy store.
try { gpupdate /target:computer /force | Out-Null } catch {}

Write-Host ""
Write-Host "[DC] Phase 2 complete. Lab misconfigurations seeded:"
Write-Host "  Kerberoastable:        svc_mssql, svc_iis, svc_backup"
Write-Host "  AS-REP roastable:      arya.stark, ned.stark"
Write-Host "  Unconstrained deleg:   svc_backup, svc_iis"
Write-Host "  Weak ACL:              svc_backup → GenericAll on Domain Admins"
Write-Host "  Domain Admin path:     tyrion.lannister (DA member)"
Write-Host "  Password spray:        all LabUsers have weak passwords"
