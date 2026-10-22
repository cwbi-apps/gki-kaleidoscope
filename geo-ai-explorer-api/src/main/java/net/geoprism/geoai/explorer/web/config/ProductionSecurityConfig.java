package net.geoprism.geoai.explorer.web.config;

import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandlerImpl;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

import jakarta.servlet.DispatcherType;

@Configuration
@EnableWebSecurity
@Profile("!dev")
public class ProductionSecurityConfig
{

  @Bean
  public SecurityFilterChain filterChain(HttpSecurity http) throws Exception
  {
    // Same as Spring Boot's default chain, except the error page is public so
    // a rejected request renders an error instead of redirecting to the login
    // page (which can loop).
    http.authorizeHttpRequests(auth -> auth //
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll() //
        .requestMatchers("/error").permitAll() //
        .anyRequest().authenticated());
    http.formLogin(form -> form.permitAll());
    http.httpBasic(Customizer.withDefaults());

    // Only remember page navigations as the post-login destination. By default
    // any non-JSON GET qualifies, so background requests (Chrome DevTools'
    // /.well-known/... probe, map tiles) could overwrite the page the user
    // asked for and send them to a 404 after logging in.
    MediaTypeRequestMatcher html = new MediaTypeRequestMatcher(MediaType.TEXT_HTML);
    html.setIgnoredMediaTypes(Set.of(MediaType.ALL));

    HttpSessionRequestCache requestCache = new HttpSessionRequestCache();
    requestCache.setRequestMatcher(new AndRequestMatcher( //
        PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.GET, "/**"), html));

    http.requestCache(cache -> cache.requestCache(requestCache));

    // A login POST whose CSRF token doesn't match the session (the session
    // expired, the server restarted, or the request reached a different
    // instance) would otherwise render the 403 error page. Send the user back
    // to the login form instead, which issues a fresh session and token.
    http.exceptionHandling(ex -> ex.defaultAccessDeniedHandlerFor(loginCsrfHandler(), //
        PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/login")));

    return http.build();
  }

  private AccessDeniedHandler loginCsrfHandler()
  {
    AccessDeniedHandler delegate = new AccessDeniedHandlerImpl();

    return (request, response, exception) -> {
      if (exception instanceof CsrfException)
      {
        response.sendRedirect(request.getContextPath() + "/login?error");
      }
      else
      {
        delegate.handle(request, response, exception);
      }
    };
  }
}
