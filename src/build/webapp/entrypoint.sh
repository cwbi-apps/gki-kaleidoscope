#!/bin/sh
set -eu

SERVER_XML="$CATALINA_HOME/conf/server.xml"

# --- TEMPORARY DIAGNOSTIC: log Host / X-Forwarded-* on every request ------
# Appends the raw Host header plus X-Forwarded-Host, X-Forwarded-Proto, and
# X-Forwarded-Port to the AccessLogValve pattern so we can see exactly what
# every hop is telling Tomcat. Remove this block once you've captured what
# you need -- it's not meant to stay in the image long-term.
if ! grep -q '%{Host}i' "$SERVER_XML"; then
  awk '
    {
      line = $0
      if (index(line, "pattern=\"") > 0 && index(line, "%{Host}i") == 0) {
        start = index(line, "pattern=\"") + length("pattern=\"")
        rest  = substr(line, start)
        endq  = index(rest, "\"")
        line  = substr(line, 1, start - 1) substr(rest, 1, endq - 1) " %{Host}i %{X-Forwarded-Host}i %{X-Forwarded-Proto}i %{X-Forwarded-Port}i" substr(rest, endq)
      }
      print line
    }
  ' "$SERVER_XML" > "$SERVER_XML.tmp"
  mv "$SERVER_XML.tmp" "$SERVER_XML"
fi
# ---------------------------------------------------------------------------

exec "$CATALINA_HOME/bin/catalina.sh" run
