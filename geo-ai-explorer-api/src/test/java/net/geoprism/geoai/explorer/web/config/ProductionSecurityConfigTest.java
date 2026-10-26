package net.geoprism.geoai.explorer.web.config;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import jakarta.servlet.http.Cookie;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK, classes = Application.class, properties = { "mapbox.key=test", "spring.security.user.name=admin", "spring.security.user.password=password" })
@AutoConfigureMockMvc
public class ProductionSecurityConfigTest
{
  // Not mapped to a controller: a request that passes the security filters
  // gets a 404, one rejected by the CSRF check gets a 403
  private static final String UNMAPPED_POST = "/api/csrf-test";

  @Autowired
  private MockMvc             mockMvc;

  @Test
  public void testHealthIsPublic() throws Exception
  {
    // Load balancer health checks are unauthenticated
    this.mockMvc.perform(get("/actuator/health")).andExpect(status().isOk());
  }

  @Test
  public void testHealthIsPublicUnderContextPath() throws Exception
  {
    // Deployed under a non-root context path, e.g. /chat
    this.mockMvc.perform(get("/chat/actuator/health").contextPath("/chat")).andExpect(status().isOk());
  }

  @Test
  public void testOtherActuatorEndpointsRequireAuthentication() throws Exception
  {
    this.mockMvc.perform(get("/actuator/info")).andExpect(status().is4xxClientError());
  }

  @Test
  public void testCsrfTokenCookieIsAcceptedInHeader() throws Exception
  {
    Browser browser = new Browser();
    browser.login();

    Cookie xsrf = browser.cookies.get("XSRF-TOKEN");

    assertNotNull(xsrf, "The XSRF-TOKEN cookie should be set after logging in");

    browser.perform(post(UNMAPPED_POST).header("X-XSRF-TOKEN", xsrf.getValue()).contentType(MediaType.APPLICATION_JSON).content("{}"));

    assertEquals(404, browser.status);
  }

  @Test
  public void testPostWithoutCsrfTokenIsRejected() throws Exception
  {
    Browser browser = new Browser();
    browser.login();

    browser.perform(post(UNMAPPED_POST).contentType(MediaType.APPLICATION_JSON).content("{}"));

    assertEquals(403, browser.status);
  }

  @Test
  public void testCsrfTokenRotatesOnLogin() throws Exception
  {
    Browser browser = new Browser();
    browser.perform(get("/login"));

    Cookie before = browser.cookies.get("XSRF-TOKEN");

    assertNotNull(before, "The login page should set the XSRF-TOKEN cookie");

    browser.login();

    // The pre-login token must no longer be what the browser sends, or be accepted
    assertNotEquals(before.getValue(), browser.cookies.get("XSRF-TOKEN").getValue());

    browser.perform(post(UNMAPPED_POST).header("X-XSRF-TOKEN", before.getValue()).contentType(MediaType.APPLICATION_JSON).content("{}"));

    assertEquals(403, browser.status);
  }

  @Test
  public void testLoginWithStaleCsrfTokenReturnsToLoginForm() throws Exception
  {
    MvcResult result = this.mockMvc.perform(post("/login").param("username", "admin").param("password", "password").param("_csrf", "stale")).andReturn();

    assertEquals(302, result.getResponse().getStatus());
    assertEquals("/login?error", result.getResponse().getRedirectedUrl());
  }

  @Test
  public void testApiWithoutSessionReturns401() throws Exception
  {
    // The Accept header Angular's HttpClient sends
    MvcResult result = this.mockMvc.perform(get("/api/configuration/get").accept("application/json, text/plain, */*")).andReturn();

    assertEquals(401, result.getResponse().getStatus());

    // A Basic challenge would make the browser show its own login dialog
    assertNull(result.getResponse().getHeader("WWW-Authenticate"));
  }

  @Test
  public void testApiPostWithExpiredSessionReturns401() throws Exception
  {
    // The XSRF-TOKEN cookie outlives the session, so the CSRF check passes and
    // the request fails authentication instead
    Browser browser = new Browser();
    browser.perform(get("/login"));

    Cookie xsrf = browser.cookies.get("XSRF-TOKEN");

    browser.perform(post("/api/chat/prompt/start").header("X-XSRF-TOKEN", xsrf.getValue()).contentType(MediaType.APPLICATION_JSON).content("{\"sessionId\":\"s1\",\"prompt\":\"hello\"}"));

    assertEquals(401, browser.status);
  }

  @Test
  public void testPageWithoutSessionRedirectsToLogin() throws Exception
  {
    MvcResult result = this.mockMvc.perform(get("/").accept(MediaType.TEXT_HTML)).andReturn();

    assertEquals(302, result.getResponse().getStatus());
    assertTrue(result.getResponse().getRedirectedUrl().endsWith("/login"));
  }

  @Test
  public void testPromptIsSentInPostBody() throws Exception
  {
    Browser browser = new Browser();
    browser.login();

    // Well beyond what fits in a URL
    String prompt = "Run this SPARQL query: SELECT ?s ?p ?o WHERE { ?s ?p ?o } " + "x".repeat(20_000);
    String body = "{\"sessionId\":\"s1\",\"prompt\":\"" + prompt + "\"}";

    browser.perform(post("/api/chat/prompt/start").header("X-XSRF-TOKEN", browser.cookies.get("XSRF-TOKEN").getValue()).contentType(MediaType.APPLICATION_JSON).content(body));

    assertEquals(202, browser.status);
    assertTrue(browser.body.contains("jobId"));
  }

  /**
   * Carries the session and cookies between requests the way a browser would.
   */
  private class Browser
  {
    private final MockHttpSession     session = new MockHttpSession();

    private final Map<String, Cookie> cookies = new LinkedHashMap<>();

    private int                       status;

    private String                    body;

    void login() throws Exception
    {
      this.perform(get("/login"));

      // Submit the login form with its hidden _csrf field, as a browser would
      Matcher matcher = Pattern.compile("name=\"_csrf\"[^>]*value=\"([^\"]+)\"").matcher(this.body);

      assertTrue(matcher.find(), "The login form should include a CSRF token");

      this.perform(post("/login").param("username", "admin").param("password", "password").param("_csrf", matcher.group(1)));
      this.perform(get("/").accept(MediaType.TEXT_HTML));

      assertEquals(200, this.status, "Should be logged in");
    }

    void perform(MockHttpServletRequestBuilder request) throws Exception
    {
      request.session(this.session);

      if (!this.cookies.isEmpty())
      {
        request.cookie(this.cookies.values().toArray(new Cookie[0]));
      }

      MockHttpServletResponse response = mockMvc.perform(request).andReturn().getResponse();

      this.status = response.getStatus();
      this.body = response.getContentAsString();

      // Apply Set-Cookie headers, including deletions
      for (Cookie cookie : response.getCookies())
      {
        if (cookie.getMaxAge() == 0)
        {
          this.cookies.remove(cookie.getName());
        }
        else
        {
          this.cookies.put(cookie.getName(), cookie);
        }
      }
    }
  }
}
