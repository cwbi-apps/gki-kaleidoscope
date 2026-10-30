/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.web.config;

import java.io.IOException;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.security.web.firewall.HttpStatusRequestRejectedHandler;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.RequestRejectedHandler;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * Always-on diagnostics for deployment problems (proxy / load balancer
 * misconfiguration, wrong profile, wrong context path). Costs nothing on normal
 * requests: the rejection logger only runs when Spring Security's firewall
 * rejects a request, and is rate limited so junk traffic can't flood the logs.
 */
@Configuration
public class DiagnosticsConfiguration
{
  private static final Logger logger            = LoggerFactory.getLogger(DiagnosticsConfiguration.class);

  private static final int    MAX_LOGS_PER_MINUTE = 10;

  private static final int    MAX_FIELD_LENGTH  = 300;

  private final AtomicLong    windowStart       = new AtomicLong();

  private final AtomicInteger windowCount       = new AtomicInteger();

  private final AtomicInteger suppressed        = new AtomicInteger();

  @EventListener(ApplicationReadyEvent.class)
  public void logStartup(ApplicationReadyEvent event)
  {
    Environment env = event.getApplicationContext().getEnvironment();
    ServletContext servletContext = event.getApplicationContext().getBean(ServletContext.class);

    String[] profiles = env.getActiveProfiles();

    logger.info("Started: contextPath=[{}] activeProfiles={} sessionTrackingModes={}", //
        servletContext.getContextPath(), //
        profiles.length > 0 ? Arrays.toString(profiles) : "[default]", //
        servletContext.getEffectiveSessionTrackingModes());
  }

  /**
   * Logs requests rejected by Spring Security's firewall (e.g. URLs containing
   * '//' or ';'), then responds with a 400 as Spring Security does by default.
   * Never logs cookies, the Authorization header or the query string.
   */
  @Bean
  public RequestRejectedHandler requestRejectedHandler()
  {
    HttpStatusRequestRejectedHandler delegate = new HttpStatusRequestRejectedHandler();

    return new RequestRejectedHandler()
    {
      @Override
      public void handle(HttpServletRequest request, HttpServletResponse response, RequestRejectedException exception) throws IOException, ServletException
      {
        if (shouldLog())
        {
          logger.warn("Rejected request: method=[{}] uri=[{}] reason=[{}] host=[{}] referer=[{}] x-forwarded-host=[{}] x-forwarded-proto=[{}] x-forwarded-port=[{}] x-forwarded-prefix=[{}] user-agent=[{}]", //
              clean(request.getMethod()), clean(request.getRequestURI()), clean(exception.getMessage()), //
              clean(request.getHeader("Host")), clean(request.getHeader("Referer")), //
              clean(request.getHeader("X-Forwarded-Host")), clean(request.getHeader("X-Forwarded-Proto")), //
              clean(request.getHeader("X-Forwarded-Port")), clean(request.getHeader("X-Forwarded-Prefix")), //
              clean(request.getHeader("User-Agent")));
        }

        delegate.handle(request, response, exception);
      }
    };
  }

  private boolean shouldLog()
  {
    long now = System.currentTimeMillis();
    long start = this.windowStart.get();

    if (now - start >= 60_000 && this.windowStart.compareAndSet(start, now))
    {
      this.windowCount.set(0);

      int count = this.suppressed.getAndSet(0);

      if (count > 0)
      {
        logger.warn("Suppressed logging of {} rejected requests in the last minute", count);
      }
    }

    if (this.windowCount.incrementAndGet() <= MAX_LOGS_PER_MINUTE)
    {
      return true;
    }

    this.suppressed.incrementAndGet();

    return false;
  }

  /**
   * Strips control characters (so a crafted URL can't forge log lines) and
   * caps the length.
   */
  private static String clean(String value)
  {
    if (value == null)
    {
      return null;
    }

    String cleaned = value.replaceAll("\\p{Cntrl}", "?");

    return cleaned.length() > MAX_FIELD_LENGTH ? cleaned.substring(0, MAX_FIELD_LENGTH) + "..." : cleaned;
  }
}
