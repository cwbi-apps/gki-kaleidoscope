package net.geoprism.geoai.explorer.core.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Sent in the request body rather than the query string so long prompts
 * aren't limited by URL length and don't end up in access logs.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class PromptRequest
{
  private String sessionId;

  private String prompt;
}
