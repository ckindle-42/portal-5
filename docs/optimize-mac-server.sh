#!/bin/bash

# ================================================
# FINAL optimize-mac-server.sh for macOS 26 Tahoe
# Optimized for M4 Mac Mini Pro (64GB) as dedicated Portal LLM server
# Run with: sudo ./optimize-mac-server.sh
# ================================================

# Safety: Must run as root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run with sudo."
    exit 1
fi

# Get user and base directory from environment or defaults
USER=${OLLAMA_USER:-$(whoami)}
BASE_DIR=${OLLAMA_BASE_DIR:-"/Users/$USER/mac-studio-server"}
LOG_FILE="$BASE_DIR/logs/optimization.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log_action() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_action "Starting FINAL macOS 26 Tahoe optimization for Portal LLM server (M4 Mac Mini Pro)..."

# 1. GPU / Unified Memory Optimization (CRITICAL for MLX)
log_action "Overriding unified memory GPU limit (configurable)..."
GPU_WIRED_MB=52224         # 51 GB for 64 GB system → change to 122880 for 128 GB
sudo sysctl iogpu.wired_limit_mb=$GPU_WIRED_MB
sudo sysctl -w vm.compressor_mode=2   # Better memory compression for heavy LLM workloads

# 2. WindowServer & GUI Overhead Reduction
log_action "Reducing WindowServer VRAM/CPU overhead..."
defaults write com.apple.universalaccess reduceTransparency -bool true
defaults write com.apple.universalaccess reduceMotion -bool true
defaults write com.apple.desktop Background '{default = {SolidColor = (0, 0, 0);};}'

# 3. Extended Power & Headless Settings
log_action "Configuring extended power management..."
sudo pmset -a sleep 0
sudo pmset -a hibernatemode 0
sudo pmset -a disablesleep 1
sudo pmset -a autopoweroff 0
sudo pmset -a standby 0
sudo pmset -a proximitywake 0
sudo pmset -a disksleep 0
sudo pmset -a autorestart 1
sudo pmset -a powerbutton 0
sudo pmset -a powernap 0
sudo pmset -a sms 0
sudo pmset -a tcpkeepalive 1
defaults write com.apple.EnergySaver "PreventSleepWhenDisplayOff" -bool true

# 4. Full Spotlight Disable (Modern Syntax)
log_action "Fully disabling Spotlight indexing everywhere..."
sudo launchctl bootout system/com.apple.metadata.mds 2>/dev/null || true
sudo launchctl disable system/com.apple.metadata.mds 2>/dev/null || true
sudo mdutil -i off -a
sudo mdutil -E -a

# 5. Time Machine
log_action "Disabling Time Machine..."
sudo tmutil disable

# 6. Automatic Updates
log_action "Disabling automatic updates..."
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticCheckEnabled -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool false

# 7. Display / Screen Saver
log_action "Disabling screen saver..."
defaults write com.apple.screensaver idleTime 0

# 8. Ensure Screen Sharing Stays Enabled (Modern Syntax)
log_action "Ensuring Screen Sharing remains active..."
sudo defaults write /var/db/launchd.db/com.apple.launchd/overrides.plist com.apple.screensharing -dict Disabled -bool false
sudo launchctl enable system/com.apple.screensharing 2>/dev/null || true
sudo launchctl bootstrap system /System/Library/LaunchDaemons/com.apple.screensharing.plist 2>/dev/null || true

# 9. Disable File Sharing & Handoff (Modern Syntax)
log_action "Disabling file sharing and Handoff..."
sudo launchctl bootout system/com.apple.AppleFileServer 2>/dev/null || true
sudo launchctl disable system/com.apple.AppleFileServer 2>/dev/null || true
sudo launchctl bootout system/com.apple.smbd 2>/dev/null || true
sudo launchctl disable system/com.apple.smbd 2>/dev/null || true

defaults write ~/Library/Preferences/ByHost/com.apple.coreservices.useractivityd ActivityAdvertisingAllowed -bool no
defaults write ~/Library/Preferences/ByHost/com.apple.coreservices.useractivityd ActivityReceivingAllowed -bool no

# 10. Aggressive Bloat / AI / Telemetry Disable
log_action "Disabling background analytics, Siri/AI, iCloud, location, media, and Tahoe-specific daemons..."

# System Daemons
for daemon in \
    com.apple.analyticsd com.apple.SubmitDiagInfo com.apple.ReportCrash.Root \
    com.apple.biometrickitd com.apple.biomed com.apple.coreduetd com.apple.dprivacyd \
    com.apple.findmymac com.apple.findmymacmessenger com.apple.icloud.findmydeviced \
    com.apple.locationd com.apple.wifianalyticsd com.apple.triald.system \
    com.apple.backupd-helper com.apple.audioanalyticsd com.apple.ecosystemanalyticsd \
    com.apple.modelmanagerd com.apple.intelligenceplatformd com.apple.generativeexperiencesd \
    com.apple.intelligenceflowd com.apple.intelligencecontextd com.apple.assistantd; do
    sudo launchctl bootout system/"$daemon" 2>/dev/null || true
    sudo launchctl disable system/"$daemon" 2>/dev/null || true
done

# User Agents
for agent in \
    com.apple.cloudd com.apple.cloudphotod com.apple.CoreLocationAgent \
    com.apple.siriknowledged com.apple.Siri.agent com.apple.assistantd \
    com.apple.photoanalysisd com.apple.photolibraryd com.apple.quicklook \
    com.apple.quicklook.ui.helper com.apple.quicklook.ThumbnailsAgent \
    com.apple.UsageTrackingAgent com.apple.suggestd com.apple.parsecd \
    com.apple.parsec-fbf com.apple.knowledge-agent com.apple.mediaanalysisd \
    com.apple.mediastream.mstreamd com.apple.newsd com.apple.weatherd com.apple.tipsd; do
    launchctl bootout gui/"$(id -u)"/"$agent" 2>/dev/null || true
    launchctl disable gui/"$(id -u)"/"$agent" 2>/dev/null || true
done

# 11. Make GPU Wired Limit Permanent (Critical for autorestart)
log_action "Creating permanent LaunchDaemon for GPU wired limit (survives reboots/power outages)..."
sudo tee /Library/LaunchDaemons/com.portal.vram.plist > /dev/null << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.portal.vram</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/sbin/sysctl</string>
        <string>iogpu.wired_limit_mb=59392</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
EOF

sudo chown root:wheel /Library/LaunchDaemons/com.portal.vram.plist
sudo chmod 644 /Library/LaunchDaemons/com.portal.vram.plist
sudo launchctl load /Library/LaunchDaemons/com.portal.vram.plist 2>/dev/null || true

log_action "FINAL optimization completed successfully!"
log_action "GPU wired limit is now permanent via LaunchDaemon."
log_action "Expected idle RAM on 64 GB M4 Mac Mini Pro: ~2.5–4 GB"

echo ""
echo "=== OPTIMIZATION FINISHED ==="
echo "Log file: $LOG_FILE"
echo "Reboot now for full effect? (y/n)"
read -r reboot_choice
if [[ "$reboot_choice" == "y" || "$reboot_choice" == "Y" ]]; then
    sudo shutdown -r now
fi