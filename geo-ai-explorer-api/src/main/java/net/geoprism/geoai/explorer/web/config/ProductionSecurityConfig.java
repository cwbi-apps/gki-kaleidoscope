package net.geoprism.geoai.explorer.web.config;

import java.util.Set;

import org.springframework.boot.health.actuate.endpoint.HealthEndpoint;
import org.springframework.boot.security.autoconfigure.actuate.web.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandlerImpl;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.AnyRequestMatcher;
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
    // page (which can loop). Defining this chain also disables Boot's default
    // actuator chain, so the health endpoint must be opened here for
    // unauthenticated load balancer health checks.
    http.authorizeHttpRequests(auth -> auth //
        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll() //
        .requestMatchers("/error").permitAll() //
        .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll() //
        .anyRequest().authenticated());
    http.formLogin(form -> form.permitAll());
    http.httpBasic(Customizer.withDefaults());

    // Send the CSRF token to the UI as an XSRF-TOKEN cookie, which the UI
    // echoes back in the X-XSRF-TOKEN header. The browser keeps the cookie in
    // sync with the server (e.g. when the token rotates on login), so the UI
    // never holds a stale copy.
    http.csrf(csrf -> csrf.spa());

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
    // to the login form instead, which issues a fresh session and token. The
    // explicit fallback matters: with a single mapping Spring Security applies
    // that handler to every request, which would redirect rejected API calls
    // to the login form instead of returning 403.
    //
    // API calls without a valid session get a plain 401 rather than a
    // redirect to the login page, which the UI can't follow. The UI reports a
    // 401 as an expired session, distinct from a 403 (e.g. a request blocked
    // by a web application firewall in front of the app).
    http.exceptionHandling(ex -> ex //
        .defaultAccessDeniedHandlerFor(loginCsrfHandler(), PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/login")) //
        .defaultAccessDeniedHandlerFor(new AccessDeniedHandlerImpl(), AnyRequestMatcher.INSTANCE) //
        .defaultAuthenticationEntryPointFor(new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED), PathPatternRequestMatcher.withDefaults().matcher("/api/**")));

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
