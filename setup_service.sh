#!/bin/bash

# Configuration
SERVICE_NAME="com.${USER}.tasty0dte"
PLIST_NAME="${SERVICE_NAME}.plist"
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
PLIST_DEST="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"

echo "Setting up Tasty0DTE Service..."
echo "Project Directory: ${PROJECT_DIR}"
echo "Service Name:      ${SERVICE_NAME}"

# Verify run_autotrader.sh exists
if [ ! -f "${PROJECT_DIR}/run_autotrader.sh" ]; then
    echo "Error: run_autotrader.sh not found in ${PROJECT_DIR}"
    exit 1
fi

# Ensure run_autotrader.sh is executable
chmod +x "${PROJECT_DIR}/run_autotrader.sh"

# Create plist content
cat > "${PROJECT_DIR}/${PLIST_NAME}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${PROJECT_DIR}/run_autotrader.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/stderr.log</string>
</dict>
</plist>
EOF

echo "Created plist file at: ${PROJECT_DIR}/${PLIST_NAME}"

# Move to LaunchAgents
mkdir -p "${LAUNCH_AGENTS_DIR}"
mv "${PROJECT_DIR}/${PLIST_NAME}" "${PLIST_DEST}"
echo "Installed plist to: ${PLIST_DEST}"

# Unload existing if running (ignore error if not loaded)
launchctl unload "${PLIST_DEST}" 2>/dev/null

# Load service
echo "Loading service..."
if launchctl load "${PLIST_DEST}"; then
    echo "✅ Service loaded successfully!"
    echo "Logs are available at:"
    echo "  stdout: ${PROJECT_DIR}/stdout.log"
    echo "  stderr: ${PROJECT_DIR}/stderr.log"
    echo ""
    echo "To stop the service, run:"
    echo "  launchctl unload ${PLIST_DEST}"
else
    echo "❌ Failed to load service."
    echo "Try running 'launchctl bootstrap gui/$(id -u) ${PLIST_DEST}' for more info."
    exit 1
fi
