# lab_provision_dc.ps1 — run on lab-dc01 via QEMU guest agent after Windows install
# Installs AD DS, creates portal.lab domain, seeds misconfigurations for red team practice.
# Executed by: python3 scripts/lab_setup.py

param(
    [string]$DomainName   = "portal.lab",
    [string]$NetbiosName  = "PORTAL",
    [string]$SafeModePass = "LabSafe1!",     # DSRM password
    [string]$AdminPass    = "LabAdmin1!"     # local admin password (set during Windows install)
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ── Phase 1: Install ADDS + promote to DC ─────────────────────────────────────
Write-Host "[DC] Phase 1: Installing AD DS role..."
Install-WindowsFeature -Name AD-Domain-Services -IncludeManagementTools -Verbose

Write-Host "[DC] Promoting to domain controller ($DomainName)..."
$SecureSafe = ConvertTo-SecureString $SafeModePass -AsPlainText -Force

Install-ADDSForest `
    -DomainName $DomainName `
    -DomainNetbiosName $NetbiosName `
    -SafeModeAdministratorPassword $SecureSafe `
    -InstallDns `
    -Force `
    -NoRebootOnCompletion

Write-Host "[DC] Phase 1 complete. Server will reboot. Re-run phase 2 after reboot."
