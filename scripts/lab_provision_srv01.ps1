# lab_provision_srv01.ps1 — run on lab-srv01 after Windows install
# Joins portal.lab domain, installs IIS, registers vulnerable web app + SQL instance.

param(
    [string]$DomainName  = "portal.lab",
    [string]$DCName      = "lab-dc01",
    [string]$DCIp        = "",             # injected by lab_setup.py at runtime
    [string]$DomainUser  = "PORTAL\Administrator",
    [string]$DomainPass  = "LabAdmin1!",
    [string]$LocalPass   = "LabAdmin1!"
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ── DNS: point at DC so domain join works ─────────────────────────────────────
if ($DCIp) {
    Write-Host "[SRV] Setting DNS → $DCIp"
    $adapter = Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | Select-Object -First 1
    Set-DnsClientServerAddress -InterfaceIndex $adapter.InterfaceIndex -ServerAddresses $DCIp
}

# ── Join domain ───────────────────────────────────────────────────────────────
Write-Host "[SRV] Joining domain $DomainName..."
$cred = New-Object PSCredential($DomainUser, (ConvertTo-SecureString $DomainPass -AsPlainText -Force))
try {
    Add-Computer -DomainName $DomainName -Credential $cred -Restart:$false -Force
    Write-Host "[SRV] Domain join queued — will take effect after reboot"
} catch {
    Write-Host "[SRV] Domain join error: $_"
}

# ── Install IIS + management tools ───────────────────────────────────────────
Write-Host "[SRV] Installing IIS..."
Install-WindowsFeature -Name Web-Server,Web-Mgmt-Tools,Web-Default-Doc,Web-Static-Content -IncludeManagementTools

# ── Install MSSQL Express (lightweight, realistic target for Kerberoasting) ───
Write-Host "[SRV] Configuring fake MSSQL service registration..."
# Register the SPN target service without actually installing SQL (lab weight savings)
# The svc_mssql account + SPN on the DC is enough for Kerberoasting exercises.
# For full MSSQL install, run: winget install Microsoft.SQLServer.2022.Express

# ── Enable WinRM for lateral movement practice ────────────────────────────────
Write-Host "[SRV] Enabling WinRM..."
Enable-PSRemoting -Force -SkipNetworkProfileCheck
Set-Item WSMan:\localhost\Client\TrustedHosts -Value "*" -Force

# ── Create a local admin account (lateral movement target) ───────────────────
$lpass = ConvertTo-SecureString $LocalPass -AsPlainText -Force
try {
    New-LocalUser -Name "localadmin" -Password $lpass -PasswordNeverExpires $true -Description "Lab local admin"
    Add-LocalGroupMember -Group "Administrators" -Member "localadmin"
    Write-Host "[SRV] Local admin: localadmin / $LocalPass"
} catch { Write-Host "[SRV] localadmin exists" }

# ── Disable Windows Firewall on lab networks (ease of attack, lab only) ───────
Set-NetFirewallProfile -Profile Domain,Public,Private -Enabled False
Write-Host "[SRV] Firewall disabled (lab range)"

Write-Host ""
Write-Host "[SRV] Provisioning complete. Reboot needed to complete domain join."
Write-Host "  Attack paths on this host:"
Write-Host "  - IIS on port 80 (HTTP)"
Write-Host "  - WinRM on 5985 (PowerShell remoting)"
Write-Host "  - NTLM relay via SMB/HTTP"
Write-Host "  - Local admin reuse: localadmin / $LocalPass"
