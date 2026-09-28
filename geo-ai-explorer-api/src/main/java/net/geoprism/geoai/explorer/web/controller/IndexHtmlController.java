package net.geoprism.geoai.explorer.web.controller;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.util.HtmlUtils;

import jakarta.servlet.http.HttpServletRequest;

/**
 * Serves the Angular index.html with its {@code <base href>} rewritten to the
 * servlet context path the app is deployed under (e.g. "/kaleidoscope/").
 *
 * The Angular build emits {@code <base href="/">}. All UI asset and API URLs
 * are relative and resolve against the base href, so rewriting it here lets a
 * single WAR run at the root context or at any sub-path without rebuilding the
 * UI.
 *
 * The page is sent with Cache-Control: no-cache so a browser never reuses an
 * index.html rendered for a different context path. The hashed JS/CSS bundles
 * are still served (and cached) by Spring's static resource handling.
 */
@Controller
public class IndexHtmlController
{
  private static final String  INDEX_LOCATION = "static/index.html";

  private static final Pattern BASE_HREF      = Pattern.compile("<base\\s+href\\s*=\\s*\"[^\"]*\"\\s*/?>", Pattern.CASE_INSENSITIVE);

  private volatile String      template;

  @GetMapping(value = { "/", "/index.html" }, produces = MediaType.TEXT_HTML_VALUE)
  public ResponseEntity<String> index(HttpServletRequest request) throws IOException
  {
    String html = this.getTemplate();

    if (html == null)
    {
      // The UI hasn't been built into this WAR
      return ResponseEntity.notFound().build();
    }

    // Context path is "" for the root context, otherwise "/kaleidoscope" (no trailing slash)
    String baseHref = request.getContextPath() + "/";
    String baseTag = "<base href=\"" + HtmlUtils.htmlEscape(baseHref) + "\">";

    Matcher matcher = BASE_HREF.matcher(html);

    if (matcher.find())
    {
      html = matcher.replaceFirst(Matcher.quoteReplacement(baseTag));
    }
    else
    {
      html = html.replaceFirst("(?i)<head>", Matcher.quoteReplacement("<head>" + baseTag));
    }

    return ResponseEntity.ok() //
        .cacheControl(CacheControl.noCache()) //
        .contentType(new MediaType(MediaType.TEXT_HTML, StandardCharsets.UTF_8)) //
        .body(html);
  }

  private String getTemplate() throws IOException
  {
    if (this.template == null)
    {
      Resource resource = new ClassPathResource(INDEX_LOCATION);

      if (!resource.exists())
      {
        return null;
      }

      try (InputStream istream = resource.getInputStream())
      {
        this.template = new String(istream.readAllBytes(), StandardCharsets.UTF_8);
      }
    }

    return this.template;
  }
}
