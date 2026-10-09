#
#
#

FROM public.ecr.aws/docker/library/tomcat:11-jdk25

ENV LOG_LEVEL=error

# Tomcat webapp directory name, which determines the servlet context path:
#   ROOT              -> /
#   kaleidoscope      -> /kaleidoscope
#   usace#kaleidoscope -> /usace/kaleidoscope
ARG CONTEXT_PATH=ROOT

RUN mkdir -p $CATALINA_HOME/wars

# Copy WAR
COPY target/geo-ai-explorer-api.war $CATALINA_HOME/wars/geoprism.war

# Deploy War
RUN mkdir -p $CATALINA_HOME/wars/geoprism && cd $CATALINA_HOME/wars/geoprism && $JAVA_HOME/bin/jar xf $CATALINA_HOME/wars/geoprism.war
RUN mv $CATALINA_HOME/wars/geoprism "$CATALINA_HOME/webapps/$CONTEXT_PATH"

# Log4j properties
ADD https://raw.githubusercontent.com/terraframe/geoprism-cloud/dev/ansible/roles/webserver/files/log4j2.xml $CATALINA_HOME/webapps/$CONTEXT_PATH/WEB-INF/classes/log4j2.xml
RUN sed -i -e "s/<Root level=\"error\">/<Root level=\"$LOG_LEVEL\">/g" "$CATALINA_HOME/webapps/$CONTEXT_PATH/WEB-INF/classes/log4j2.xml"

ADD https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh $CATALINA_HOME/bin/wait-for-it.sh
RUN chmod +x $CATALINA_HOME/bin/wait-for-it.sh

#CMD ["$CATALINA_HOME/bin/wait-for-it.sh", "-t", 0, "database:$POSTGRES_PORT", "--"]

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
