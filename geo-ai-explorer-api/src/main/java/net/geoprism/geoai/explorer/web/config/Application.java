/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.web.config;

import java.util.EnumSet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.scheduling.annotation.EnableScheduling;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.SessionTrackingMode;

@SpringBootApplication
@EnableScheduling
@ComponentScan(basePackages = { "net.geoprism.geoai.explorer.core", "net.geoprism.geoai.explorer.web" })
public class Application extends SpringBootServletInitializer
{
  public static void main(String[] args)
  {
    SpringApplication.run(Application.class, args);
  }

  @Override
  public void onStartup(ServletContext servletContext) throws ServletException
  {
    // Track sessions by cookie only. Otherwise Tomcat rewrites redirects to
    // include ';jsessionid=...', which Spring Security's firewall rejects,
    // causing an endless redirect loop on the login page.
    servletContext.setSessionTrackingModes(EnumSet.of(SessionTrackingMode.COOKIE));

    super.onStartup(servletContext);
  }
}
