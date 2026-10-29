package net.geoprism.geoai.explorer.web.controller;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import net.geoprism.geoai.explorer.web.config.Application;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK, classes = Application.class, properties = { "mapbox.key=test" })
@AutoConfigureMockMvc
public class VersionControllerTest
{
  @Autowired
  private MockMvc         mockMvc;

  // Generated into target/classes by the spring-boot-maven-plugin build-info goal
  @Autowired
  private BuildProperties buildProperties;

  @Test
  public void testVersionReportsBuildInfo() throws Exception
  {
    this.mockMvc.perform(get("/api/version").with(user("admin"))) //
        .andExpect(status().isOk()) //
        .andExpect(jsonPath("$.version").value(this.buildProperties.getVersion())) //
        .andExpect(jsonPath("$.buildTime").isString());
  }

  @Test
  public void testVersionRequiresAuthentication() throws Exception
  {
    this.mockMvc.perform(get("/api/version")).andExpect(status().is4xxClientError());
  }

}
