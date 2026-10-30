/*
 * Copyright (c) 2025 TerraFrame
 *
 * Licensed under the MIT License. See the LICENSE file in the project root
 * for full license information.
 */
package net.geoprism.geoai.explorer.web.controller;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import net.geoprism.geoai.explorer.web.config.Application;

// Requires the UI to have been built, since the controller serves the built index.html
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK, classes = Application.class, properties = { "mapbox.key=test" })
@AutoConfigureMockMvc
public class IndexHtmlControllerTest
{
  @Autowired
  private MockMvc         mockMvc;

  // Generated into target/classes by the spring-boot-maven-plugin build-info goal
  @Autowired
  private BuildProperties buildProperties;

  @Test
  public void testIndexContainsVersionMetaTag() throws Exception
  {
    this.mockMvc.perform(get("/").accept(MediaType.TEXT_HTML).with(user("admin"))) //
        .andExpect(status().isOk()) //
        .andExpect(content().string(containsString("<meta name=\"app-version\" content=\"" + this.buildProperties.getVersion() + "\" data-build-time=\"" + this.buildProperties.getTime() + "\">")));
  }

  @Test
  public void testIndexStillRewritesBaseHref() throws Exception
  {
    this.mockMvc.perform(get("/chat/").contextPath("/chat").accept(MediaType.TEXT_HTML).with(user("admin"))) //
        .andExpect(status().isOk()) //
        .andExpect(content().string(containsString("<base href=\"/chat/\"><meta name=\"app-version\"")));
  }

}
