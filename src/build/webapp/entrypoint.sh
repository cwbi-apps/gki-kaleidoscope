#!/bin/sh
set -eu

SERVER_XML="$CATALINA_HOME/conf/server.xml"

if ! grep -q "RemoteIpValve" "$SERVER_XML"; then

  awk '
    BEGIN {
      in_host = 0
      inserted = 0
    }

    /<Host[[:space:]>]/ {
      in_host = 1
    }

    {
      print
    }

    in_host && />/ && !inserted {
      print "        <Valve className=\"org.apache.catalina.valves.RemoteIpValve\""
      print "               remoteIpHeader=\"x-forwarded-for\""
      print "               protocolHeader=\"x-forwarded-proto\""
      print "               protocolHeaderHttpsValue=\"https\""
      print "               portHeader=\"x-forwarded-port\" />"
      inserted = 1
      in_host = 0
    }
  ' "$SERVER_XML" > "$SERVER_XML.tmp"

  mv "$SERVER_XML.tmp" "$SERVER_XML"
fi

exec "$CATALINA_HOME/bin/catalina.sh" run
