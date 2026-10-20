package net.geoprism.geoai.explorer.web.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

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
        .requestMatchers("/error", "/login").permitAll() //
        .anyRequest().authenticated());
    http.formLogin(form -> form.permitAll());
    http.httpBasic(Customizer.withDefaults());

    return http.build();
  }
}
