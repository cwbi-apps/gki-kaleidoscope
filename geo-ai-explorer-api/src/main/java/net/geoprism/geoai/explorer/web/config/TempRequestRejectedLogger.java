package net.geoprism.geoai.explorer.web.config;

import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.web.firewall.HttpStatusRequestRejectedHandler;
import org.springframework.security.web.firewall.RequestRejectedException;
import org.springframework.security.web.firewall.RequestRejectedHandler;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

// TEMPORARY: log the raw URL of requests rejected by Spring Security's firewall
// so we can see where a '//' is coming from. Delete once done.
@Configuration
public class TempRequestRejectedLogger
{
  private static final Logger logger = LoggerFactory.getLogger(TempRequestRejectedLogger.class);

  @Bean
  public RequestRejectedHandler requestRejectedHandler()
  {
    HttpStatusRequestRejectedHandler delegate = new HttpStatusRequestRejectedHandler();

    return new RequestRejectedHandler()
    {
      @Override
      public void handle(HttpServletRequest request, HttpServletResponse response, RequestRejectedException exception) throws IOException, ServletException
      {
        logger.error("Rejected request: method=[{}] uri=[{}] query=[{}] reason=[{}] host=[{}] referer=[{}] x-forwarded-host=[{}] x-forwarded-proto=[{}] x-forwarded-port=[{}] x-forwarded-prefix=[{}] user-agent=[{}]", //
            request.getMethod(), request.getRequestURI(), request.getQueryString(), exception.getMessage(), //
            request.getHeader("Host"), request.getHeader("Referer"), request.getHeader("X-Forwarded-Host"), //
            request.getHeader("X-Forwarded-Proto"), request.getHeader("X-Forwarded-Port"), //
            request.getHeader("X-Forwarded-Prefix"), request.getHeader("User-Agent"));

        delegate.handle(request, response, exception);
      }
    };
  }
}
