package net.geoprism.geoai.explorer.web.controller;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.webmvc.autoconfigure.error.ErrorViewResolver;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.View;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

/**
 * Serves the HTML error pages in {@code error-pages/} (403.html / 4xx.html /
 * 5xx.html) to browsers in place of Spring Boot's Whitelabel page, with
 * {@code {{status}}} replaced by the response's status code and
 * {@code {{contextPath}}} by the application's context path. Non-HTML clients
 * still get Spring Boot's JSON error response.
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ErrorPageViewResolver implements ErrorViewResolver
{
  private final Map<String, String> templates = new ConcurrentHashMap<>();

  @Override
  public ModelAndView resolveErrorView(HttpServletRequest request, HttpStatus status, Map<String, Object> model)
  {
    // Every route only requires a login, so a 403 means the session (and its
    // CSRF token) was lost; that page links back to the login form
    String name = status == HttpStatus.FORBIDDEN ? "403" : status.is5xxServerError() ? "5xx" : "4xx";
    String html = this.getTemplate(name) //
        .replace("{{status}}", String.valueOf(status.value())) //
        .replace("{{contextPath}}", request.getContextPath());

    View view = new View()
    {
      @Override
      public String getContentType()
      {
        return "text/html;charset=UTF-8";
      }

      @Override
      public void render(Map<String, ?> model, HttpServletRequest request, HttpServletResponse response) throws IOException
      {
        response.setContentType(this.getContentType());
        response.getWriter().write(html);
      }
    };

    ModelAndView modelAndView = new ModelAndView(view);
    modelAndView.setStatus(status);

    return modelAndView;
  }

  private String getTemplate(String name)
  {
    return this.templates.computeIfAbsent(name, key -> {
      try (InputStream istream = new ClassPathResource("error-pages/" + key + ".html").getInputStream())
      {
        return new String(istream.readAllBytes(), StandardCharsets.UTF_8);
      }
      catch (IOException e)
      {
        throw new UncheckedIOException(e);
      }
    });
  }
}
