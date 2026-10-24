#!/bin/bash
# Installs ~/Applications/OpenPDF.app, the handler for openpdf:///abs/path.pdf links, so the CoRL 2026 page
# opens local PDFs in Preview (highlights save into the original file) instead of Chrome's viewer.
# Only PDFs under htmls/corl2026/pdfs are opened. Uninstall: rm -rf ~/Applications/OpenPDF.app
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)/htmls/corl2026/pdfs"
APP="$HOME/Applications/OpenPDF.app"
mkdir -p "$HOME/Applications"
rm -rf "$APP"
osacompile -o "$APP" -e 'on open location u
	do shell script quoted form of (POSIX path of (path to me) & "Contents/Resources/open.sh") & " " & quoted form of u
end open location'
cat > "$APP/Contents/Resources/open.sh" <<EOF
#!/bin/bash
p=\$(printf '%s' "\${1#openpdf://}" | /usr/bin/perl -pe 's/%([0-9A-Fa-f]{2})/chr(hex(\$1))/eg')
case "\$p" in
  */../*) exit 1 ;;
  "$ROOT"/*.pdf) [ -f "\$p" ] && exec open -a Preview "\$p" ;;
esac
exit 1
EOF
chmod +x "$APP/Contents/Resources/open.sh"
plutil -replace CFBundleIdentifier -string local.openpdf "$APP/Contents/Info.plist"
plutil -replace CFBundleURLTypes -json '[{"CFBundleURLName":"openpdf","CFBundleURLSchemes":["openpdf"]}]' "$APP/Contents/Info.plist"
codesign --force --deep -s - "$APP"  # Info.plist edit breaks osacompile's ad-hoc signature
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"
echo "installed $APP (opens PDFs under $ROOT)"
