#!/bin/sh
set -eu

SERVER_XML="$CATALINA_HOME/conf/server.xml"

if ! grep -q "RemoteIpValve" "$SERVER_XML"; then
  sed -i '/<Host /a\
        <Valve className="org.apache.catalina.valves.RemoteIpValve" \
               remoteIpHeader="x-forwarded-for" \
               protocolHeader="x-forwarded-proto" \
               protocolHeaderHttpsValue="https" \
               portHeader="x-forwarded-port" />' \
    "$SERVER_XML"
fi

exec "$CATALINA_HOME/bin/catalina.sh" run
